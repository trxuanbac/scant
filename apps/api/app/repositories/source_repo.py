from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.entities import Source, Citation, ClaimSource, Template, TemplateVersion, Evidence, Claim
from app.repositories.base import BaseRepository


class SourceRepository(BaseRepository[Source]):
    def __init__(self):
        super().__init__(Source)

    async def get_by_project(self, db: AsyncSession, project_id: str) -> List[Source]:
        result = await db.execute(
            select(Source)
            .where(Source.project_id == project_id)
            .order_by(Source.verification_score.desc(), Source.reliability_score.desc(), Source.created_at.desc())
        )
        return list(result.scalars().all())


class EvidenceRepository(BaseRepository[Evidence]):
    def __init__(self):
        super().__init__(Evidence)

    async def get_by_source(self, db: AsyncSession, source_id: str) -> List[Evidence]:
        result = await db.execute(
            select(Evidence)
            .where(Evidence.source_id == source_id)
            .order_by(Evidence.page_number.asc(), Evidence.paragraph_index.asc(), Evidence.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_by_project(self, db: AsyncSession, project_id: str) -> List[Evidence]:
        result = await db.execute(
            select(Evidence)
            .where(Evidence.project_id == project_id)
            .order_by(Evidence.created_at.desc())
        )
        return list(result.scalars().all())


class ClaimRepository(BaseRepository[Claim]):
    def __init__(self):
        super().__init__(Claim)

    async def get_by_report(self, db: AsyncSession, report_id: str) -> List[Claim]:
        result = await db.execute(
            select(Claim)
            .where(Claim.report_id == report_id)
            .order_by(Claim.created_at.asc())
        )
        return list(result.scalars().all())


class CitationRepository(BaseRepository[Citation]):
    def __init__(self):
        super().__init__(Citation)

    async def get_by_section(self, db: AsyncSession, section_id: str) -> List[Citation]:
        result = await db.execute(
            select(Citation)
            .where(Citation.report_section_id == section_id)
            .options(selectinload(Citation.source), selectinload(Citation.evidence))
            .order_by(Citation.citation_number.asc())
        )
        return list(result.scalars().all())

    async def get_by_report(self, db: AsyncSession, report_id: str) -> List[Citation]:
        result = await db.execute(
            select(Citation)
            .where(Citation.report_id == report_id)
            .options(selectinload(Citation.source), selectinload(Citation.evidence))
            .order_by(Citation.citation_number.asc())
        )
        return list(result.scalars().all())

    async def get_by_source(self, db: AsyncSession, source_id: str) -> List[Citation]:
        result = await db.execute(
            select(Citation)
            .where(Citation.source_id == source_id)
        )
        return list(result.scalars().all())


class ClaimSourceRepository(BaseRepository[ClaimSource]):
    def __init__(self):
        super().__init__(ClaimSource)

    async def get_by_section(self, db: AsyncSession, section_id: str) -> List[ClaimSource]:
        result = await db.execute(
            select(ClaimSource)
            .where(ClaimSource.report_section_id == section_id)
            .order_by(ClaimSource.created_at.asc())
        )
        return list(result.scalars().all())


class TemplateRepository(BaseRepository[Template]):
    def __init__(self):
        super().__init__(Template)

    async def get_available(self, db: AsyncSession, user_id: Optional[str] = None) -> List[Template]:
        query = select(Template).options(selectinload(Template.versions))
        if user_id:
            query = query.where((Template.is_system == True) | (Template.is_public == True) | (Template.user_id == user_id))
        else:
            query = query.where((Template.is_system == True) | (Template.is_public == True))
        result = await db.execute(query.order_by(Template.created_at.desc()))
        return list(result.scalars().all())


source_repo = SourceRepository()
evidence_repo = EvidenceRepository()
claim_repo = ClaimRepository()
citation_repo = CitationRepository()
claim_source_repo = ClaimSourceRepository()
template_repo = TemplateRepository()
template_version_repo = BaseRepository[TemplateVersion](TemplateVersion)
