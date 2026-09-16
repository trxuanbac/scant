from datetime import date, datetime
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


CitationStyle = Literal["apa7", "ieee", "numbered"]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TemplateProfile(StrictContract):
    schema_version: Literal["1.0"] = "1.0"
    headings: List[str] = Field(default_factory=list)
    required_sections: List[str] = Field(default_factory=list)
    citation_style: CitationStyle
    presentation_rules: str = ""
    has_uploaded_template: bool = False


class ResearchQuestion(StrictContract):
    id: str
    section_id: str
    section_title: str
    query: str
    query_en: Optional[str] = None
    fact_types: List[str] = Field(default_factory=list)
    preferred_source_types: List[str] = Field(default_factory=list)
    freshness_required: bool = False
    image_requested: bool = False


class ResearchPlan(StrictContract):
    schema_version: Literal["1.0"] = "1.0"
    topic: str
    questions: List[ResearchQuestion] = Field(default_factory=list)


class SourceCandidate(StrictContract):
    id: str
    canonical_url: str
    title: str
    author_or_organization: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[str] = None
    accessed_at: Optional[date] = None
    source_type: str = "website"
    language: Optional[str] = None
    excerpt: str = ""
    retrieval_status: Literal["available", "unverified", "unavailable"] = "unverified"
    trust_score: float = Field(default=0, ge=0, le=1)
    relevance_score: float = Field(default=0, ge=0, le=1)
    freshness_score: float = Field(default=0, ge=0, le=1)


class ClaimEvidence(StrictContract):
    claim_id: str
    section_id: str
    planned_claim: str
    source_ids: List[str] = Field(default_factory=list)
    supporting_excerpts: List[str] = Field(default_factory=list)
    confidence: float = Field(default=0, ge=0, le=1)
    citation_required: bool = True
    verification_status: Literal["verified", "needs_review", "unverified"] = "unverified"


class ImagePlanItem(StrictContract):
    id: str
    section_id: str
    query: str
    purpose: str
    caption: str
    alt_text: str
    status: Literal["planned", "inserted", "skipped", "failed"] = "planned"


class IntegrityIssue(StrictContract):
    code: str
    message: str
    section_id: Optional[str] = None
    source_id: Optional[str] = None
    asset_id: Optional[str] = None


class IntegrityResult(StrictContract):
    schema_version: Literal["1.0"] = "1.0"
    ready: bool
    blocking_errors: List[IntegrityIssue] = Field(default_factory=list)
    warnings: List[IntegrityIssue] = Field(default_factory=list)
    counts: Dict[str, int] = Field(default_factory=dict)
    checked_at: datetime = Field(default_factory=datetime.utcnow)

