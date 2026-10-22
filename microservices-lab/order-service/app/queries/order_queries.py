from sqlalchemy import select
from app.schemas.order import OrderResponse,OrderItemResponse
from app.eventstore.models import OrderProjection

# Formateador compartido de respuestas; no lee el Event Store.
def response_from_order(order):
    return OrderResponse(id=order.id,customer_id=order.customer_id,status=order.status,
        created_at=order.created_at,total=f'{order.total:.2f}',items=[OrderItemResponse(
            product_id=i.product_id,quantity=i.quantity,unit_price=f'{i.unit_price:.2f}',
            subtotal=f'{i.subtotal:.2f}') for i in order.items])

class OrderQueries:
    def __init__(self,sessions):self.sessions=sessions
    @staticmethod
    def response(projection):
        return OrderResponse(id=projection.order_id,customer_id=projection.customer_id,
            status=projection.status,items=projection.items,total=f'{projection.total_amount:.2f}',
            created_at=projection.created_at)
    async def get(self,order_id):
        async with self.sessions() as session:
            row=await session.get(OrderProjection,order_id)
            return (self.response(row),row.event_count) if row else None
    async def list(self,limit=50,offset=0):
        async with self.sessions() as session:
            rows=(await session.scalars(select(OrderProjection).order_by(
                OrderProjection.created_at.desc(),OrderProjection.order_id).limit(limit).offset(offset))).all()
            return [self.response(row) for row in rows]
