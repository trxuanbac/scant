import pytest
from test_admin_core import ctx, auth
from app.models.entities import Project, Document, UploadedFile, Template, AIUsageEvent
from sqlalchemy import select

@pytest.mark.asyncio
async def test_metadata_and_operational_routes(ctx):
    c,f=ctx
    async with f() as db:
        db.add(Project(id='p',user_id='user',name='Test Project'))
        await db.flush()
        db.add(Document(id='d',project_id='p',title='Quarterly document',content_text='PRIVATE CONTENT NEVER LEAK',content_json={'private':'PRIVATE CONTENT NEVER LEAK'}))
        db.add(Template(id='t',user_id='user',name='User private template',is_public=False,is_system=False,visibility='my'))
        await db.commit()
    for path in ['projects','documents','storage','templates','integrations','system/health','plans','payments','billing']:
        assert (await c.get('/api/v1/admin/'+path,headers=auth('user'))).status_code==403
        res=await c.get('/api/v1/admin/'+path,headers=auth('admin'))
        assert res.status_code==200,(path,res.text)
        assert 'PRIVATE CONTENT NEVER LEAK' not in res.text
    for path in ['ai-config','providers','settings']:
        assert (await c.get('/api/v1/admin/'+path,headers=auth('admin'))).status_code==403
        res=await c.get('/api/v1/admin/'+path,headers=auth('root'))
        assert res.status_code==200,(path,res.text)
        assert 'api_key' not in res.text.lower()
    assert (await c.post('/api/v1/admin/templates/t/publish',headers=auth('root'),json={'reason':'Publish private data'})).status_code==403

@pytest.mark.asyncio
async def test_overview_empty_is_real_and_time_bounded(ctx):
    c,_=ctx
    res=await c.get('/api/v1/admin/overview',headers=auth('admin'))
    assert res.status_code==200,res.text
    metrics={m['key']:m for m in res.json()['metrics']}
    assert metrics['active_users']['value']==0
    assert metrics['total_users']['value']==3
    assert metrics['storage']['value']==0
    assert metrics['cost']['value']==0
    assert 'providers_health' not in res.json()

@pytest.mark.asyncio
async def test_job_action_guards_and_redaction(ctx):
    from app.models.entities import Job
    c,f=ctx
    async with f() as db:
        db.add(Job(id='job',job_type='generation',project_id='p',status='running',metadata_json={'report_id':'r'},error_message='secret=mustnotleak PRIVATE CONTENT',payload_json={'prompt':'PRIVATE CONTENT'}))
        await db.commit()
    detail=await c.get('/api/v1/admin/jobs/job',headers=auth('admin'))
    assert detail.status_code==200
    assert 'mustnotleak' not in detail.text and 'PRIVATE CONTENT' not in detail.text
    assert (await c.post('/api/v1/admin/jobs/job/retry',headers=auth('admin'),json={'reason':'Try again'})).status_code==409
    assert (await c.post('/api/v1/admin/jobs/job/cancel',headers=auth('admin'),json={'reason':'Stop runaway job'})).status_code==200
    assert (await c.post('/api/v1/admin/jobs/job/cancel',headers=auth('admin'),json={'reason':'Duplicate cancel'})).status_code==409

@pytest.mark.asyncio
async def test_project_detail_and_template_validation(ctx):
    from app.models.entities import Project,Template,TemplateVersion,AuditLog
    from sqlalchemy import select
    c,f=ctx
    async with f() as db:
        db.add(Project(id='detail-project',user_id='user',name='Project'))
        db.add(Template(id='system-template',name='System template',is_system=True,is_public=False))
        await db.commit()
    res=await c.get('/api/v1/admin/projects/detail-project',headers=auth('admin'))
    assert res.status_code==200,res.text
    assert res.json()['project']['documents_count']==0
    assert (await c.get('/api/v1/admin/projects/missing',headers=auth('admin'))).status_code==404
    url='/api/v1/admin/templates/system-template'
    assert not (await c.get(url+'/validation',headers=auth('admin'))).json()['valid']
    assert (await c.post(url+'/publish',headers=auth('root'),json={'reason':'Reviewed system template'})).status_code==422
    async with f() as db:
        db.add(TemplateVersion(template_id='system-template',schema_json={'sections':[{'title':'Summary'}]}))
        await db.commit()
    assert (await c.post(url+'/publish',headers=auth('root'),json={'reason':'Reviewed system template'})).status_code==200
    async with f() as db:
        assert len((await db.scalars(select(AuditLog).where(AuditLog.action=='TEMPLATE_PUBLISH'))).all())==1
