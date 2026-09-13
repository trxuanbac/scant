"""Bounded operational metadata queries. Never serialize ORM objects or content blobs."""
from datetime import datetime, timezone
from time import perf_counter
import os
import shutil
from fastapi import HTTPException
from sqlalchemy import select, func, or_, case, literal
from app.models.entities import (Project, Document, UploadedFile, Template, TemplateVersion,
    Report, Job, User, AIUsageEvent)
from app.core.config import settings


def utc(value):
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def encode(row):
    return {key: utc(value) if isinstance(value, datetime) else value for key, value in dict(row).items()}


def count_for(model, foreign_key, parent):
    return select(func.count(model.id)).where(foreign_key == parent).correlate_except(model).scalar_subquery()


async def list_resources(db, kind, filters, resource_id=None):
    owner = User.email.label('owner_email')
    if kind == 'projects':
        m = Project
        columns = [m.id, m.name, m.user_id, owner, m.type, m.created_at, m.updated_at,
            count_for(Document, Document.project_id, m.id).label('documents_count'),
            count_for(Report, Report.project_id, m.id).label('reports_count'),
            count_for(Job, Job.project_id, m.id).label('jobs_count'),
            select(func.coalesce(func.sum(UploadedFile.file_size), 0)).where(UploadedFile.project_id == m.id).correlate(m).scalar_subquery().label('storage_bytes')]
        stmt = select(*columns).outerjoin(User, User.id == m.user_id)
        user_col, project_col, name_col = m.user_id, m.id, m.name
    elif kind in ('documents', 'storage'):
        m = Document if kind == 'documents' else UploadedFile
        columns = [m.id, m.project_id, Project.user_id, owner, m.created_at]
        if kind == 'documents':
            columns += [m.title, m.document_type, m.file_id, m.token_count, UploadedFile.file_type, UploadedFile.file_size, UploadedFile.is_parsed]
        else:
            columns += [m.original_name, m.file_type, m.file_size, m.is_parsed]
        stmt = select(*columns).outerjoin(Project, Project.id == m.project_id).outerjoin(User, User.id == Project.user_id)
        if kind == 'documents':
            stmt = stmt.outerjoin(UploadedFile, UploadedFile.id == m.file_id)
        user_col, project_col = Project.user_id, m.project_id
        name_col = m.title if kind == 'documents' else m.original_name
    elif kind == 'templates':
        m = Template
        stmt = select(m.id, m.name, m.category, m.user_id, owner, m.is_system, m.is_public, m.visibility,
            m.usage_count, m.created_at, m.updated_at,
            select(func.max(TemplateVersion.version_number)).where(TemplateVersion.template_id == m.id).correlate(m).scalar_subquery().label('version')
        ).outerjoin(User, User.id == m.user_id)
        user_col, project_col, name_col = m.user_id, None, m.name
    else:
        raise HTTPException(404, 'Unknown resource')
    created = m.created_at
    if filters.get('from_'):
        stmt = stmt.where(created >= filters['from_'])
    if filters.get('to'):
        stmt = stmt.where(created < filters['to'])
    if filters.get('search'):
        term = '%' + filters['search'].replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        parts = [name_col.ilike(term, escape='\\'), m.id.ilike(term, escape='\\')]
        parts.append(User.email.ilike(term, escape='\\'))
        stmt = stmt.where(or_(*parts))
    for key, column in [('user_id', user_col), ('project_id', project_col)]:
        if filters.get(key) and column is not None:
            stmt = stmt.where(column == filters[key])
    if filters.get('status'):
        status = filters['status']
        raise HTTPException(422, 'Status filter is unavailable for this resource')
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    sort = filters.get('sort') or 'created_at'
    sorts = {col.key: col for col in stmt.selected_columns}
    if sort not in sorts:
        raise HTTPException(422, 'Unsupported sort field')
    page, size = filters['page'], filters['page_size']
    stmt = stmt.order_by(sorts[sort].asc() if filters['order'] == 'asc' else sorts[sort].desc(), m.id.asc()).offset((page-1)*size).limit(size)
    items = [encode(row) for row in (await db.execute(stmt)).mappings().all()]
    for row in items:
        if kind == 'templates':
            row['allowed_actions'] = ['unpublish'] if row['is_public'] and not row['is_system'] else []
    result = dict(items=items, total=total, page=page, page_size=size)
    if kind == 'storage':
        # Same filter scope as table; recorded upload bytes, not physical disk usage.
        sub = stmt.order_by(None).limit(None).offset(None).subquery()
        agg = (await db.execute(select(func.coalesce(func.sum(sub.c.file_size),0), func.avg(sub.c.file_size)).select_from(sub))).one()
        result['summary'] = {'recorded_upload_bytes': agg[0], 'average_file_size': agg[1], 'orphaned_files': None,
            'note': 'Database upload records only. Physical orphan reconciliation and parsing failure telemetry are unavailable.'}
    return result


async def integrations(db, filters):
    stmt = select(AIUsageEvent.provider, func.count().label('requests'),
        func.sum(case((AIUsageEvent.status == 'failed', 1), else_=0)).label('failures'),
        func.avg(AIUsageEvent.latency_ms).label('average_latency_ms'), func.max(AIUsageEvent.created_at).label('last_observed_at'))
    if filters.get('from_'):
        stmt = stmt.where(AIUsageEvent.created_at >= filters['from_'])
    if filters.get('to'):
        stmt = stmt.where(AIUsageEvent.created_at < filters['to'])
    observed = {row['provider']: encode(row) for row in (await db.execute(stmt.group_by(AIUsageEvent.provider))).mappings()}
    from app.services.billing.billing_provider import billing_provider
    configs = [('payos','payment',billing_provider.configured,True),('local_storage','storage',os.path.isdir(settings.STORAGE_DIR),True),('email','email',False,False),('gemini', 'ai', bool(settings.GEMINI_API_KEY), True), ('openai', 'ai', bool(settings.OPENAI_API_KEY), True),
        ('anthropic', 'ai', bool(settings.ANTHROPIC_API_KEY), False),
        ('google_oauth', 'authentication', bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET), True),
        ('tavily', 'search', bool(settings.TAVILY_API_KEY), True), ('brave', 'search', bool(settings.BRAVE_SEARCH_API_KEY), True),
        ('serpapi', 'search', bool(settings.SERPAPI_API_KEY), True)]
    items = []
    for name, category, configured, supported in configs:
        observation = observed.get(name, {})
        items.append({'id': name, 'name': name, 'category': category, 'configured': configured, 'supported': supported,
            'status': 'unsupported' if not supported else ('configured' if configured else 'not_configured'),
            'health': None, 'health_note': 'No external connectivity probe. Usage observations do not establish live health.',
            'requests': observation.get('requests', 0), 'failures': observation.get('failures', 0),
            'average_latency_ms': observation.get('average_latency_ms'), 'last_observed_at': observation.get('last_observed_at')})
    if filters.get('search'):
        items = [i for i in items if filters['search'].lower() in i['name']]
    sort = filters.get('sort') or 'name'
    if sort not in {'name', 'category', 'status', 'requests', 'failures'}:
        raise HTTPException(422, 'Unsupported sort field')
    items.sort(key=lambda item: item[sort], reverse=filters['order'] == 'desc')
    page, size = filters['page'], filters['page_size']
    return {'items':items[(page-1)*size:page*size], 'total':len(items), 'page':page, 'page_size':size}


async def system_health(db):
    start = perf_counter()
    try:
        await db.execute(select(literal(1)))
        database = {'status':'healthy', 'latency_ms':round((perf_counter()-start)*1000, 2)}
    except Exception:
        await db.rollback()
        database = {'status':'unavailable', 'latency_ms':None, 'note':'Database probe failed.'}
    try:
        usage = shutil.disk_usage(settings.STORAGE_DIR)
        storage = {'status':'accessible' if os.access(settings.STORAGE_DIR, os.R_OK | os.W_OK) else 'unavailable',
            'filesystem_total_bytes':usage.total, 'filesystem_free_bytes':usage.free,
            'note':'Filesystem capacity containing storage; includes other applications.'}
    except OSError:
        storage = {'status':'unavailable', 'note':'Storage filesystem probe failed.'}
    from app.services.observability.metrics_collector import metrics_collector
    return {'checked_at': utc(datetime.now(timezone.utc)), 'api':{'status':'responding','scope':'current_process_since_start','metrics':metrics_collector.get_summary()}, 'database':database, 'storage':storage,
        'worker':{'status':'unavailable', 'note':'No distributed worker heartbeat is collected.'},
        'queue':{'status':'unavailable', 'note':'No external queue depth collector is configured.'}}


def ai_configuration():
    from app.services.ai.model_router import model_router
    return {'writable':False, 'note':'Defaults below are deployment-managed. Runtime overrides apply to new AIGateway calls only; explicit request model choices take precedence. Legacy direct provider calls are not changed.',
        'runtime_mode':settings.AI_RUNTIME_MODE, 'default_provider':settings.DEFAULT_AI_PROVIDER,
        'default_model':settings.DEFAULT_AI_MODEL,
        'routes':[{'task_type':task.value, 'primary_provider':route.primary_provider.value, 'primary_model':route.primary_model,
            'fallback_provider':route.fallback_provider.value, 'fallback_model':route.fallback_model} for task,route in model_router.ROUTING_MATRIX.items()],
        'pricing':[{'model':name, 'input_per_million_usd':price[0], 'output_per_million_usd':price[1]} for name,price in model_router.TOKEN_PRICING.items()],
        'pricing_note':'Current runtime estimation rates, not verified provider quotations or retroactive historical billing.'}


def system_settings():
    return {'writable':False, 'note':'Deployment settings below are read-only. Runtime registration settings apply to new accounts; existing plans are preserved.',
        'environment':settings.ENVIRONMENT, 'debug':settings.DEBUG, 'project_name':settings.PROJECT_NAME,
        'ai_runtime_mode':settings.AI_RUNTIME_MODE, 'search_provider':settings.SEARCH_PROVIDER,
        'access_token_expire_minutes':settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        'storage_backend':'local', 'database_backend':'sqlite' if settings.DATABASE_URL.startswith('sqlite') else 'postgresql'}

async def project_detail(db,project_id):
    from app.services.admin.query_service import usage_summary,job_dict
    if not await db.get(Project,project_id):raise HTTPException(404,'Không tìm thấy dự án.')
    f={'project_id':project_id,'page':1,'page_size':25,'order':'desc'}
    project=(await list_resources(db,'projects',f))['items'][0]
    documents=await list_resources(db,'documents',f)
    reports=(await db.execute(select(Report.id,Report.report_type,Report.status,Report.created_at).where(Report.project_id==project_id).order_by(Report.created_at.desc()).limit(25))).mappings().all()
    jobs=(await db.scalars(select(Job).where(Job.project_id==project_id).order_by(Job.created_at.desc()).limit(25))).all()
    return {'project':project,'usage':await usage_summary(db,[AIUsageEvent.project_id==project_id]),'documents':documents['items'],
        'reports':[encode(row) for row in reports],'jobs':[job_dict(row) for row in jobs],
        'note':'Metadata only. Usage is lifetime for this project. Recent lists are limited to 25 records.'}

async def validate_template(db,template):
    from pathlib import Path
    from zipfile import ZipFile,BadZipFile
    from lxml import etree
    version=await db.scalar(select(TemplateVersion).where(TemplateVersion.template_id==template.id).order_by(TemplateVersion.version_number.desc()).limit(1))
    if not version:
        return {'valid':False,'checks':[{'check':'version','valid':False,'message':'Mẫu chưa có phiên bản.'}]}
    if not version.file_path:
        valid=isinstance(version.schema_json,dict) and bool(version.schema_json)
        return {'valid':valid,'checks':[{'check':'schema','valid':valid,'message':'Mẫu dựa trên schema; không có file DOCX để kiểm tra.'}]}
    path=Path(version.file_path).resolve()
    if not path.is_relative_to(Path(settings.TEMPLATE_DIR).resolve()) or path.suffix.lower()!='.docx':
        return {'valid':False,'checks':[{'check':'format','valid':False,'message':'File không thuộc kho mẫu DOCX được hỗ trợ.'}]}
    try:
        with ZipFile(path) as doc:
            if sum(item.file_size for item in doc.infolist())>50*1024*1024:raise ValueError('size')
            for name in ['[Content_Types].xml','word/document.xml']:
                root=etree.fromstring(doc.read(name),parser=etree.XMLParser(resolve_entities=False,no_network=True,load_dtd=False))
                if root.getroottree().docinfo.doctype:raise ValueError("doctype")
            if doc.testzip():raise ValueError('crc')
        return {'valid':True,'checks':[{'check':'docx_structure','valid':True}],
            'note':'DOCX archive/XML validated. Semantic placeholder compatibility still requires template author review.'}
    except (OSError,BadZipFile,KeyError,ValueError,etree.XMLSyntaxError):
        return {'valid':False,'checks':[{'check':'docx_structure','valid':False,'message':'File thiếu, hỏng hoặc XML không hợp lệ.'}]}
