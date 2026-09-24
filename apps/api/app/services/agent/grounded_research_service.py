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
        "va", "la", "ve", "voi", "tai", "tu", "den", "theo", "khi", "qua", "de", "duoc",
    }
    _TOPIC_GENERIC_WORDS = _STOP_WORDS | {
        "tich", "thi", "truong", "tong", "quan", "hien", "thuc", "trang", "nghien", "cuu",
        "chien", "luoc", "giai", "phap", "xuat", "danh", "gia", "dong", "khuc", "pho", "thong",
        "tham", "nhap", "phat", "trien", "mo", "hinh", "ung", "dung", "yeu", "cau", "noi", "dung",
        "market", "analysis", "strategy", "research", "overview", "report", "solution", "current",
    }
    _CONCEPT_COMPONENTS = {
        "__electric_vehicle__": {
            "xe", "dien", "o", "to", "ev", "bev", "electric", "vehicle", "vehicles", "car", "cars",
            "automobile", "automobiles", "automotive", "electrification", "electrified",
        },
        "__ecommerce__": {
            "thuong", "mai", "dien", "tu", "ecommerce", "commerce", "electronic", "online", "retail",
        },
        "__digital_transformation__": {
            "chuyen", "doi", "so", "digital", "transformation",
        },
        "__artificial_intelligence__": {
            "tri", "tue", "nhan", "tao", "artificial", "intelligence", "ai",
        },
    }

    @classmethod
    def _normalize_text(cls, value: str) -> str:
        normalized = unicodedata.normalize("NFD", value or "")
        normalized = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
        return re.sub(r"[^a-z0-9]+", " ", normalized.lower().replace("đ", "d")).strip()

    @classmethod
    def _tokens(cls, value: str) -> set[str]:
        tokens = {
            token
            for token in cls._normalize_text(value).split()
            if len(token) >= 3 and token not in cls._STOP_WORDS
        }
        return tokens | cls._semantic_concepts(value)

    @classmethod
    def _semantic_concepts(cls, value: str) -> set[str]:
        """Map common Vietnamese/English topic phrases to stable, specific concepts."""
        normalized = cls._normalize_text(value)
        concepts: set[str] = set()
        electric_vehicle_phrase = re.search(
            r"\b(?:xe dien|o to dien|electric (?:vehicle|vehicles|car|cars|mobility)|"
            r"battery electric (?:vehicle|vehicles)|ev|bev)\b",
            normalized,
        )
        vehicle_term = re.search(r"\b(?:xe|o to|vehicle|vehicles|car|cars|automotive)\b", normalized)
        electrification_term = re.search(r"\b(?:dien hoa|electrification|electrified)\b", normalized)
        if electric_vehicle_phrase or (vehicle_term and electrification_term):
            concepts.add("__electric_vehicle__")
        if re.search(
            r"\b(?:thuong mai dien tu|e commerce|ecommerce|electronic commerce|online retail)\b",
            normalized,
        ):
            concepts.add("__ecommerce__")
        if re.search(r"\b(?:chuyen doi so|digital transformation)\b", normalized):
            concepts.add("__digital_transformation__")
        if re.search(r"\b(?:tri tue nhan tao|artificial intelligence|ai)\b", normalized):
            concepts.add("__artificial_intelligence__")
        return concepts

    @classmethod
    def _topic_anchor_tokens(cls, value: str) -> set[str]:
        """Return the distinctive words that every automatically selected source should share."""
        anchors = {
            token
            for token in cls._normalize_text(value).split()
            if len(token) >= 2 and token not in cls._TOPIC_GENERIC_WORDS and not token.isdigit()
        }
        concepts = cls._semantic_concepts(value)
        for concept in concepts:
            anchors.difference_update(cls._CONCEPT_COMPONENTS.get(concept, set()))
        return anchors | concepts

    @staticmethod
    def _shares_topic_anchor(topic_anchors: set[str], content_anchors: set[str]) -> bool:
        if not topic_anchors:
            return True
        shared = topic_anchors & content_anchors
        if not shared:
            return False
        # A mapped phrase such as xe dien/electric vehicle is already a
        # distinctive multi-word signal. For raw words, require either a rare
        # long token or two independent anchors so one ambiguous word such as
        # "xe" or "dien" cannot admit an unrelated source.
        if any(token.startswith("__") for token in shared):
            return True
        if len(topic_anchors) == 1:
            return True
        if any(len(token) >= 7 for token in shared):
            return True
        return len(shared) >= 2

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
        score = min(1.0, overlap / max(1, min(len(query_tokens), 6)))
        if cls._semantic_concepts(query) & cls._semantic_concepts(f"{title} {excerpt}"):
            score = max(score, 0.5)
        return score

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
            # A reputable domain is not evidence for an unrelated topic. Search
            # providers can return high-authority academic results with no query
            # overlap, so discard those before they reach the report ledger.
            if relevance_score < 0.2:
                continue
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
            metadata = getattr(source, "metadata_json", None) or {}
            research_scores = metadata.get("research_scores") if isinstance(metadata, dict) else {}
            stored_relevance = research_scores.get("relevance") if isinstance(research_scores, dict) else None
            try:
                relevance = float(stored_relevance) if stored_relevance is not None else 0.5
            except (TypeError, ValueError):
                relevance = 0.5
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
                    relevance_score=max(0, min(1, relevance)),
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
        topic: str = "",
    ) -> Dict[str, List[ClaimEvidence]]:
        packets: Dict[str, List[ClaimEvidence]] = {}
        topic_anchors = cls._topic_anchor_tokens(topic)
        for section in sections:
            section_id = str(getattr(section, "id", "") or "")
            title = str(getattr(section, "title", "") or "")
            title_tokens = cls._tokens(title)
            matches: List[ClaimEvidence] = []
            for candidate in candidates:
                content_tokens = cls._tokens(f"{candidate.title} {candidate.excerpt}")
                anchor_content_tokens = cls._topic_anchor_tokens(f"{candidate.title} {candidate.excerpt}")
                if not cls._shares_topic_anchor(topic_anchors, anchor_content_tokens):
                    continue
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
