from functools import lru_cache
import io
import json
import openpyxl
import pytest
from test_admin_core import ctx, auth


@lru_cache
def workbook(value=10):
    wb=openpyxl.Workbook();wb.active.title='Lương';wb.active.append(['Salary']);wb.active.append([value])
    out=io.BytesIO();wb.save(out);wb.close();return out.getvalue()

async def preview(c,value=10,cells=None):
    return await c.post('/api/v1/data/workbook-actions/preview',headers=auth('user'),files={'file':('payroll.xlsx',workbook(value))},data={'source_key':'payroll','action':json.dumps({'type':'HIGHLIGHT_CELLS','sheet':'Lương','cells':cells or ['A2'],'color':'#FFFF00'})})

@pytest.mark.asyncio
async def test_preview_confirm_history_and_undo_are_durable_and_owned(ctx):
    c,_=ctx
    response=await preview(c);assert response.status_code==200,response.text
    action=response.json();assert action['status']=='pending';assert action['preview'][0]['value']==10
    assert action['action']['color']=='#FFFF00'
    for _ in range(2):
        result=await c.post(f"/api/v1/data/workbook-actions/{action['id']}/confirm",headers=auth('user'),files={'file':('payroll.xlsx',workbook())})
        assert result.status_code==200,result.text
    history=await c.get('/api/v1/data/workbook-actions/history',headers=auth('user'),params={'source_key':'payroll','source_hash':action['source_hash']})
    assert len(history.json()['layers'])==1
    assert (await c.post(f"/api/v1/data/workbook-actions/{action['id']}/undo",headers=auth('admin'))).status_code==404
    undo=await c.post(f"/api/v1/data/workbook-actions/{action['id']}/undo",headers=auth('user'))
    assert undo.status_code==200,undo.text
    history=await c.get('/api/v1/data/workbook-actions/history',headers=auth('user'),params={'source_key':'payroll','source_hash':action['source_hash']})
    assert history.json()['layers']==[]
    assert history.json()['items'][0]['status']=='undone'

@pytest.mark.asyncio
async def test_changed_workbook_and_stale_preview_are_rejected(ctx):
    c,_=ctx
    first=(await preview(c)).json();second=(await preview(c)).json()
    url=f"/api/v1/data/workbook-actions/{first['id']}/confirm"
    assert (await c.post(url,headers=auth('user'),files={'file':('payroll.xlsx',workbook(99))})).status_code==409
    assert (await c.post(url,headers=auth('user'),files={'file':('payroll.xlsx',workbook())})).status_code==200
    assert (await c.post(f"/api/v1/data/workbook-actions/{second['id']}/confirm",headers=auth('user'),files={'file':('payroll.xlsx',workbook())})).status_code==409

@pytest.mark.asyncio
async def test_cancel_prevents_confirm_and_invalid_range_rejected(ctx):
    c,_=ctx
    assert (await preview(c,cells=['A0'])).status_code==422
    action=(await preview(c)).json()
    assert (await c.post(f"/api/v1/data/workbook-actions/{action['id']}/cancel",headers=auth('user'))).status_code==200
    assert (await c.post(f"/api/v1/data/workbook-actions/{action['id']}/confirm",headers=auth('user'),files={'file':('payroll.xlsx',workbook())})).status_code==409
    assert (await c.get('/api/v1/data/workbook-actions/history',params={'source_key':'payroll','source_hash':action['source_hash']})).status_code==401

@pytest.mark.asyncio
async def test_clear_undo_restores_previous_layers_and_audit(ctx):
    from sqlalchemy import select
    from app.models.entities import AuditLog
    c,f=ctx
    first=(await preview(c)).json()
    await c.post(f"/api/v1/data/workbook-actions/{first['id']}/confirm",headers=auth('user'),files={'file':('payroll.xlsx',workbook())})
    clear=await c.post('/api/v1/data/workbook-actions/preview',headers=auth('user'),files={'file':('payroll.xlsx',workbook())},data={'source_key':'payroll','action':json.dumps({'type':'CLEAR_HIGHLIGHTS','sheet':'Lương'})})
    item=clear.json()
    assert (await c.post(f"/api/v1/data/workbook-actions/{item['id']}/confirm",headers=auth('user'),files={'file':('payroll.xlsx',workbook())})).status_code==200
    params={'source_key':'payroll','source_hash':item['source_hash']}
    assert (await c.get('/api/v1/data/workbook-actions/history',headers=auth('user'),params=params)).json()['layers']==[]
    assert (await c.post(f"/api/v1/data/workbook-actions/{first['id']}/undo",headers=auth('user'))).status_code==409
    assert (await c.post(f"/api/v1/data/workbook-actions/{item['id']}/undo",headers=auth('user'))).status_code==200
    assert len((await c.get('/api/v1/data/workbook-actions/history',headers=auth('user'),params=params)).json()['layers'])==1
    async with f() as db:
        events=(await db.scalars(select(AuditLog).where(AuditLog.resource_type=='workbook_layer'))).all()
        assert len(events)==5
        assert all(event.details_json['target']=='scant_display' for event in events)

@pytest.mark.asyncio
async def test_additive_migration_can_repeat_without_data_loss(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import inspect, text
    from app.models.entities import User
    from app.migrations.workbook_actions import upgrade
    engine=create_async_engine(f'sqlite+aiosqlite:///{tmp_path / "migration.sqlite"}')
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: User.__table__.create(conn))
        await connection.execute(text("CREATE TABLE existing_data (value TEXT)"))
        await connection.execute(text("INSERT INTO existing_data VALUES ('preserved')"))
        await connection.run_sync(upgrade)
        await connection.run_sync(upgrade)
        assert 'workbook_actions' in await connection.run_sync(lambda conn: inspect(conn).get_table_names())
        assert (await connection.execute(text('SELECT value FROM existing_data'))).scalar_one()=='preserved'
    await engine.dispose()

@pytest.mark.asyncio
async def test_legacy_undo_requires_authentication(ctx):
    c,_=ctx
    assert (await c.post('/api/v1/data/action-undo',data={'session_id':'default'})).status_code==401


@pytest.mark.asyncio
async def test_source_endpoint_returns_the_complete_version_identity(ctx):
    c, _ = ctx
    response = await c.post(
        '/api/v1/data/workbook-actions/source',
        headers=auth('user'),
        files={'file': ('payroll.xlsx', workbook())},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['source_hash'] == body['source_version']['version']
    assert body['source_version']['source_kind'] == 'upload'
    assert body['source_version']['display_name'] == 'payroll.xlsx'

@pytest.mark.asyncio
async def test_records_survive_database_engine_restart(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
    from sqlalchemy import select
    from app.core.database import Base
    from app.models.entities import User
    from app.models.workbook_action import WorkbookAction
    url=f'sqlite+aiosqlite:///{tmp_path / "durable.sqlite"}'
    engine=create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine,expire_on_commit=False)() as db:
        db.add(User(id='owner',email='owner@example.com',name='Owner'))
        await db.flush()
        db.add(WorkbookAction(id='action',user_id='owner',source_key='a'*64,source_hash='b'*64,base_revision='c'*64,status='applied',payload_json={'type':'HIGHLIGHT_CELLS','sheet':'Sheet','cells':['A1'],'color':'FFFF00'},preview_json=[]))
        await db.commit()
    await engine.dispose()
    reopened=create_async_engine(url)
    async with async_sessionmaker(reopened)() as db:
        item=await db.scalar(select(WorkbookAction).where(WorkbookAction.id=='action'))
        assert item.status=='applied'
        assert item.payload_json['cells']==['A1']
    await reopened.dispose()
