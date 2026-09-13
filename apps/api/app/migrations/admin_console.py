"""Legacy admin helpers retained for the Alembic adoption revision.

Back up the database first. Run before rolling out admin-enabled API workers.
Existing account plans and existing quota overrides are preserved.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from sqlalchemy import Index, select, func, inspect, MetaData, insert, text
from app.core.database import engine
from app.models.entities import User, UserQuota, AIUsageEvent, Job, AuditLog, Project, UploadedFile
from app.models.admin_billing import Payment, Subscription
from app.models.admin_configuration import AdminConfiguration
from app.services.billing.plan_definitions import PLANS

INDEXES=[
    Index('ix_admin_users_created',User.created_at),
    Index('ix_admin_usage_user_date',AIUsageEvent.user_id,AIUsageEvent.created_at),
    Index('ix_admin_usage_date',AIUsageEvent.created_at),
    Index('ix_admin_jobs_status_date',Job.status,Job.created_at),
    Index('ix_admin_jobs_project_date',Job.project_id,Job.created_at),
    Index('ix_admin_audit_target_date',AuditLog.resource_id,AuditLog.created_at),
    Index('ix_admin_audit_date',AuditLog.created_at),
    Index('ix_admin_projects_user_date',Project.user_id,Project.created_at),
    Index('ix_admin_files_project',UploadedFile.project_id),
    Index('ix_admin_payments_date',Payment.created_at),
]


def create_admin_indexes(connection):
    """Create the shared query indexes on an existing schema."""
    for index in INDEXES:
        index.create(connection, checkfirst=True)


def drop_admin_indexes(connection):
    """Remove shared query indexes during an Alembic downgrade."""
    for index in reversed(INDEXES):
        index.drop(connection, checkfirst=True)


def backfill_missing_quotas(connection, *, now=None):
    """Create quotas only for users that do not already have an override."""
    now = now or datetime.now(timezone.utc)
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    reset_at = datetime(
        now.year + (now.month == 12),
        1 if now.month == 12 else now.month + 1,
        1,
        tzinfo=timezone.utc,
    )
    users = connection.execute(
        select(User.id, User.plan)
        .outerjoin(UserQuota, UserQuota.user_id == User.id)
        .where(UserQuota.id.is_(None))
    ).all()
    if not users:
        return 0
    user_ids = [user_id for user_id, _plan in users]
    usage = connection.execute(
        select(
            AIUsageEvent.user_id,
            func.sum(AIUsageEvent.total_tokens),
            func.sum(AIUsageEvent.estimated_cost_usd),
        )
        .where(
            AIUsageEvent.user_id.in_(user_ids),
            AIUsageEvent.created_at >= month,
        )
        .group_by(AIUsageEvent.user_id)
    ).all()
    totals = {user_id: (tokens, cost) for user_id, tokens, cost in usage}
    rows = []
    for user_id, plan_name in users:
        plan = PLANS.get(plan_name, PLANS["free"])
        tokens, cost = totals.get(user_id, (0, 0))
        rows.append(
            {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "monthly_token_limit": plan.monthly_tokens_limit,
                "monthly_cost_limit_usd": plan.monthly_ai_budget_usd,
                "tokens_used_this_month": tokens or 0,
                "cost_usd_this_month": cost or 0,
                "reset_at": reset_at,
                "created_at": now,
                "updated_at": now,
            }
        )
    connection.execute(insert(UserQuota), rows)
    return len(rows)

def upgrade_subscription_grants(connection):
    columns=inspect(connection).get_columns('billing_subscriptions')
    if next(column for column in columns if column['name']=='payment_id')['nullable']:
        return
    if connection.dialect.name=='postgresql':
        connection.execute(text('ALTER TABLE billing_subscriptions ALTER COLUMN payment_id DROP NOT NULL'))
        return
    if connection.dialect.name!='sqlite':
        raise RuntimeError('Subscription nullable migration supports PostgreSQL and SQLite only')
    # Upgrade a pre-release admin schema without dropping subscription records.
    metadata=MetaData()
    User.__table__.to_metadata(metadata)
    Payment.__table__.to_metadata(metadata)
    temporary=Subscription.__table__.to_metadata(metadata,name='billing_subscriptions_next')
    temporary.indexes.clear()
    temporary.drop(connection,checkfirst=True)
    temporary.create(connection)
    names=[column.name for column in Subscription.__table__.columns]
    connection.execute(insert(temporary).from_select(names,select(*Subscription.__table__.columns)))
    Subscription.__table__.drop(connection)
    connection.execute(text('ALTER TABLE billing_subscriptions_next RENAME TO billing_subscriptions'))
    for index in Subscription.__table__.indexes:index.create(connection,checkfirst=True)


async def migrate(bind=engine):
    async with bind.begin() as conn:
        for table in [Payment.__table__,Subscription.__table__,AdminConfiguration.__table__]:
            await conn.run_sync(lambda connection,t=table:t.create(connection,checkfirst=True))
        await conn.run_sync(upgrade_subscription_grants)
        await conn.run_sync(create_admin_indexes)
        created = await conn.run_sync(backfill_missing_quotas)
    return {'quota_rows_created':created,'tables_checked':3,'indexes_checked':len(INDEXES)}


async def main():
    from app.core.config import settings
    from app.migrations.runner import bootstrap_database

    result = await bootstrap_database(settings.DATABASE_URL)
    print(
        {
            "initial_state": result.initial_state,
            "initial_revision": result.initial_revision,
            "final_revision": result.final_revision,
            "upgraded": result.upgraded,
        }
    )
    return result


if __name__=='__main__':
    asyncio.run(main())
