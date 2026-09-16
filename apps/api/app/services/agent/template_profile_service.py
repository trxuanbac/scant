import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

from app.services.agent.report_research_contracts import CitationStyle, TemplateProfile


class TemplateProfileService:
    _MANDATORY_SECTIONS = ("KẾT LUẬN", "TÀI LIỆU THAM KHẢO")

    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.sub(r"\s+", " ", normalized.replace("đ", "d").replace("Đ", "D")).strip().lower()

    @classmethod
    def _heading_texts(cls, parsed_context: Dict[str, Any]) -> List[str]:
        headings: List[str] = []
        for item in parsed_context.get("headings") or []:
            value = item.get("text") if isinstance(item, dict) else item
            text = re.sub(r"\s+", " ", str(value or "")).strip()
            if text and text not in headings:
                headings.append(text)
        return headings

    @classmethod
    def _detect_style(cls, text: str) -> Optional[CitationStyle]:
        normalized = cls._normalize(text)
        if not normalized:
            return None
        if re.search(r"(?:^|\n)\s*\[\d{1,3}\]\s+", text) or "ieee" in normalized:
            return "ieee"
        if "apa 7" in normalized or "apa7" in normalized or "american psychological association" in normalized:
            return "apa7"
        if re.search(r"\([A-ZÀ-Ỹ][^()]{1,60},\s*(?:19|20)\d{2}[a-z]?\)", text):
            return "apa7"
        if "trich dan danh so" in normalized or "tai lieu tham khao danh so" in normalized:
            return "numbered"
        return None

    @classmethod
    def _fallback_style(cls, report_type: str) -> CitationStyle:
        normalized = cls._normalize(report_type)
        if any(term in normalized for term in ("technical", "ky thuat", "engineering", "technology")):
            return "ieee"
        if any(term in normalized for term in ("research", "academic", "nghien cuu", "hoc thuat")):
            return "apa7"
        return "numbered"

    @classmethod
    def _required_sections(cls, headings: Iterable[str]) -> List[str]:
        required: List[str] = []
        for heading in headings:
            normalized = cls._normalize(heading)
            if "ket luan" in normalized and "KẾT LUẬN" not in required:
                required.append("KẾT LUẬN")
            if "tai lieu tham khao" in normalized and "TÀI LIỆU THAM KHẢO" not in required:
                required.append("TÀI LIỆU THAM KHẢO")
        for mandatory in cls._MANDATORY_SECTIONS:
            if mandatory not in required:
                required.append(mandatory)
        return required

    @classmethod
    def build(
        cls,
        parsed_context: Dict[str, Any],
        report_type: str,
        explicit_requirements: str,
    ) -> TemplateProfile:
        context = parsed_context or {}
        headings = cls._heading_texts(context)
        full_text = str(context.get("full_text") or "")
        presentation_rules = str(context.get("presentation_rules") or "").strip()
        template_text = "\n".join([full_text, presentation_rules])
        citation_style = (
            cls._detect_style(template_text)
            or cls._detect_style(explicit_requirements or "")
            or cls._fallback_style(report_type)
        )
        has_uploaded_template = bool(
            headings
            or full_text.strip()
            or presentation_rules
            or context.get("file_path")
            or context.get("styles")
        )
        return TemplateProfile(
            headings=headings,
            required_sections=cls._required_sections(headings),
            citation_style=citation_style,
            presentation_rules=presentation_rules,
            has_uploaded_template=has_uploaded_template,
        )


template_profile_service = TemplateProfileService()
