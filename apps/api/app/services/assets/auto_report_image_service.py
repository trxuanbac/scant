import copy
import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.report_repo import section_repo
from app.services.agent.report_research_contracts import ImagePlanItem
from app.services.assets.image_service import image_service


@dataclass
class ImageInsertionResult:
    status: str
    plan_item: ImagePlanItem
    content_json: Dict[str, Any]
    plain_text: str
    asset: Optional[Any] = None
    warning: Optional[str] = None


class AutoReportImageService:
    _MARKER_RE = re.compile(
        r"\[\[IMAGE\s*:\s*title\s*=\s*([^;\]]+)(?:;\s*prompt\s*=\s*([^\]]+))?\]\]",
        flags=re.IGNORECASE,
    )
    _SKIP_TITLES = ("loi mo dau", "loi noi dau", "muc luc", "tai lieu tham khao", "references", "bibliography")

    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", normalized.lower().replace("đ", "d")).strip()

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {token for token in cls._normalize(value).split() if len(token) >= 3}

    @classmethod
    def plan(cls, sections: Iterable[Any], topic: str, max_images: Optional[int] = None) -> List[ImagePlanItem]:
        section_list = list(sections)
        limit = max_images if max_images is not None else max(1, min(6, len(section_list) // 2))
        planned: List[ImagePlanItem] = []
        for section in section_list:
            title = str(getattr(section, "title", "") or "").strip()
            normalized_title = cls._normalize(title)
            if not title or any(marker in normalized_title for marker in cls._SKIP_TITLES):
                continue
            plain_text = str(getattr(section, "plain_text", "") or "")
            match = cls._MARKER_RE.search(plain_text)
            if match:
                caption = match.group(1).strip()
                query = (match.group(2) or caption).strip()
            else:
                continue
            section_id = str(getattr(section, "id", "") or "")
            planned.append(
                ImagePlanItem(
                    id=hashlib.sha1(f"{section_id}:{query}".encode("utf-8")).hexdigest()[:20],
                    section_id=section_id,
                    query=query,
                    purpose=f"Minh họa nội dung mục {title}",
                    caption=caption,
                    alt_text=caption,
                )
            )
            if len(planned) >= limit:
                break
        return planned

    @classmethod
    def _candidate_score(cls, query: str, result: Dict[str, Any]) -> float:
        query_tokens = cls._tokens(query)
        result_tokens = cls._tokens(
            f"{result.get('title') or ''} {result.get('sourceDomain') or ''} {result.get('attribution') or ''}"
        )
        overlap = len(query_tokens & result_tokens)
        return overlap / max(1, len(query_tokens))

    @classmethod
    def _node_text(cls, node: Dict[str, Any]) -> str:
        if node.get("type") == "text":
            return str(node.get("text") or "")
        return "".join(cls._node_text(child) for child in node.get("content") or [] if isinstance(child, dict))

    @classmethod
    def _insert_image_node(
        cls,
        content_json: Dict[str, Any],
        asset: Any,
        item: ImagePlanItem,
    ) -> Dict[str, Any]:
        document = copy.deepcopy(content_json) if isinstance(content_json, dict) else {"type": "doc", "content": []}
        nodes = [
            node
            for node in document.get("content") or []
            if not (isinstance(node, dict) and cls._MARKER_RE.search(cls._node_text(node)))
        ]
        image_node = {
            "type": "image",
            "attrs": {
                "id": f"img_{asset.id}",
                "assetId": asset.id,
                "src": f"/api/v1/assets/images/{asset.id}/content",
                "originalUrl": getattr(asset, "original_url", None),
                "width": min(int(getattr(asset, "width", None) or 520), 620),
                "height": None,
                "alignment": "center",
                "caption": item.caption,
                "alt": item.alt_text,
                "sourceType": "web",
                "sourceName": getattr(asset, "source_domain", None),
                "sourceUrl": getattr(asset, "source_page_url", None) or getattr(asset, "original_url", None),
                "license": getattr(asset, "license", None),
                "attribution": getattr(asset, "attribution", None),
            },
        }
        insert_at = next((index + 1 for index, node in enumerate(nodes) if node.get("type") == "paragraph" and cls._node_text(node).strip()), len(nodes))
        nodes.insert(insert_at, image_node)
        document["type"] = "doc"
        document["content"] = nodes
        return document

    @classmethod
    def _remove_internal_marker(cls, section: Any) -> tuple[Dict[str, Any], str]:
        document = copy.deepcopy(getattr(section, "content_json", None) or {"type": "doc", "content": []})
        document["content"] = [
            node
            for node in document.get("content") or []
            if not (isinstance(node, dict) and cls._MARKER_RE.search(cls._node_text(node)))
        ]
        plain_text = cls._MARKER_RE.sub("", str(getattr(section, "plain_text", "") or ""))
        plain_text = re.sub(r"\n{3,}", "\n\n", plain_text).strip()
        return document, plain_text

    @classmethod
    async def import_and_insert(
        cls,
        db: AsyncSession,
        item: ImagePlanItem,
        *,
        project_id: str,
        report_id: str,
        user_id: Optional[str],
        section: Any,
    ) -> ImageInsertionResult:
        payload = await image_service.search_web_images(item.query, license_mode="all", max_results=8)
        results = sorted(
            [
                result
                for result in payload.get("results") or []
                if cls._candidate_score(item.query, result) > 0
            ],
            key=lambda result: cls._candidate_score(item.query, result),
            reverse=True,
        )
        if not results:
            content_json, plain_text = cls._remove_internal_marker(section)
            await section_repo.update(
                db,
                db_obj=section,
                obj_in={"content_json": content_json, "plain_text": plain_text},
            )
            return ImageInsertionResult(
                status="skipped",
                plan_item=item.model_copy(update={"status": "skipped"}),
                content_json=content_json,
                plain_text=plain_text,
                warning="Không tìm thấy ảnh web phù hợp.",
            )

        last_error: Optional[Exception] = None
        for result in results:
            try:
                asset = await image_service.import_search_result(
                    db,
                    project_id=project_id,
                    report_id=report_id,
                    user_id=user_id,
                    result=result,
                )
            except Exception as exc:
                last_error = exc
                continue
            content_json = cls._insert_image_node(getattr(section, "content_json", None) or {}, asset, item)
            plain_text = cls._MARKER_RE.sub("", str(getattr(section, "plain_text", "") or ""))
            plain_text = re.sub(r"\n{3,}", "\n\n", plain_text).strip()
            await section_repo.update(
                db,
                db_obj=section,
                obj_in={"content_json": content_json, "plain_text": plain_text},
            )
            return ImageInsertionResult(
                status="inserted",
                plan_item=item.model_copy(update={"status": "inserted"}),
                content_json=content_json,
                plain_text=plain_text,
                asset=asset,
            )

        content_json, plain_text = cls._remove_internal_marker(section)
        await section_repo.update(
            db,
            db_obj=section,
            obj_in={"content_json": content_json, "plain_text": plain_text},
        )
        return ImageInsertionResult(
            status="failed",
            plan_item=item.model_copy(update={"status": "failed"}),
            content_json=content_json,
            plain_text=plain_text,
            warning=f"Không thể tải ảnh web: {last_error}" if last_error else "Không thể tải ảnh web.",
        )


auto_report_image_service = AutoReportImageService()
