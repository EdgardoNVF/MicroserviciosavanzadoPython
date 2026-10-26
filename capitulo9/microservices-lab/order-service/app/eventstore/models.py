from sqlalchemy import BigInteger,Integer,String,DateTime,Numeric,UniqueConstraint,CheckConstraint
from sqlalchemy.dialects.postgresql import UUID,JSONB
from sqlalchemy.orm import DeclarativeBase,mapped_column

class Base(DeclarativeBase):pass

class EventRecord(Base):
    __tablename__='events'
    id=mapped_column(BigInteger,primary_key=True,autoincrement=True)
    event_id=mapped_column(UUID(as_uuid=True),unique=True,nullable=False)
    event_type=mapped_column(String(100),nullable=False)
    aggregate_id=mapped_column(UUID(as_uuid=True),nullable=False)
    aggregate_type=mapped_column(String(50),nullable=False)
    aggregate_version=mapped_column(Integer,nullable=False)
    occurred_at=mapped_column(DateTime(timezone=True),nullable=False)
    payload=mapped_column(JSONB,nullable=False)
    metadata_=mapped_column('metadata',JSONB,nullable=False)
    __table_args__=(UniqueConstraint('aggregate_id','aggregate_version',name='uq_aggregate_version'),
                   CheckConstraint('aggregate_version > 0',name='ck_event_version_positive'))

class OrderProjection(Base):
    __tablename__='order_projections'
    order_id=mapped_column(UUID(as_uuid=True),primary_key=True)
    customer_id=mapped_column(UUID(as_uuid=True),nullable=False)
    status=mapped_column(String(30),nullable=False)
    items=mapped_column(JSONB,nullable=False)
    total_amount=mapped_column(Numeric(20,2),nullable=False)
    created_at=mapped_column(DateTime(timezone=True),nullable=False)
    updated_at=mapped_column(DateTime(timezone=True),nullable=False)
    event_count=mapped_column(Integer,nullable=False)
    last_event_id=mapped_column(BigInteger,nullable=False)

class SnapshotOrder(Base):
    __tablename__='snapshot_orders'
    aggregate_id=mapped_column(UUID(as_uuid=True),primary_key=True)
    aggregate_version=mapped_column(Integer,nullable=False)
    state=mapped_column(JSONB,nullable=False)
    created_at=mapped_column(DateTime(timezone=True),nullable=False)

class OutboxRecord(Base):
    __tablename__='outbox'
    id=mapped_column(BigInteger,primary_key=True,autoincrement=True)
    event_id=mapped_column(UUID(as_uuid=True),nullable=False)
    order_id=mapped_column(UUID(as_uuid=True),nullable=False)
    aggregate_version=mapped_column(Integer,nullable=False)
    topic=mapped_column(String(100),nullable=False)
    payload=mapped_column(JSONB,nullable=False)
    sent_at=mapped_column(DateTime(timezone=True),nullable=True)
    __table_args__=(UniqueConstraint('event_id','topic',name='uq_outbox_event_topic'),)
