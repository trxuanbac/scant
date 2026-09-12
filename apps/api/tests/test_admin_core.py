import pytest
import pytest_asyncio
from sqlalchemy import select
from datetime import datetime, timezone
from app.core.security import create_access_token
from app.models.entities import User, AIUsageEvent, AuditLog, UserQuota, Project

@pytest_asyncio.fixture
async def ctx(client, test_session_factory):
    async with test_session_factory() as db:
        for uid, role, su in [('user','user',False),('admin','admin',False),('root','admin',True)]:
            db.add(User(id=uid,name=uid,email=f'{uid}@example.test',role=role,is_superuser=su,plan='free'))
        await db.commit()
    yield client, test_session_factory

def auth(uid):
    return {'Authorization': f'Bearer {create_access_token(subject=uid)}'}

@pytest.mark.asyncio
async def test_role_matrix(ctx):
    c,_=ctx
    assert (await c.get('/api/v1/admin/session')).status_code == 401
    assert (await c.get('/api/v1/admin/session',headers=auth('user'))).status_code == 403
    for uid in ['admin','root']:
        assert (await c.get('/api/v1/admin/session',headers=auth(uid))).status_code == 200
    assert (await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'role':'admin','reason':'Grant permission'})).status_code == 403

@pytest.mark.asyncio
async def test_lock_and_audit_transaction(ctx):
    c,f=ctx
    res=await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'is_active':False,'reason':'Account support investigation'})
    assert res.status_code == 200, res.text
    assert (await c.get('/api/v1/auth/me',headers=auth('user'))).status_code in [400,403]
    assert (await c.post('/api/v1/data/preview-upload',headers=auth('user'))).status_code in [400,403]
    async with f() as db:
        entry=(await db.execute(select(AuditLog).where(AuditLog.action=='USER_LOCK'))).scalar_one()
        assert entry.user_id=='admin'
        assert entry.details_json['before']['is_active'] is True
        assert entry.details_json['after']['is_active'] is False
        assert entry.details_json['reason']=='Account support investigation'
    assert (await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'is_active':True})).status_code==422

@pytest.mark.asyncio
async def test_plan_validates_syncs_quota_without_reset(ctx):
    c,f=ctx
    async with f() as db:
        db.add(UserQuota(user_id='user',tokens_used_this_month=12,cost_usd_this_month=0.01))
        await db.commit()
    assert (await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'plan':'invented','reason':'Invalid plan'})).status_code==422
    res=await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'plan':'pro','reason':'Support upgrade'})
    assert res.status_code==200,res.text
    async with f() as db:
        q=(await db.execute(select(UserQuota).where(UserQuota.user_id=='user'))).scalar_one()
        assert q.monthly_token_limit==2500000
        assert q.tokens_used_this_month==12

@pytest.mark.asyncio
async def test_filtered_usage_real_cost_and_pagination(ctx):
    c,f=ctx
    async with f() as db:
        for month,cost in [(7,99),(8,2)]:
            db.add(AIUsageEvent(user_id='user',task_type='research',provider='test',model='test',total_tokens=10,estimated_cost_usd=cost,created_at=datetime(2026,month,15,tzinfo=timezone.utc)))
        await db.commit()
    res=await c.get('/api/v1/admin/usage?from=2026-08-01&to=2026-09-01',headers=auth('admin'))
    assert res.status_code==200,res.text
    assert res.json()['summary']['estimated_cost_usd']==2
    users=await c.get('/api/v1/admin/users?page=2&page_size=2',headers=auth('admin'))
    assert users.json()['total']==3
    assert len(users.json()['items'])==1
    assert (await c.get('/api/v1/admin/users?page_size=9999',headers=auth('admin'))).status_code==422
    assert (await c.get('/api/v1/admin/usage?from=2026-09-01&to=2026-08-01',headers=auth('admin'))).status_code==422

@pytest.mark.asyncio
async def test_stale_quota_identity_cannot_erase_new_month_usage(ctx):
    from app.services.usage.quota_engine import quota_engine
    c,f=ctx
    async with f() as db:
        db.add(UserQuota(user_id='user',tokens_used_this_month=999,reset_at=datetime(2026,1,1,tzinfo=timezone.utc)))
        await db.commit()
    async with f() as stale:
        original=await stale.scalar(select(UserQuota).where(UserQuota.user_id=='user'))
        async with f() as writer:
            q=await quota_engine.get_or_create_user_quota(writer,'user')
            q.tokens_used_this_month=100
            await writer.commit()
        refreshed=await quota_engine.get_or_create_user_quota(stale,'user')
        assert refreshed is original
        assert refreshed.tokens_used_this_month==100
        await stale.commit()

@pytest.mark.asyncio
async def test_locked_google_account_cannot_link_or_login(ctx,monkeypatch):
    from app.services.auth.google_auth_service import GoogleUserInfo
    from unittest.mock import AsyncMock
    c,f=ctx
    await c.patch('/api/v1/admin/users/user',headers=auth('admin'),json={'is_active':False,'reason':'Account investigation'})
    monkeypatch.setattr('app.services.auth.google_auth_service.google_auth_service.verify_id_token',AsyncMock(return_value=(True,GoogleUserInfo(google_sub='new-google-sub',email='user@example.test',email_verified=True,name='User'),None)))
    res=await c.post('/api/v1/auth/google',json={'credential':'test-credential'})
    assert res.status_code==403,res.text
    async with f() as db:assert (await db.get(User,'user')).google_sub is None

@pytest.mark.asyncio
async def test_iso_offsets_are_normalized_before_sqlite_filter(ctx):
    c,f=ctx
    async with f() as db:
        db.add(AIUsageEvent(user_id='user',task_type='test',provider='test',model='test',total_tokens=4,created_at=datetime(2026,8,15,tzinfo=timezone.utc)))
        await db.commit()
    result=await c.get('/api/v1/admin/usage',params={'from':'2026-08-15T07:00:00+07:00','to':'2026-08-16'},headers=auth('admin'))
    assert result.status_code==200,result.text
    assert result.json()['summary']['total_tokens']==4
    payments=await c.get('/api/v1/admin/payments',params={'from':'2026-08-15T07:00:00+07:00','to':'2026-08-16'},headers=auth('admin'))
    assert payments.status_code==200,payments.text
