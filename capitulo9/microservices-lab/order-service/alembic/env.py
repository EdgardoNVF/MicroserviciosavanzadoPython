import asyncio,os
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool
from app.eventstore.models import Base
from app.config import Settings

url=os.getenv('EVENTSTORE_ADMIN_DATABASE_URL',Settings().database_url)

def configure(connection=None):
    options=dict(target_metadata=Base.metadata,compare_type=True)
    if connection is None:options.update(url=url,literal_binds=True,dialect_opts={'paramstyle':'named'})
    else:options['connection']=connection
    context.configure(**options)
    with context.begin_transaction():context.run_migrations()

async def online():
    engine=create_async_engine(url,poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:await connection.run_sync(configure)
    finally:await engine.dispose()

if context.is_offline_mode():configure()
else:asyncio.run(online())
