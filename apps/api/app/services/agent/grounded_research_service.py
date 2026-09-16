import hashlib
import re
import unicodedata
from datetime import date
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.services.agent.report_research_contracts import (
    ClaimEvidence,
    ResearchPlan,
    ResearchQuestion,
    SourceCandidate,
)
from app.services.research.source_ranker import source_ranker


class GroundedResearchService:
    _TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid", "ref", "ref_src"}
    _SKIPPED_SECTIONS = (
        "loi mo dau",
        "loi noi dau",
        "muc luc",
        "tai lieu tham khao",
        "references",
        "acknowledgement",
    )
    _STOP_WORDS = {
        "bao", "cao", "phan", "chuong", "muc", "cua", "cho", "the", "and", "with",
        "this", "that", "from", "tren", "trong", "nam", "cac", "nhung", "mot", "viet", "vietnam",
    }

    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", normalized.lower().replace("đ", "d")).strip()

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        return {
            token
            for token in cls._normalize_text(value).split()
            if len(token) >= 3 and token not in cls._STOP_WORDS
        }

    @classmethod
    def canonicalize_url(cls, url: str) -> str:
        parsed = urlsplit((url or "").strip())
        kept = []
        for key, value in parse_qsl(parsed.query, keep_blank_values=True):
            lowered = key.lower()
            if lowered.startswith("utm_") or lowered in cls._TRACKING_KEYS:
                continue
            kept.append((key, value))
        path = parsed.path or "/"
        if path != "/":
            path = path.rstrip("/") or "/"
        return urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), path, urlencode(kept), ""))

    @classmethod
    def _relevance(cls, query: str, title: str, excerpt: str) -> float:
        query_tokens = cls._tokens(query)
        if not query_tokens:
            return 0
        content_tokens = cls._tokens(f"{title} {excerpt}")
        overlap = len(query_tokens & content_tokens)
        return min(1.0, overlap / max(1, min(len(query_tokens), 6)))

    @staticmethod
    def _freshness(published_at: Any) -> float:
        match = re.search(r"(?:19|20)\d{2}", str(published_at or ""))
        if not match:
            return 0.4
        age = max(0, date.today().year - int(match.group(0)))
        if age <= 1:
            return 1.0
        if age <= 3:
            return 0.8
        if age <= 6:
            return 0.6
        return 0.35

    @staticmethod
    def _first_value(item: Dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = item.get(key)
            if value not in (None, "", []):
                if isinstance(value, list):
                    return ", ".join(str(entry) for entry in value if entry)
                return value
        return None

    @classmethod
    def normalize_results(cls, raw: List[Dict[str, Any]], query: str) -> List[SourceCandidate]:
        deduplicated: Dict[str, SourceCandidate] = {}
        for item in raw or []:
            title = str(item.get("title") or "").strip()
            canonical_url = cls.canonicalize_url(str(item.get("url") or ""))
            if not title or not canonical_url.startswith(("http://", "https://")):
                continue
            excerpt = str(cls._first_value(item, "snippet", "summary", "abstract") or "").strip()
            source_type = str(item.get("source_type") or "website").strip().lower()
            trust_score = source_ranker.calculate_reliability(canonical_url, source_type)
            relevance_score = cls._relevance(query, title, excerpt)
            published_at = cls._first_value(item, "published_date", "published_at", "publication_year", "year")
            candidate = SourceCandidate(
                id=str(item.get("id") or hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:20]),
                canonical_url=canonical_url,
                title=title,
                author_or_organization=cls._first_value(item, "authors", "author", "organization", "creator"),
                publisher=cls._first_value(item, "publisher", "publication_name"),
                published_at=str(published_at) if published_at is not None else None,
                accessed_at=date.today(),
                source_type=source_type,
                language=cls._first_value(item, "language", "lang"),
                excerpt=excerpt,
                retrieval_status="available",
                trust_score=trust_score,
                relevance_score=relevance_score,
                freshness_score=cls._freshness(published_at),
            )
            current = deduplicated.get(canonical_url)
            if current is None or cls._score(candidate) > cls._score(current):
                deduplicated[canonical_url] = candidate
        return sorted(deduplicated.values(), key=cls._score, reverse=True)

    @classmethod
    def from_persisted_sources(cls, sources: Iterable[Any]) -> List[SourceCandidate]:
        candidates: List[SourceCandidate] = []
        for source in sources:
            url = cls.canonicalize_url(
                str(getattr(source, "canonical_url", None) or getattr(source, "url", None) or "")
            )
            title = str(getattr(source, "title", "") or "").strip()
            if not title or not url.startswith(("http://", "https://")):
                continue
            author_or_organization = getattr(source, "authors", None) or getattr(source, "organization", None)
            published_at = getattr(source, "published_date", None) or getattr(source, "publication_year", None)
            excerpt = str(getattr(source, "summary", None) or getattr(source, "content_extracted", None) or "").strip()
            trust = float(getattr(source, "reliability_score", 0) or 0)
            candidates.append(
                SourceCandidate(
                    id=str(getattr(source, "id")),
                    canonical_url=url,
                    title=title,
                    author_or_organization=str(author_or_organization) if author_or_organization else None,
                    publisher=getattr(source, "publisher", None),
                    published_at=str(published_at) if published_at is not None else None,
                    accessed_at=date.today(),
                    source_type=str(getattr(source, "source_type", "website") or "website").lower(),
                    language=getattr(source, "language", None),
                    excerpt=excerpt,
                    retrieval_status="available" if getattr(source, "access_status", "open") != "broken" else "unavailable",
                    trust_score=max(0, min(1, trust)),
                    relevance_score=0.5,
                    freshness_score=cls._freshness(published_at),
                )
            )
        return sorted(candidates, key=cls._score, reverse=True)

    @staticmethod
    def _score(candidate: SourceCandidate) -> float:
        return candidate.trust_score * 0.55 + candidate.relevance_score * 0.35 + candidate.freshness_score * 0.10

    @classmethod
    def build_plan(cls, topic: str, sections: Iterable[Any], report_type: str) -> ResearchPlan:
        questions: List[ResearchQuestion] = []
        for section in sections:
            title = str(getattr(section, "title", "") or "").strip()
            normalized_title = cls._normalize_text(title)
            if not title or any(marker in normalized_title for marker in cls._SKIPPED_SECTIONS):
                continue
            section_id = str(getattr(section, "id", "") or "")
            query = f"{topic} {title}".strip()
            query_id = hashlib.sha1(f"{section_id}:{query}".encode("utf-8")).hexdigest()[:20]
            freshness_required = any(
                term in normalized_title
                for term in ("thi truong", "phap luat", "chinh sach", "gia", "thong ke", "xu huong", "hien nay")
            )
            questions.append(
                ResearchQuestion(
                    id=query_id,
                    section_id=section_id,
                    section_title=title,
                    query=query,
                    fact_types=["current" if freshness_required else "background"],
                    preferred_source_types=["government", "official_doc", "paper", "university", "report"],
                    freshness_required=freshness_required,
                    image_requested=True,
                )
            )
        return ResearchPlan(topic=topic, questions=questions)

    @classmethod
    def build_evidence_packets(
        cls,
        sections: Iterable[Any],
        candidates: List[SourceCandidate],
    ) -> Dict[str, List[ClaimEvidence]]:
        packets: Dict[str, List[ClaimEvidence]] = {}
        for section in sections:
            section_id = str(getattr(section, "id", "") or "")
            title = str(getattr(section, "title", "") or "")
            title_tokens = cls._tokens(title)
            matches: List[ClaimEvidence] = []
            for candidate in candidates:
                content_tokens = cls._tokens(f"{candidate.title} {candidate.excerpt}")
                overlap = title_tokens & content_tokens
                if title_tokens and not overlap:
                    continue
                confidence = min(1.0, candidate.trust_score * 0.6 + candidate.relevance_score * 0.4)
                if confidence < 0.35:
                    continue
                matches.append(
                    ClaimEvidence(
                        claim_id=hashlib.sha1(f"{section_id}:{candidate.id}".encode("utf-8")).hexdigest()[:20],
                        section_id=section_id,
                        planned_claim=candidate.excerpt or candidate.title,
                        source_ids=[candidate.id],
                        supporting_excerpts=[candidate.excerpt] if candidate.excerpt else [],
                        confidence=confidence,
                        citation_required=True,
                        verification_status="verified" if candidate.retrieval_status == "available" else "needs_review",
                    )
                )
            packets[section_id] = matches[:8]
        return packets


grounded_research_service = GroundedResearchService()
