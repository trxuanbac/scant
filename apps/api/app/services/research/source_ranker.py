from typing import Any, Dict, List


class SourceRanker:
    """Ranks sources from 0.0 to 1.0 prioritizing official documentation, academic papers, and standards."""

    OFFICIAL_DOMAINS = [
        "microsoft.com", "spring.io", "react.dev", "angular.dev", "vuejs.org",
        "python.org", "djangoproject.com", "fastapi.tiangolo.com", "nodejs.org",
        "w3.org", "ietf.org", "iso.org", ".gov.vn", ".gov", "chinhphu.vn",
        "vbpl.vn", "who.int", "worldbank.org", "oecd.org", "un.org"
    ]

    ACADEMIC_DOMAINS = [
        "ieeexplore.ieee.org", "acm.org", "arxiv.org", "sciencedirect.com",
        "springer.com", "researchgate.net", "scholar.google.com"
    ]

    UNIVERSITY_DOMAINS = [
        ".edu.vn", ".edu", "hust.edu.vn", "fpt.edu.vn", "vnu.edu.vn", "uit.edu.vn"
    ]

    LOW_QUALITY_SEO_DOMAINS = [
        "pinterest.com", "blogspot.com", "wixsite.com", "wordpress.com"
    ]

    @classmethod
    def calculate_reliability(cls, url: str, source_type: str) -> float:
        u_lower = url.lower()

        # Check for low-quality SEO farms
        if any(d in u_lower for d in cls.LOW_QUALITY_SEO_DOMAINS):
            return 0.30

        if any(d in u_lower for d in cls.OFFICIAL_DOMAINS):
            return 0.98

        if any(d in u_lower for d in cls.ACADEMIC_DOMAINS):
            return 0.96

        if any(d in u_lower for d in cls.UNIVERSITY_DOMAINS):
            return 0.92

        if source_type in ["official_doc", "standard"]:
            return 0.95
        elif source_type == "paper":
            return 0.92
        elif source_type == "book":
            return 0.90
        elif source_type == "university":
            return 0.88

        return 0.75

    @classmethod
    def rank_sources(cls, sources: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        for s in sources:
            url = s.get("url", "")
            stype = s.get("source_type", "website")
            s["reliability_score"] = cls.calculate_reliability(url, stype)

        # Sort descending by reliability score
        return sorted(sources, key=lambda x: x["reliability_score"], reverse=True)


source_ranker = SourceRanker()
