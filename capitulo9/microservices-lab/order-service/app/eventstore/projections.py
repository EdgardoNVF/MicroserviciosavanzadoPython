from sqlalchemy import select,delete,text
from app.eventstore.models import EventRecord,OrderProjection
from app.domain.events import decode_event
from app.domain.order_aggregate import OrderAggregate
from app.queries.order_queries import response_from_order

REBUILD_LOCK=93003001

class ProjectionEngine:
    def __init__(self,sessions):self.sessions=sessions
    @staticmethod
    async def apply(session,record,aggregate):
        response=response_from_order(aggregate.order)
        row=await session.get(OrderProjection,aggregate.order.id)
        if row is None:
            row=OrderProjection(order_id=aggregate.order.id);session.add(row)
        row.customer_id=aggregate.order.customer_id;row.status=aggregate.order.status.value
        row.items=[i.model_dump(mode='json') for i in response.items]
        row.total_amount=aggregate.order.total;row.created_at=aggregate.order.created_at
        row.updated_at=record.occurred_at;row.event_count=aggregate.version;row.last_event_id=record.id
        await session.flush()

    async def rebuild_all(self):
        async with self.sessions() as session,session.begin():
            # Exclusive: commands take the shared lock before any append.
            await session.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':REBUILD_LOCK})
            rows=(await session.scalars(select(EventRecord).order_by(
                EventRecord.aggregate_id,EventRecord.aggregate_version))).all()
            await session.execute(delete(OrderProjection))
            aggregate=None;current=None
            for record in rows:
                if record.aggregate_id != current:
                    aggregate=OrderAggregate();current=record.aggregate_id
                if record.aggregate_version != aggregate.version+1:
                    raise ValueError('Secuencia de eventos incompleta')
                aggregate.apply(decode_event(record.event_type,record.payload))
                await self.apply(session,record,aggregate)
            return len(rows)
