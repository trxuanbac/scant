import re
from datetime import date
from typing import Any, Dict, Iterable, List, Literal, Optional

from pydantic import BaseModel, Field


CitationStyle = Literal["apa7", "ieee", "numbered"]


class BibliographyResult(BaseModel):
    style: CitationStyle
    source_ids: List[str] = Field(default_factory=list)
    inline_labels: Dict[str, str] = Field(default_factory=dict)
    entries: List[str] = Field(default_factory=list)
    plain_text: str = ""


class BibliographyService:
    _MARKER_RE = re.compile(r"\[SRC:([a-zA-Z0-9-]+)\]")

    @staticmethod
    def _value(source: Any, *keys: str) -> Any:
        for key in keys:
            value = source.get(key) if isinstance(source, dict) else getattr(source, key, None)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return ", ".join(str(item) for item in value if item)
                return value
        return None

    @classmethod
    def _year(cls, source: Any) -> str:
        value = cls._value(source, "published_date", "published_at", "publication_year", "year")
        match = re.search(r"(?:19|20)\d{2}", str(value or ""))
        return match.group(0) if match else "n.d."

    @classmethod
    def inline_label(cls, source: Any, position: int, style: CitationStyle) -> str:
        if style in {"ieee", "numbered"}:
            return f"[{position}]"
        author = cls._value(source, "authors", "author_or_organization", "organization", "publisher")
        if author:
            return f"({author}, {cls._year(source)})"
        title = str(cls._value(source, "title") or "Nguồn không ghi tác giả")
        shortened = title if len(title) <= 48 else f"{title[:45].rstrip()}…"
        return f"({shortened}, {cls._year(source)})"

    @classmethod
    def render_entry(
        cls,
        source: Any,
        position: int,
        style: CitationStyle,
        accessed_at: date,
    ) -> str:
        title = str(cls._value(source, "title") or "Tài liệu không có tiêu đề")
        author = cls._value(source, "authors", "author_or_organization", "organization")
        publisher = cls._value(source, "publisher", "publication_name")
        year = cls._year(source)
        url = str(cls._value(source, "canonical_url", "url") or "")
        access_label = accessed_at.strftime("%Y-%m-%d")

        if style == "apa7":
            lead = f"{author}." if author else f"{title}."
            title_part = f" {title}." if author else ""
            publisher_part = f" {publisher}." if publisher else ""
            url_part = f" {url}" if url else ""
            return f"{lead} ({year}).{title_part}{publisher_part}{url_part}".strip()

        if style == "ieee":
            parts = [f"[{position}]"]
            if author:
                parts.append(f"{author},")
            parts.append(f'"{title},"')
            if publisher:
                parts.append(f"{publisher},")
            parts.append(f"{year}.")
            if url:
                parts.append(f"[Online]. Available: {url}. [Accessed: {access_label}].")
            return " ".join(parts)

        parts = [f"[{position}]"]
        if author:
            parts.append(f"{author}.")
        parts.append(f"{title}.")
        if publisher:
            parts.append(f"{publisher},")
        parts.append(f"{year}.")
        if url:
            parts.append(f"{url} (truy cập {access_label}).")
        return " ".join(parts)

    @classmethod
    def build(
        cls,
        cited_source_ids: Iterable[str],
        sources_by_id: Dict[str, Any],
        style: CitationStyle,
        accessed_at: Optional[date] = None,
    ) -> BibliographyResult:
        ordered_ids = [
            source_id
            for source_id in dict.fromkeys(str(item) for item in cited_source_ids if item)
            if source_id in sources_by_id
        ]
        access_date = accessed_at or date.today()
        labels: Dict[str, str] = {}
        entries: List[str] = []
        for position, source_id in enumerate(ordered_ids, 1):
            source = sources_by_id[source_id]
            labels[source_id] = cls.inline_label(source, position, style)
            entries.append(cls.render_entry(source, position, style, access_date))
        return BibliographyResult(
            style=style,
            source_ids=ordered_ids,
            inline_labels=labels,
            entries=entries,
            plain_text="\n".join(entries),
        )

    @classmethod
    def render_stable_markers(cls, text: str, labels: Dict[str, str]) -> str:
        return cls._MARKER_RE.sub(lambda match: labels.get(match.group(1), ""), text or "")


bibliography_service = BibliographyService()
