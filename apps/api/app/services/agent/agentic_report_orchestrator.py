import asyncio
import json
import re
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import Job, Report, ReportSection, Project, TemplateVersion
from app.repositories.base import BaseRepository
from app.repositories.project_repo import project_repo, document_repo, file_repo
from app.repositories.report_repo import report_repo, section_repo
from app.repositories.source_repo import claim_source_repo, source_repo
from app.services.editor.writing_engine import writing_engine
from app.services.editor.outline_service import outline_service
from app.services.research.search_engine import search_engine
from app.services.quality.multi_profile_quality_engine import multi_profile_quality_engine
from app.services.quality.grounding_guard import grounding_guard
from app.services.data.data_engine import data_engine
from app.services.documents.docx_parser import docx_parser
from app.services.templates.template_cleaner import template_cleaner
from app.services.agent.report_context_builder import report_context_builder
from app.services.agent.grounded_research_service import grounded_research_service
from app.services.agent.report_research_contracts import ClaimEvidence
from app.services.agent.template_profile_service import template_profile_service


class AgenticReportOrchestrator:
    """
    Multi-Stage Autonomous Document Engine (Phase U11 & High-Speed Parallel Optimization).
    Executes the One-Click Auto Report Pipeline safely in a standalone session with concurrent section drafting.
    """

    @classmethod
    def _build_template_profile_checkpoint(
        cls,
        template_context: Dict[str, Any],
        report_type: str,
        instructions: Optional[str],
    ) -> Dict[str, Any]:
        profile = template_profile_service.build(
            template_context,
            report_type=report_type,
            explicit_requirements=instructions or "",
        )
        return profile.model_dump(mode="json")

    @classmethod
    def _claim_source_payloads(
        cls,
        section_id: str,
        draft_result: Dict[str, Any],
        evidence_items: List[ClaimEvidence],
    ) -> List[Dict[str, Any]]:
        cited = set(draft_result.get("citations_found") or [])
        payloads: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in evidence_items:
            for source_id in item.source_ids:
                key = (source_id, item.claim_id)
                if source_id not in cited or key in seen:
                    continue
                seen.add(key)
                payloads.append({
                    "report_section_id": section_id,
                    "source_id": source_id,
                    "citation_id": None,
                    "claim_text": item.planned_claim,
                    "evidence_text": item.supporting_excerpts[0] if item.supporting_excerpts else item.planned_claim,
                    "confidence_score": item.confidence,
                    "verification_status": item.verification_status,
                })
        return payloads

    @classmethod
    def _resolve_length_plan(cls, instructions: Optional[str]) -> Dict[str, int]:
        text = instructions or ""
        page_match = re.search(r"(\d{1,3})\s*(?:trang|page|pages)", text, flags=re.IGNORECASE)
        pages = int(page_match.group(1)) if page_match else 12
        pages = max(5, min(pages, 100))
        body_pages = pages
        front_matter_pages = 2
        target_words = body_pages * 300
        target_chapters = max(2, min(12, round(body_pages / 2)))
        return {
            "target_pages": pages,
            "body_pages": body_pages,
            "front_matter_pages": front_matter_pages,
            "estimated_total_pages": body_pages + front_matter_pages,
            "target_words": target_words,
            "target_chapters": target_chapters,
        }

    @classmethod
    def _section_weight(cls, sec: ReportSection) -> float:
        title_upper = (sec.title or "").upper()
        if "TÀI LIỆU THAM KHẢO" in title_upper or "MỤC LỤC" in title_upper:
            return 0.2
        if title_upper.startswith(("LỜI ", "KẾT LUẬN")):
            return 0.5
        if cls._normalize_section_level(sec.title, sec.level) == 1:
            return 0.65
        return 1.0

    @classmethod
    def _allocate_section_word_targets(cls, sections: List[ReportSection], length_plan: Dict[str, int]) -> Dict[str, int]:
        body_sections = [
            sec for sec in sections
            if "MỤC LỤC" not in (sec.title or "").upper()
        ]
        total_weight = sum(cls._section_weight(sec) for sec in body_sections) or 1
        target_words = length_plan["target_words"]
        min_words = 140 if length_plan["body_pages"] <= 8 else 220
        max_words = 650 if length_plan["body_pages"] <= 8 else 1200

        targets: Dict[str, int] = {}
        for sec in body_sections:
            title_upper = (sec.title or "").upper()
            raw_target = int(target_words * cls._section_weight(sec) / total_weight)
            if "TÀI LIỆU THAM KHẢO" in title_upper:
                section_target = max(40, min(raw_target, 80))
            else:
                section_target = max(min_words, min(raw_target, max_words))
            targets[sec.title] = section_target

        overflow = sum(targets.values()) - target_words
        if overflow > 0:
            adjustable = [
                sec.title for sec in body_sections
                if "TÀI LIỆU THAM KHẢO" not in (sec.title or "").upper()
            ]
            while overflow > 0 and adjustable:
                changed = False
                for title in adjustable:
                    if overflow <= 0:
                        break
                    if targets[title] > min_words:
                        targets[title] -= 1
                        overflow -= 1
                        changed = True
                if not changed:
                    break

        return targets

    @classmethod
    async def _load_template_context(cls, db: AsyncSession, report: Report) -> Dict[str, str]:
        if not report.template_version_id:
            return {"full_text": "", "presentation_rules": "", "prompt": ""}

        template_version = await BaseRepository[TemplateVersion](TemplateVersion).get(db, report.template_version_id)
        if not template_version or not template_version.file_path:
            return {"full_text": "", "presentation_rules": "", "prompt": ""}

        try:
            parsed = docx_parser.extract_document(template_version.file_path)
        except Exception:
            return {"full_text": "", "presentation_rules": "", "prompt": ""}

        cleaned_structure = template_cleaner.build_structure_context(parsed)
        full_text = (cleaned_structure.get("full_text") or "").strip()
        presentation_rules = cls._extract_presentation_rules(full_text)
        headings = "\n".join(
            f"- {h.get('text')}"
            for h in cleaned_structure.get("headings", [])
            if h.get("text")
        )

        prompt = f"""
NGỮ CẢNH FILE MẪU DOCX NGƯỜI DÙNG ĐÃ TẢI LÊN:
- File mẫu chỉ dùng cho style/layout/cấu trúc, không dùng làm factual context.
- Giữ heading, numbering, table layout, header/footer, font, margin và page structure.
- Nội dung mẫu, số liệu mẫu, placeholder và prompt nội bộ đã bị loại khỏi ngữ cảnh.
- Không append báo cáo mới vào cuối template theo nghĩa nội dung; khi export phải thay/đổ nội dung mới vào vùng thân báo cáo.

DANH SÁCH HEADING TRONG MẪU:
{headings or "Không phát hiện heading rõ ràng."}

PHẦN QUY ĐỊNH/YÊU CẦU TRÌNH BÀY TRÍCH TỪ MẪU:
{presentation_rules or "Không có phần quy định trình bày riêng; hãy suy luận theo bố cục và văn phong trong toàn bộ mẫu."}
"""

        return {
            "full_text": full_text,
            "presentation_rules": presentation_rules,
            "prompt": prompt.strip(),
            **cleaned_structure,
        }

    @classmethod
    def _extract_presentation_rules(cls, full_text: str) -> str:
        if not full_text:
            return ""
        markers = [
            "QUY ĐỊNH TRÌNH BÀY",
            "YÊU CẦU TRÌNH BÀY",
            "HƯỚNG DẪN TRÌNH BÀY",
            "QUY CÁCH TRÌNH BÀY",
            "CÁCH TRÌNH BÀY",
        ]
        upper = full_text.upper()
        for marker in markers:
            start = upper.find(marker)
            if start >= 0:
                return full_text[start:].strip()[:20000]
        return ""

    @classmethod
    def _build_dataset_context(cls, files: List[Any], docs: List[Any]) -> Dict[str, Any]:
        profiles: List[Dict[str, Any]] = []
        context_parts: List[str] = []

        data_files = [
            f for f in files
            if f.file_type in ["excel", "csv"] or (f.original_name or "").lower().endswith((".csv", ".xlsx", ".xls", ".xlsm"))
        ]
        for data_file in data_files:
            profile = None
            try:
                profile = (data_file.metadata_json or {}).get("dataset_profile")
            except Exception:
                profile = None
            if not profile:
                try:
                    profile = data_engine.profile_dataset(data_file.file_path)
                except Exception as ex:
                    profile = {
                        "file_name": data_file.original_name,
                        "verified_facts": [],
                        "warnings": [f"Không thể phân tích file dữ liệu: {str(ex)}"],
                        "grounding_rules": data_engine.grounding_rules(),
                    }
            profiles.append(profile)
            context_parts.append(data_engine.format_profile_for_prompt(profile))

        if not context_parts:
            for doc in docs:
                if doc.document_type == "dataset" and doc.content_text:
                    if isinstance(doc.content_json, dict) and doc.content_json.get("sheets"):
                        profiles.append(doc.content_json)
                    context_parts.append(doc.content_text[:12000])

        if not context_parts:
            return {"profiles": [], "prompt": "", "has_dataset": False}

        prompt = """
NGỮ CẢNH DỮ LIỆU ĐÃ KIỂM ĐỊNH BẰNG PYTHON:
- Đây là nguồn sự thật duy nhất cho mọi số liệu, KPI, tên nhóm, tên nhân viên, ngày tháng, tiền tệ và tỷ lệ.
- AI chỉ được diễn giải và nhận xét dựa trên VERIFIED_FACTS hoặc thống kê đã tính sẵn bên dưới.
- Nếu cần số liệu mà profile không có, ghi rõ "Dữ liệu nguồn không cung cấp thông tin này".
- Không dùng nội dung/số liệu trong Word template làm dữ liệu thật.
- Khi tạo bảng hoặc biểu đồ, labels và values phải lấy từ thống kê bên dưới, không tự bịa.

{dataset_context}
""".strip().format(dataset_context="\n\n---\n\n".join(context_parts))
        return {"profiles": profiles, "prompt": prompt, "has_dataset": True}

    @classmethod
    def _normalize_section_level(cls, title: str, raw_level: Any) -> int:
        text = (title or "").strip().upper()
        if re.match(r"^(LỜI|MỤC LỤC|CHƯƠNG|KẾT LUẬN|TÀI LIỆU THAM KHẢO)", text):
            return 1
        if re.match(r"^\d+\.\d+", text):
            return 2
        try:
            level = int(raw_level or 1)
        except Exception:
            level = 1
        return max(1, min(level, 3))

    @classmethod
    def _is_placeholder_or_too_short(cls, text: str, min_words: int) -> bool:
        stripped = (text or "").strip()
        if len(stripped.split()) < min_words:
            return True
        placeholder_markers = [
            "Nội dung học thuật được tạo lập dựa trên cấu trúc chuẩn mực",
            "Nội dung đang được soạn thảo",
            "Nội dung phân tích chuyên sâu cho phần này",
        ]
        return any(marker.lower() in stripped.lower() for marker in placeholder_markers)

    @classmethod
    def _deduplicate_paragraphs(cls, text: str) -> str:
        seen: set[str] = set()
        cleaned: List[str] = []
        for block in re.split(r"\n{2,}", text or ""):
            paragraph = block.strip()
            if not paragraph:
                continue
            key = re.sub(r"\W+", " ", paragraph.lower()).strip()
            if len(key) > 80:
                key = key[:220]
            if key in seen and len(paragraph.split()) > 16:
                continue
            seen.add(key)
            cleaned.append(paragraph)
        return "\n\n".join(cleaned)

    @classmethod
    def _deduplicate_visual_markers(cls, text: str, seen_visuals: set[str]) -> str:
        kept_lines: List[str] = []
        for line in (text or "").splitlines():
            marker = line.strip()
            match = re.fullmatch(r"\[\[(IMAGE|CHART)\s*:(.*?)\]\]", marker, flags=re.IGNORECASE | re.DOTALL)
            if match:
                kind = match.group(1).lower()
                payload = re.sub(r"\s+", " ", match.group(2).lower()).strip()
                title_match = re.search(r"title\s*=\s*([^;]+)", payload)
                key = f"{kind}:{title_match.group(1).strip() if title_match else payload[:100]}"
                if key in seen_visuals:
                    continue
                seen_visuals.add(key)
            kept_lines.append(line)
        return "\n".join(kept_lines).strip()

    @classmethod
    def _apply_grounded_charts(cls, text: str, section_context: Dict[str, Any]) -> str:
        chart_specs = (section_context or {}).get("chart_specs") or []
        if not chart_specs:
            return re.sub(r"(?im)^\s*\[\[CHART\s*:.*?\]\]\s*$", "", text or "").strip()
        cleaned = re.sub(r"(?im)^\s*\[\[CHART\s*:.*?\]\]\s*$", "", text or "").strip()
        spec = chart_specs[0]
        labels = ",".join(str(x).replace(",", " ") for x in spec.get("labels", [])[:8])
        values = ",".join(str(x) for x in spec.get("values", [])[:8])
        if not labels or not values:
            return cleaned
        marker = (
            f"[[CHART:type={spec.get('chart_type', 'bar')};"
            f"title={str(spec.get('title') or 'Biểu đồ dữ liệu').replace(';', ' ')};"
            f"labels={labels};values={values};unit={spec.get('unit', '')}]]"
        )
        return f"{cleaned}\n\n{marker}".strip()

    @classmethod
    def _fallback_section_draft(
        cls,
        section_title: str,
        section_level: int,
        topic_name: str,
        sources_payload: List[Dict[str, Any]],
        instructions: str,
        target_words: int,
    ) -> Dict[str, Any]:
        plain_text = writing_engine._build_fallback_draft(
            section_title=section_title,
            topic_name=topic_name,
            instruction=instructions,
            tone="technical" if "CHƯƠNG" in section_title.upper() else "academic",
            sources=sources_payload,
            target_words=target_words,
        )
        return {
            "plain_text": plain_text,
            "tiptap_json": writing_engine._text_to_tiptap_json(plain_text, section_level),
            "word_count": len(plain_text.split()),
        }

    @classmethod
    async def run_workflow(
        cls,
        job_id: str,
        project_id: str,
        report_id: str,
        instructions: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        from app.core.database import async_session_maker
        async with async_session_maker() as session:
            return await cls._run_workflow_with_session(session, job_id, project_id, report_id, instructions)

    @classmethod
    async def _run_workflow_with_session(
        cls,
        db: AsyncSession,
        job_id: str,
        project_id: str,
        report_id: str,
        instructions: Optional[str] = None
    ) -> Dict[str, Any]:
        job_repo = BaseRepository[Job](Job)

        async def check_job_state() -> Optional[str]:
            try:
                fresh_job = await job_repo.get(db, job_id)
                if fresh_job:
                    if fresh_job.status in ["cancelled"]:
                        return "cancelled"
                    if fresh_job.status == "paused":
                        return "paused"
                return None
            except Exception:
                return None

        async def wait_if_paused():
            while True:
                state = await check_job_state()
                if state == "cancelled":
                    raise asyncio.CancelledError("Job was cancelled by user")
                if state != "paused":
                    break
                await asyncio.sleep(0.5)

        async def update_stage(stage_name: str, progress: int, message: str, meta: Optional[Dict[str, Any]] = None):
            await wait_if_paused()
            try:
                job = await job_repo.get(db, job_id)
                if not job:
                    return
                current_meta = job.metadata_json or {}
                timeline = list(current_meta.get("timeline") or [])
                if not timeline or timeline[-1].get("stage") != stage_name or timeline[-1].get("message") != message:
                    timeline.append({
                        "stage": stage_name,
                        "progress": progress,
                        "message": message,
                    })
                timeline = timeline[-30:]
                terminal_status = stage_name if stage_name in {"completed", "review_needed", "failed", "cancelled"} else "completed"
                await job_repo.update(db, db_obj=job, obj_in={
                    "status": "running" if progress < 100 else terminal_status,
                    "progress_percent": progress,
                    "status_message": message,
                    "metadata_json": {**current_meta, **(meta or {}), "current_stage": stage_name, "timeline": timeline}
                })
            except Exception:
                pass

        try:
            project = await project_repo.get(db, project_id)
            report = await report_repo.get(db, report_id)
            if not project or not report:
                await update_stage("failed", 0, "Dự án hoặc báo cáo không tồn tại.")
                return {"error": "Invalid project or report"}

            # STAGE 1: Understand Request & Document Profile
            await update_stage("understand_request", 10, "Đang phân tích yêu cầu và định hình mục tiêu văn bản...")
            doc_type = report.report_type or project.type or "business_report"
            length_plan = cls._resolve_length_plan(instructions)
            template_context = await cls._load_template_context(db, report)
            template_profile = cls._build_template_profile_checkpoint(
                template_context,
                report_type=doc_type,
                instructions=instructions,
            )
            await update_stage(
                "understand_request",
                15,
                "Đã đọc yêu cầu, cấu trúc mẫu và quy chuẩn trích dẫn.",
                {"template_profile": template_profile},
            )

            # STAGE 2: Inspect Knowledge Base & Datasets
            await update_stage("inspect_knowledge_base", 25, "Đang đọc hiểu và tổng hợp tài liệu tham khảo...")
            docs = await document_repo.get_multi(db, project_id=project_id)
            files = await file_repo.get_multi(db, project_id=project_id)
            dataset_context = cls._build_dataset_context(files, docs)

            # STAGE 3: Load user-provided and previously verified sources.
            sources = await source_repo.get_by_project(db, project_id)

            # STAGE 4: Outline Generation
            sections = await section_repo.get_by_report(db, report_id)
            if not sections:
                await update_stage("generate_outline", 35, "Đang thiết kế cấu trúc đề cương logic...")
                outline_res = await outline_service.generate_outline(
                    type("Req", (), {
                        "topic_name": project.name,
                        "project_type": doc_type,
                        "topic_description": project.description,
                        "audience": (project.metadata_json or {}).get("audience", "Ban Lãnh đạo"),
                        "requirements_text": (
                            f"{instructions or ''}\n\n"
                            f"{dataset_context['prompt']}\n\n"
                            f"{template_context['prompt']}\n\n"
                            f"Yêu cầu độ dài: khoảng {length_plan['body_pages']} trang A4 cho PHẦN NỘI DUNG CHÍNH, "
                            f"không tính bìa và mục lục. Tổng phần nội dung khoảng {length_plan['target_words']} từ; "
                            f"toàn bộ file ước tính khoảng {length_plan['estimated_total_pages']} trang nếu cộng bìa/mục lục."
                        ),
                        "target_chapters_count": length_plan["target_chapters"],
                    })()
                )
                pos = 0
                async def create_outline_section(item, parent_prefix: str = ""):
                    nonlocal pos
                    pos += 1
                    level = cls._normalize_section_level(item.title, item.level)
                    sec = await section_repo.create(db, obj_in={
                        "report_id": report.id,
                        "title": item.title,
                        "position": pos,
                        "level": level,
                        "status": "planned",
                        "plain_text": f"{item.title}\n\nNội dung đang được soạn thảo...",
                        "content_json": {"type": "doc", "content": [{"type": "heading", "attrs": {"level": level}, "content": [{"type": "text", "text": item.title}]}]},
                        "word_count": 10,
                    })
                    sections.append(sec)
                    for child in getattr(item, "children", []) or []:
                        await create_outline_section(child, item.title)

                for item in outline_res.outline:
                    await create_outline_section(item)

            # STAGE 5: Plan section-specific research, search, normalize, and bind evidence.
            await update_stage("research", 45, "Đang lập kế hoạch và tìm nguồn riêng cho từng chương mục...")
            research_plan = grounded_research_service.build_plan(project.name, sections, doc_type)
            candidates = grounded_research_service.from_persisted_sources(sources)
            candidates_by_url = {item.canonical_url: item for item in candidates}
            existing_urls = set(candidates_by_url)

            should_search_web = not (doc_type == "data_analysis" and dataset_context["has_dataset"])
            if should_search_web:
                provider = search_engine.get_search_provider()
                for question in research_plan.questions:
                    try:
                        raw_results = await provider.search(question.query, max_results=4)
                    except Exception:
                        raw_results = []
                    for candidate in grounded_research_service.normalize_results(raw_results, question.query):
                        current = candidates_by_url.get(candidate.canonical_url)
                        if current and grounded_research_service._score(current) >= grounded_research_service._score(candidate):
                            continue
                        candidates_by_url[candidate.canonical_url] = candidate

                for candidate in sorted(candidates_by_url.values(), key=grounded_research_service._score, reverse=True):
                    if candidate.canonical_url in existing_urls:
                        continue
                    src = await source_repo.create(db, obj_in={
                        "project_id": project_id,
                        "title": candidate.title,
                        "url": candidate.canonical_url,
                        "canonical_url": candidate.canonical_url,
                        "authors": candidate.author_or_organization,
                        "publisher": candidate.publisher,
                        "published_date": candidate.published_at,
                        "source_type": candidate.source_type,
                        "provider": "web",
                        "language": candidate.language or "vi",
                        "reliability_score": candidate.trust_score,
                        "summary": candidate.excerpt or None,
                        "content_extracted": candidate.excerpt or None,
                        "access_status": "open" if candidate.retrieval_status == "available" else "restricted",
                        "verification_status": "PARTIALLY_VERIFIED",
                        "verification_score": round(candidate.trust_score * 100),
                        "domain_trust": "OFFICIAL" if candidate.trust_score >= 0.95 else "GENERAL_WEB",
                        "metadata_json": {
                            "research_scores": {
                                "trust": candidate.trust_score,
                                "relevance": candidate.relevance_score,
                                "freshness": candidate.freshness_score,
                            }
                        },
                    })
                    sources.append(src)

            candidates = grounded_research_service.from_persisted_sources(sources)
            evidence_packets = grounded_research_service.build_evidence_packets(sections, candidates)
            await update_stage(
                "research",
                55,
                f"Đã thu thập {len(candidates)} nguồn và liên kết bằng chứng theo từng mục.",
                {
                    "research_plan": research_plan.model_dump(mode="json"),
                    "source_candidates": [item.model_dump(mode="json") for item in candidates],
                    "claim_source_ledger": {
                        section_id: [item.model_dump(mode="json") for item in items]
                        for section_id, items in evidence_packets.items()
                    },
                },
            )

            # STAGE 6: High-Speed Parallel Section Drafting
            section_word_targets = cls._allocate_section_word_targets(sections, length_plan)
            await update_stage(
                "draft_sections",
                75,
                f"Đang đồng loạt soạn thảo {len(sections)} chương mục, mục tiêu ~{length_plan['body_pages']} trang nội dung..."
            )
            sources_payload = [
                {
                    "id": s.id,
                    "title": s.title,
                    "url": s.canonical_url or s.url,
                    "authors": s.authors or s.organization,
                    "publisher": s.publisher,
                    "published_date": s.published_date or s.publication_year,
                    "summary": s.summary,
                    "reliability_score": s.reliability_score,
                }
                for s in sources
            ]
            sources_by_id = {candidate.id: candidate for candidate in candidates}
            citation_labels = {candidate.id: f"[{index}]" for index, candidate in enumerate(candidates, 1)}

            async def draft_one_section(sec: ReportSection):
                try:
                    normalized_level = cls._normalize_section_level(sec.title, sec.level)
                    if normalized_level != sec.level:
                        await section_repo.update(db, db_obj=sec, obj_in={"level": normalized_level})
                        sec.level = normalized_level

                    if "TÀI LIỆU THAM KHẢO" in sec.title.upper():
                        ref_lines = ["TÀI LIỆU THAM KHẢO"]
                        if sources_payload:
                            for idx, src in enumerate(sources_payload, 1):
                                ref_lines.append(f"[{idx}] {src.get('title') or 'Nguồn tham khảo'}, {src.get('publisher') or 'Nhà xuất bản/website'}, {src.get('summary') or 'Tài liệu tham khảo cho báo cáo.'}")
                        else:
                            ref_lines.append("Không có nguồn tham khảo ngoài đã được xác minh.")
                        plain_text = "\n".join(ref_lines)
                        return sec, {
                            "plain_text": plain_text,
                            "tiptap_json": writing_engine._text_to_tiptap_json(plain_text, sec.level),
                            "word_count": len(plain_text.split()),
                        }

                    section_target_words = section_word_targets.get(sec.title, 220)
                    section_context = report_context_builder.build_for_section(
                        sec,
                        dataset_context.get("profiles", []),
                        template_context,
                    ) if dataset_context["has_dataset"] else {}
                    validation_result: Dict[str, Any] = {"valid": True, "errors": [], "scores": {}}
                    repair_count = 0

                    base_instruction = (
                        f"{instructions or ''}\n\n"
                        f"{section_context.get('prompt') or dataset_context['prompt']}\n\n"
                        f"{template_context['prompt']}\n\n"
                        f"Hãy viết mục này khoảng {section_target_words} từ để giữ tổng phần nội dung gần {length_plan['body_pages']} trang A4. "
                        "Chỉ viết đúng nội dung của mục đang soạn, không lặp lại nguyên văn đoạn đã dùng ở mục khác, "
                        "không tự tạo lại bìa, mục lục hoặc thông tin sinh viên trong nội dung chương. "
                        "Nếu có dataset, chỉ dùng số liệu trong SECTION-SCOPED GROUNDED CONTEXT, không tự tính lại KPI. "
                        "Không để lộ FACT_, prompt nội bộ hoặc placeholder vào nội dung cuối. "
                        "Khi có bảng/biểu đồ, labels và values phải khớp với verified facts được phép dùng."
                    )

                    draft_res: Dict[str, Any] = {}
                    for attempt in range(1, 4 if dataset_context["has_dataset"] else 2):
                        repair_count = attempt - 1
                        repair_note = ""
                        if attempt > 1:
                            repair_note = (
                                "\n\nREPAIR REQUIRED:\n"
                                f"Validation errors: {json.dumps(validation_result.get('errors', []), ensure_ascii=False)}\n"
                                "Viết lại mục này, loại bỏ số/entity/claim sai và chỉ dùng verified facts được phép."
                            )
                        if dataset_context["has_dataset"]:
                            draft_res = await writing_engine.draft_section(
                                section_title=sec.title,
                                section_level=sec.level,
                                topic_name=project.name,
                                sources=sources_payload,
                                instruction=base_instruction + repair_note,
                                tone="professional",
                                target_words=section_target_words,
                            )
                            min_words = max(140, min(section_target_words // 2, 700))
                            if cls._is_placeholder_or_too_short(draft_res.get("plain_text", ""), min_words):
                                draft_res = cls._fallback_section_draft(
                                    section_title=sec.title,
                                    section_level=sec.level,
                                    topic_name=project.name,
                                    sources_payload=sources_payload,
                                    instructions=base_instruction,
                                    target_words=section_target_words,
                                )
                        else:
                            draft_res = await writing_engine.draft_grounded_section(
                                section_title=sec.title,
                                section_level=sec.level,
                                topic_name=project.name,
                                evidence=evidence_packets.get(sec.id, []),
                                sources_by_id=sources_by_id,
                                citation_labels=citation_labels,
                                instruction=base_instruction,
                                tone="professional",
                                target_words=section_target_words,
                            )
                        draft_res["plain_text"] = cls._deduplicate_paragraphs(draft_res.get("plain_text", ""))
                        if dataset_context["has_dataset"]:
                            draft_res["plain_text"] = cls._apply_grounded_charts(draft_res["plain_text"], section_context)
                            validation_result = grounding_guard.validate_section(draft_res["plain_text"], section_context)
                            if validation_result["valid"]:
                                break
                        else:
                            break

                    draft_res["tiptap_json"] = writing_engine._text_to_tiptap_json(draft_res["plain_text"], sec.level)
                    draft_res["word_count"] = len(draft_res["plain_text"].split())
                    draft_res["validation"] = validation_result
                    draft_res["section_context"] = section_context
                    draft_res["repair_count"] = repair_count
                    return sec, draft_res
                except Exception as ex:
                    fallback_target_words = 450
                    return sec, cls._fallback_section_draft(
                        section_title=sec.title,
                        section_level=cls._normalize_section_level(sec.title, sec.level),
                        topic_name=project.name,
                        sources_payload=sources_payload,
                        instructions=instructions or "",
                        target_words=fallback_target_words,
                    )

            if dataset_context["has_dataset"]:
                draft_results = []
                for sec in sections:
                    draft_results.append(await draft_one_section(sec))
            else:
                draft_results = await asyncio.gather(*[draft_one_section(sec) for sec in sections])

            seen_visuals: set[str] = set()
            validation_results: List[Dict[str, Any]] = []
            for sec, draft_res in draft_results:
                text = cls._deduplicate_visual_markers(draft_res.get("plain_text", ""), seen_visuals)
                draft_res["plain_text"] = text
                draft_res["tiptap_json"] = writing_engine._text_to_tiptap_json(text, sec.level)
                draft_res["word_count"] = len(text.split())
                validation = draft_res.get("validation") or {"valid": True}
                if dataset_context["has_dataset"]:
                    validation_results.append(validation)
                summary_json = {
                    **(getattr(sec, "structured_summary_json", None) or {}),
                    "grounding": {
                        "facts_used": (draft_res.get("section_context") or {}).get("facts_used", []),
                        "source_ranges": (draft_res.get("section_context") or {}).get("source_ranges", []),
                        "allowed_fact_types": (draft_res.get("section_context") or {}).get("allowed_fact_types", []),
                        "validation": validation,
                        "repair_count": draft_res.get("repair_count", 0),
                        "prompt_version": "grounded_section_v1",
                        "temperature": 0.4,
                    },
                    "web_grounding": {
                        "source_ids": draft_res.get("citations_found", []),
                        "eligible_source_ids": draft_res.get("source_ids", []),
                        "invalid_citations": draft_res.get("invalid_citations", []),
                        "unsupported_claims": draft_res.get("unsupported_claims", []),
                        "prompt_version": "grounded_web_section_v1",
                    },
                }
                web_grounding_valid = not draft_res.get("invalid_citations") and not draft_res.get("unsupported_claims")
                await section_repo.update(db, db_obj=sec, obj_in={
                    "status": "draft" if validation.get("valid", True) and web_grounding_valid else "review_needed",
                    "plain_text": draft_res["plain_text"],
                    "content_json": draft_res["tiptap_json"],
                    "word_count": draft_res["word_count"],
                    "structured_summary_json": summary_json,
                })
                claim_rows = cls._claim_source_payloads(
                    section_id=sec.id,
                    draft_result=draft_res,
                    evidence_items=evidence_packets.get(sec.id, []),
                )
                existing_claim_sources = await claim_source_repo.get_by_section(db, sec.id)
                existing_keys = {(item.source_id, item.claim_text) for item in existing_claim_sources}
                for payload in claim_rows:
                    key = (payload["source_id"], payload["claim_text"])
                    if key not in existing_keys:
                        await claim_source_repo.create(db, obj_in=payload)
                        existing_keys.add(key)

            # STAGE 6: Quality Check & Finalization
            await update_stage("run_quality_check", 95, "Đang kiểm định chất lượng và hoàn tất tài liệu...")
            quality = multi_profile_quality_engine.evaluate(
                profile=doc_type,
                sections=sections,
                sources_count=len(sources),
                has_dataset=dataset_context["has_dataset"],
            )
            grounding_gate = grounding_guard.final_quality_gate(validation_results) if dataset_context["has_dataset"] else {"final": True}
            if dataset_context["has_dataset"] and not grounding_gate["final"]:
                quality["overall_score"] = min(quality["overall_score"], 59)
                quality["is_ready_to_export"] = False

            final_status = "completed" if grounding_gate.get("final", True) else "review_needed"
            final_message = (
                f"Báo cáo hoàn chỉnh sẵn sàng. Điểm chất lượng: {quality['overall_score']}/100."
                if final_status == "completed"
                else "Báo cáo đã tạo nhưng cần rà soát vì phát hiện nội dung/số liệu chưa bám dữ liệu nguồn."
            )
            await update_stage(
                final_status,
                100,
                final_message,
                {"quality_score": quality["overall_score"], "report_id": report.id, "grounding_gate": grounding_gate}
            )
            fresh_report = await report_repo.get(db, report_id)
            if fresh_report:
                await report_repo.update(db, db_obj=fresh_report, obj_in={
                    "status": final_status,
                    "document_settings_json": {
                        **(fresh_report.document_settings_json or {}),
                        "grounding_gate": grounding_gate,
                    },
                })

            return {
                "status": final_status,
                "quality_score": quality["overall_score"],
                "report_id": report.id,
                "sections_count": len(sections),
            }

        except asyncio.CancelledError:
            try:
                job = await job_repo.get(db, job_id)
                if job:
                    current_meta = job.metadata_json or {}
                    timeline = [
                        *(current_meta.get("timeline") or []),
                        {"stage": "cancelled", "progress": job.progress_percent, "message": "Quy trình đã được người dùng hủy bỏ."},
                    ][-30:]
                    await job_repo.update(db, db_obj=job, obj_in={
                        "status": "cancelled",
                        "status_message": "Quy trình đã được người dùng hủy bỏ.",
                        "metadata_json": {**current_meta, "current_stage": "cancelled", "timeline": timeline},
                    })
            except Exception:
                pass
            return {"status": "cancelled"}
        except Exception as e:
            try:
                job = await job_repo.get(db, job_id)
                if job:
                    current_meta = job.metadata_json or {}
                    timeline = [
                        *(current_meta.get("timeline") or []),
                        {"stage": "failed", "progress": job.progress_percent, "message": f"Lỗi: {str(e)}"},
                    ][-30:]
                    await job_repo.update(db, db_obj=job, obj_in={
                        "status": "failed",
                        "status_message": f"Lỗi trong quá trình thực thi: {str(e)}",
                        "error_message": str(e),
                        "metadata_json": {**current_meta, "current_stage": "failed", "timeline": timeline},
                    })
                fresh_report = await report_repo.get(db, report_id)
                if fresh_report:
                    await report_repo.update(db, db_obj=fresh_report, obj_in={"status": "failed"})
            except Exception:
                pass
            return {"status": "failed", "error": str(e)}


agentic_orchestrator = AgenticReportOrchestrator()
