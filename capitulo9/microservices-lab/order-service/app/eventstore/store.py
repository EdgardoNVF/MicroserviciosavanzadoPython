import hashlib
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.domain.order_aggregate import OrderAggregate
from app.domain.events import decode_event,OrderCreated
from app.eventstore.models import EventRecord,SnapshotOrder,OutboxRecord
from app.eventstore.projections import ProjectionEngine,REBUILD_LOCK
from shared.events import OrderCreated as IntegrationOrderCreated,RequestedItem

class VersionConflict(Exception):pass

class EventStore:
    def __init__(self,url,snapshot_threshold=10):
        self.engine=create_async_engine(url,pool_pre_ping=True)
        self.sessions=async_sessionmaker(self.engine,expire_on_commit=False)
        self.snapshot_threshold=snapshot_threshold

    async def load_in_session(self,session,aggregate_id,use_snapshot=True):
        snapshot=await session.get(SnapshotOrder,aggregate_id) if use_snapshot else None
        aggregate=OrderAggregate.from_snapshot(snapshot.state,snapshot.aggregate_version) if snapshot else OrderAggregate()
        rows=(await session.scalars(select(EventRecord).where(
            EventRecord.aggregate_id==aggregate_id,EventRecord.aggregate_version>aggregate.version
            ).order_by(EventRecord.aggregate_version))).all()
        for record in rows:
            if record.aggregate_version != aggregate.version+1:raise ValueError('Secuencia de eventos incompleta')
            aggregate.apply(decode_event(record.event_type,record.payload))
        return aggregate

    async def load(self,aggregate_id,use_snapshot=True):
        # One coherent read transaction for snapshot + tail.
        async with self.engine.connect() as connection:
            connection=await connection.execution_options(isolation_level='REPEATABLE READ')
            async with connection.begin():
                async with self.sessions(bind=connection) as session:
                    return await self.load_in_session(session,aggregate_id,use_snapshot)

    async def append_events(self,aggregate_id,events,expected_version):
        if not events:raise ValueError('El lote de eventos no puede estar vacío')
        lock_key=int.from_bytes(hashlib.blake2b(aggregate_id.bytes,digest_size=8).digest(),'big',signed=True)
        async with self.sessions() as session,session.begin():
            await session.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'),{'key':REBUILD_LOCK})
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':lock_key})
            current=(await session.scalar(select(func.max(EventRecord.aggregate_version)).where(
                EventRecord.aggregate_id==aggregate_id))) or 0
            if expected_version != current:raise VersionConflict(f'Esperada {expected_version}; actual {current}')
            aggregate=await self.load_in_session(session,aggregate_id)
            if aggregate.version != current:raise ValueError('Snapshot o historial inconsistente')
            for event in events:
                if event.aggregate_id != aggregate_id:raise ValueError('Evento de otro agregado')
                aggregate.apply(event)
                record=EventRecord(event_id=event.event_id,event_type=event.event_type,
                    aggregate_id=aggregate_id,aggregate_type='Order',aggregate_version=aggregate.version,
                    occurred_at=event.timestamp,payload=event.model_dump(mode='json'),metadata_={
                        'correlation_id':str(event.correlation_id),'causation_id':str(event.causation_id) if event.causation_id else None,
                        'source_service':event.source_service,'event_version':event.event_version})
                session.add(record);await session.flush()
                await ProjectionEngine.apply(session,record,aggregate)
                # Snapshot at each boundary, even if one batch crosses 10/20/etc.
                if aggregate.version % self.snapshot_threshold == 0:
                    snapshot=await session.get(SnapshotOrder,aggregate_id)
                    if snapshot is None:
                        snapshot=SnapshotOrder(aggregate_id=aggregate_id);session.add(snapshot)
                    snapshot.aggregate_version=aggregate.version;snapshot.state=aggregate.snapshot()
                    snapshot.created_at=event.timestamp
                audit={**event.model_dump(mode='json'),'aggregate_version':aggregate.version}
                session.add(OutboxRecord(event_id=event.event_id,order_id=aggregate_id,
                    aggregate_version=aggregate.version,topic='order-events',payload=audit))
                if isinstance(event,OrderCreated):
                    integration=IntegrationOrderCreated(event_id=event.event_id,timestamp=event.timestamp,
                        correlation_id=event.correlation_id,order_id=aggregate_id,customer_id=event.customer_id,
                        items=[RequestedItem(product_id=i.product_id,quantity=i.quantity) for i in event.items])
                    session.add(OutboxRecord(event_id=event.event_id,order_id=aggregate_id,
                        aggregate_version=aggregate.version,topic='orders.created',payload=integration.model_dump(mode='json')))
            await session.flush()
            return aggregate
