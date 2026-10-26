"""Esquema inicial fijo; no importa los modelos vivos de la aplicación."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql as pg
revision='001_eventstore'
down_revision=None
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('events',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('event_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('event_type',sa.String(100),nullable=False),
        sa.Column('aggregate_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('aggregate_type',sa.String(50),nullable=False),
        sa.Column('aggregate_version',sa.Integer(),nullable=False),
        sa.Column('occurred_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('payload',pg.JSONB(),nullable=False),sa.Column('metadata',pg.JSONB(),nullable=False),
        sa.UniqueConstraint('event_id',name='uq_event_id'),
        sa.UniqueConstraint('aggregate_id','aggregate_version',name='uq_aggregate_version'),
        sa.CheckConstraint('aggregate_version>0',name='ck_event_version_positive'))
    op.create_table('order_projections',
        sa.Column('order_id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('customer_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('status',sa.String(30),nullable=False),sa.Column('items',pg.JSONB(),nullable=False),
        sa.Column('total_amount',sa.Numeric(20,2),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('event_count',sa.Integer(),nullable=False),sa.Column('last_event_id',sa.BigInteger(),nullable=False))
    op.create_table('snapshot_orders',
        sa.Column('aggregate_id',pg.UUID(as_uuid=True),primary_key=True),
        sa.Column('aggregate_version',sa.Integer(),nullable=False),sa.Column('state',pg.JSONB(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_table('outbox',
        sa.Column('id',sa.BigInteger(),primary_key=True,autoincrement=True),
        sa.Column('event_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('order_id',pg.UUID(as_uuid=True),nullable=False),
        sa.Column('aggregate_version',sa.Integer(),nullable=False),sa.Column('topic',sa.String(100),nullable=False),
        sa.Column('payload',pg.JSONB(),nullable=False),sa.Column('sent_at',sa.DateTime(timezone=True),nullable=True),
        sa.UniqueConstraint('event_id','topic',name='uq_outbox_event_topic'))

def downgrade():
    for table in ['outbox','snapshot_orders','order_projections','events']:op.drop_table(table)
