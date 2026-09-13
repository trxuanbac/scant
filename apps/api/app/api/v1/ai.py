from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.entities import User, Project, Report, ReportSection, Document
from app.repositories.project_repo import project_repo, document_repo
from app.repositories.report_repo import report_repo, section_repo
from app.repositories.source_repo import source_repo
from app.schemas.ai import (
    AnalyzeIntentRequest, AnalyzeIntentResponse,
    OutlineGenerationRequest, OutlineGenerationResponse,
    SectionDraftRequest, SectionEditRequest, AICompletionResponse,
    ReportQualityCheckResponse, CopilotMessageRequest, CopilotMessageResponse
)
from app.api.deps import get_current_user
from app.services.editor.outline_service import outline_service
from app.services.editor.writing_engine import writing_engine
from app.services.editor.context_summarizer import context_summarizer
from app.services.ai.copilot_service import copilot_service

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/analyze-intent", response_model=AnalyzeIntentResponse)
async def analyze_intent(
    req: AnalyzeIntentRequest,
    current_user: User = Depends(get_current_user),
):
    """Analyzes free-form user ideas into structured report profiles and metadata fields."""
    return await outline_service.analyze_intent(req)


@router.post("/generate-outline", response_model=OutlineGenerationResponse)
async def generate_outline(
    req: OutlineGenerationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, req.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    if not req.requirements_text:
        docs = await document_repo.get_multi(db, project_id=req.project_id)
        req_docs = [d.content_text for d in docs if d.document_type in ["requirement", "rubric"]]
        if req_docs:
            req.requirements_text = "\n\n".join(req_docs)[:4000]

    outline_result = await outline_service.generate_outline(req)
    return outline_result


@router.post("/draft-section", response_model=AICompletionResponse)
async def draft_section(
    req: SectionDraftRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, req.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    section = await section_repo.get(db, req.section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")

    # Fetch sources and previous sections for context chaining
    sources = await source_repo.get_by_project(db, req.project_id)
    all_sections = await section_repo.get_by_report(db, req.report_id)
    prev_sections = [s for s in all_sections if s.position < section.position]
    chain_summary = context_summarizer.build_chain_summary(prev_sections)

    sources_dicts = [
        {
            "id": s.id,
            "title": s.title,
            "url": s.url,
            "authors": s.authors,
            "publisher": s.publisher,
            "published_date": s.published_date,
            "summary": s.summary,
            "reliability_score": s.reliability_score
        }
        for s in sources
    ]

    draft_result = await writing_engine.draft_section(
        section_title=section.title,
        section_level=section.level,
        topic_name=project.name,
        sources=sources_dicts,
        previous_summary=chain_summary,
        instruction=req.instruction,
        tone=req.tone,
    )

    # Update section in DB
    await section_repo.update(db, db_obj=section, obj_in={
        "status": "draft",
        "content_json": draft_result["tiptap_json"],
        "plain_text": draft_result["plain_text"],
        "word_count": draft_result["word_count"],
    })

    return AICompletionResponse(
        text=draft_result["plain_text"],
        tiptap_json=draft_result["tiptap_json"],
        claims_verified=draft_result["claims_verified"],
        tokens_used=draft_result["tokens_used"],
    )


@router.post("/edit-selection")
async def edit_selection(
    req: SectionEditRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, req.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    edited_text = await writing_engine.edit_selection(
        selected_text=req.selected_text,
        action=req.action,
        custom_instruction=req.custom_instruction,
    )
    return {"edited_text": edited_text}


@router.post("/check-report/{report_id}", response_model=ReportQualityCheckResponse)
async def check_report_quality(
    report_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.quality.multi_profile_quality_engine import multi_profile_quality_engine

    sections = await section_repo.get_by_report(db, report_id)
    sources = await source_repo.get_by_project(db, project.id)

    quality = multi_profile_quality_engine.evaluate(
        profile=report.report_type or project.type or "business",
        sections=sections,
        sources_count=len(sources)
    )
    return ReportQualityCheckResponse(**quality)


@router.post("/copilot", response_model=CopilotMessageResponse)
async def chat_copilot(
    req: CopilotMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project = await project_repo.get(db, req.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    section = None
    if req.section_id:
        section = await section_repo.get(db, req.section_id)

    docs = await document_repo.get_multi(db, project_id=req.project_id)
    knowledge_docs = [{"id": d.id, "original_name": d.title, "content_text": d.content_text} for d in docs]

    sources_raw = await source_repo.get_by_project(db, req.project_id)
    sources_payload = [{"title": s.title, "publisher": s.publisher, "summary": s.summary} for s in sources_raw]
    report = await report_repo.get(db, req.report_id) if req.report_id else None
    project_metadata = {
        **(project.metadata_json or {}),
        "project_id": project.id,
        "project_name": project.name,
        "project_type": project.type,
        "project_description": project.description,
        "topic_details": project.topic_details_json or {},
        "report_title": report.title if report else None,
        "report_type": report.report_type if report else None,
    }

    return await copilot_service.chat(
        req=req,
        project_metadata=project_metadata,
        knowledge_docs=knowledge_docs,
        sources=sources_payload,
        section_title=section.title if section else None,
        section_text=section.plain_text if section else None,
    )


@router.post("/inspect-facts")
async def inspect_section_facts(
    project_id: str,
    text: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Fact checks claims, percentages, and statements against project sources and data."""
    project = await project_repo.get(db, project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    from app.services.citations.fact_inspector import fact_inspector

    sources_raw = await source_repo.get_by_project(db, project_id)
    sources_payload = [{"title": s.title, "publisher": s.publisher, "summary": s.summary} for s in sources_raw]

    docs = await document_repo.get_multi(db, project_id=project_id)
    dataset_summaries = [f"File {d.title}: {d.content_text[:300]}" for d in docs if d.document_type == "dataset"]

    return await fact_inspector.inspect_facts(
        text=text,
        sources=sources_payload,
        dataset_summaries=dataset_summaries
    )


@router.post("/transform-document")
async def transform_document(
    report_id: str,
    target_format: str = "executive_summary",  # executive_summary, presentation_slides, one_page, technical_memo
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Converts a full report into a presentation, executive summary, 1-pager, or technical memo."""
    report = await report_repo.get(db, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    project = await project_repo.get(db, report.project_id)
    if not project or project.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Project not found")

    sections = await section_repo.get_by_report(db, report_id)
    full_text = "\n\n".join([f"## {s.title}\n{s.plain_text or ''}" for s in sections])

    from app.services.editor.document_transformer import document_transformer

    return await document_transformer.transform(
        title=report.title,
        full_text=full_text,
        target_format=target_format,
        target_audience=(project.metadata_json or {}).get("audience")
    )


class AgentTurnRequest(BaseModel):
    project_id: str
    report_id: Optional[str] = None
    message: str
    active_section_id: Optional[str] = None
    selected_text: Optional[str] = None


@router.get("/agent/tools")
async def list_agent_tools(current_user: User = Depends(get_current_user)):
    """Phase U12: Lists all available tools for Document Agent."""
    from app.services.agent.agent_tool_registry import agent_tool_registry
    return agent_tool_registry.list_tools()


@router.post("/agent/execute-turn")
async def execute_agent_turn(
    req: AgentTurnRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Phase U12: Executes an autonomous multi-tool turn for Document Agent."""
    from app.services.agent.document_agent_service import document_agent_service

    return await document_agent_service.execute_turn(
        db=db,
        project_id=req.project_id,
        report_id=req.report_id,
        user_message=req.message,
        active_section_id=req.active_section_id,
        selected_text=req.selected_text,
    )


class HumanizeRequest(BaseModel):
    text: str
    style: Optional[str] = "academic"  # academic, executive, concise, natural
    custom_instructions: Optional[str] = None


@router.post("/humanize")
async def humanize_text(
    req: HumanizeRequest,
    current_user: User = Depends(get_current_user),
):
    """Refines robotic phrasing into authentic, high-impact human prose."""
    from app.services.quality.humanize_service import humanize_service
    return await humanize_service.humanize(
        text=req.text,
        style=req.style or "academic",
        custom_instructions=req.custom_instructions,
    )


class DiagramGenerateRequest(BaseModel):
    context_text: str
    diagram_type: Optional[str] = "flowchart"  # flowchart, erd, sequence, architecture, process, timeline
    diagram_title: Optional[str] = "Sơ Đồ Quy Trình & Kiến Trúc"
    detail_level: Optional[str] = "standard"


@router.post("/diagram/generate")
async def generate_diagram(
    req: DiagramGenerateRequest,
    current_user: User = Depends(get_current_user),
):
    """Generates an editable Mermaid.js diagram from text context."""
    from app.services.visuals.diagram_agent import visual_diagram_agent, DiagramType
    try:
        dtype = DiagramType(req.diagram_type.lower()) if req.diagram_type else DiagramType.FLOWCHART
    except Exception:
        dtype = DiagramType.FLOWCHART

    spec = await visual_diagram_agent.plan_and_generate_diagram(
        context_text=req.context_text,
        diagram_type=dtype,
        detail_level=req.detail_level or "standard",
        diagram_title=req.diagram_title or "Sơ Đồ Trực Quan",
    )
    return spec.model_dump()

