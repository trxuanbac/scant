"""Legacy workbook helper retained for Alembic adoption compatibility."""
from app.models.workbook_action import WorkbookAction


def upgrade(connection):
    WorkbookAction.__table__.create(connection, checkfirst=True)


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


if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
