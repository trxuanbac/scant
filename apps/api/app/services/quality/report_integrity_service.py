import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set

from app.services.agent.report_research_contracts import IntegrityIssue, IntegrityResult


class ReportIntegrityService:
    """Final, deterministic checks before an autonomous report is export-ready."""

    _SOURCE_MARKER_RE = re.compile(r"\[SRC\s*:\s*([^\]]+)\]", flags=re.IGNORECASE)
    _IMAGE_MARKER_RE = re.compile(r"\[\[IMAGE\s*:", flags=re.IGNORECASE)
    _STAGE_ORDER = (
        "template_profile",
        "research",
        "draft_sections",
        "bibliography",
        "image_research",
        "integrity",
    )

    @staticmethod
    def _value(item: Any, key: str, default: Any = None) -> Any:
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        normalized = normalized.lower().replace("đ", "d")
        return re.sub(r"[^a-z0-9]+", " ", normalized).strip()

    @classmethod
    def _walk_nodes(cls, node: Any) -> Iterable[Dict[str, Any]]:
        if not isinstance(node, dict):
            return
        yield node
        for child in node.get("content") or []:
            yield from cls._walk_nodes(child)

    @classmethod
    def validate(
        cls,
        *,
        sections: Iterable[Any],
        sources: Iterable[Any],
        images: Iterable[Any],
        template_profile: Optional[Dict[str, Any]] = None,
    ) -> IntegrityResult:
        section_list = list(sections)
        source_list = list(sources)
        image_list = list(images)
        blocking: List[IntegrityIssue] = []
        warnings: List[IntegrityIssue] = []
        source_ids: Set[str] = {str(cls._value(item, "id", "")) for item in source_list}
        image_by_id = {str(cls._value(item, "id", "")): item for item in image_list}
        cited_ids: Set[str] = set()
        bibliography_ids: Set[str] = set()
        image_node_count = 0

        for section in section_list:
            section_id = str(cls._value(section, "id", "") or "") or None
            plain_text = str(cls._value(section, "plain_text", "") or "")
            summary = cls._value(section, "structured_summary_json", {}) or {}
            grounding = summary.get("web_grounding") or {}
            bibliography = summary.get("bibliography") or {}

            for marker in cls._SOURCE_MARKER_RE.findall(plain_text):
                blocking.append(IntegrityIssue(
                    code="dangling_citation",
                    message=f"Còn mã trích dẫn nội bộ chưa được chuyển đổi: {marker.strip()}.",
                    section_id=section_id,
                    source_id=marker.strip() or None,
                ))
            if cls._IMAGE_MARKER_RE.search(plain_text):
                blocking.append(IntegrityIssue(
                    code="unresolved_image_marker",
                    message="Còn yêu cầu ảnh nội bộ chưa được xử lý.",
                    section_id=section_id,
                ))

            section_cited = {str(item) for item in grounding.get("source_ids") or [] if item}
            cited_ids.update(section_cited)
            bibliography_ids.update(str(item) for item in bibliography.get("source_ids") or [] if item)
            for cited_id in sorted(section_cited - source_ids):
                blocking.append(IntegrityIssue(
                    code="missing_source",
                    message="Trích dẫn tham chiếu đến nguồn không tồn tại.",
                    section_id=section_id,
                    source_id=cited_id,
                ))
            for cited_id in grounding.get("invalid_citations") or []:
                blocking.append(IntegrityIssue(
                    code="invalid_citation",
                    message="Trích dẫn không thuộc tập bằng chứng được phép của mục.",
                    section_id=section_id,
                    source_id=str(cited_id),
                ))
            for claim in grounding.get("unsupported_claims") or []:
                blocking.append(IntegrityIssue(
                    code="unsupported_claim",
                    message=f"Luận điểm chưa có bằng chứng: {str(claim)[:240]}",
                    section_id=section_id,
                ))

            for node in cls._walk_nodes(cls._value(section, "content_json", {}) or {}):
                if node.get("type") != "image":
                    continue
                image_node_count += 1
                attrs = node.get("attrs") or {}
                asset_id = str(attrs.get("assetId") or "") or None
                asset = image_by_id.get(asset_id or "")
                source_type = str(attrs.get("sourceType") or cls._value(asset, "source_type", "") or "").lower()
                if source_type != "web":
                    continue
                source_page = (
                    attrs.get("sourceUrl")
                    or cls._value(asset, "source_page_url")
                    or cls._value(asset, "original_url")
                )
                if not source_page:
                    blocking.append(IntegrityIssue(
                        code="image_missing_provenance",
                        message="Ảnh web thiếu liên kết trang nguồn.",
                        section_id=section_id,
                        asset_id=asset_id,
                    ))

        for source_id in sorted(bibliography_ids - cited_ids):
            blocking.append(IntegrityIssue(
                code="uncited_reference",
                message="Tài liệu tham khảo không được trích dẫn trong nội dung.",
                source_id=source_id,
            ))
        for source_id in sorted(cited_ids - bibliography_ids):
            blocking.append(IntegrityIssue(
                code="missing_reference",
                message="Nguồn đã trích dẫn chưa có trong tài liệu tham khảo.",
                source_id=source_id,
            ))

        normalized_titles = {cls._normalize(str(cls._value(item, "title", "") or "")) for item in section_list}
        for required in (template_profile or {}).get("required_sections") or []:
            required_normalized = cls._normalize(str(required))
            if required_normalized and not any(
                required_normalized == title or required_normalized in title
                for title in normalized_titles
            ):
                blocking.append(IntegrityIssue(
                    code="missing_required_section",
                    message=f"Thiếu mục bắt buộc: {required}.",
                ))

        if image_node_count == 0:
            warnings.append(IntegrityIssue(
                code="no_relevant_image",
                message="Không có ảnh phù hợp để chèn; báo cáo vẫn có thể hoàn tất.",
            ))

        return IntegrityResult(
            ready=not blocking,
            blocking_errors=blocking,
            warnings=warnings,
            counts={
                "sections": len(section_list),
                "sources": len(source_list),
                "cited_sources": len(cited_ids),
                "bibliography_sources": len(bibliography_ids),
                "images": image_node_count,
                "blocking_errors": len(blocking),
                "warnings": len(warnings),
            },
        )

    @classmethod
    def resume_stage(cls, metadata: Optional[Dict[str, Any]]) -> str:
        payload = metadata or {}
        pipeline = payload.get("pipeline") or {}
        for stage in cls._STAGE_ORDER:
            checkpoint = pipeline.get(stage)
            if not checkpoint:
                if stage == "template_profile" and payload.get("template_profile"):
                    continue
                if stage == "research" and payload.get("research_plan"):
                    continue
                if stage == "bibliography" and payload.get("bibliography"):
                    continue
                if stage == "image_research" and "image_results" in payload:
                    continue
                if stage == "integrity" and payload.get("integrity_result"):
                    continue
                return stage
            if checkpoint.get("status") != "completed":
                return stage
        return "completed"


report_integrity_service = ReportIntegrityService()
