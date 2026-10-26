from decimal import Decimal
from uuid import uuid4
from app.models.order import Order,OrderItem,OrderStatus
from app.domain.events import OrderCreated,OrderStatusChanged,OrderCancelled,OrderItemAdded
from app.services.order_service import InvalidOrderState

TRANSITIONS={
    OrderStatus.PENDING:{OrderStatus.CONFIRMED},
    OrderStatus.CONFIRMED:{OrderStatus.PROCESSING},
    OrderStatus.PROCESSING:{OrderStatus.SHIPPED},
    OrderStatus.SHIPPED:{OrderStatus.DELIVERED},
    OrderStatus.DELIVERED:set(),OrderStatus.CANCELLED:set(),
}

class OrderAggregate:
    def __init__(self):
        self.order=None;self.version=0;self.correlation_id=None;self.last_event_id=None

    @classmethod
    def creation(cls,payload):
        return OrderCreated(aggregate_id=uuid4(),customer_id=payload.customer_id,items=payload.items)

    def common(self):
        if self.order is None:raise InvalidOrderState()
        return dict(aggregate_id=self.order.id,correlation_id=self.correlation_id,
                    causation_id=self.last_event_id)

    def change_status(self,status):
        event=OrderStatusChanged(**self.common(),previous_status=self.order.status,new_status=status)
        self.check(event)
        return event

    def cancel(self,reason=""):
        event=OrderCancelled(**self.common(),reason=reason);self.check(event);return event

    def add_item(self,item):
        event=OrderItemAdded(**self.common(),item=item);self.check(event);return event

    def check(self,event):
        if isinstance(event,OrderCreated):
            if self.order is not None:raise InvalidOrderState()
            return
        if self.order is None or event.aggregate_id != self.order.id:raise InvalidOrderState()
        if isinstance(event,OrderStatusChanged):
            if event.previous_status != self.order.status or event.new_status not in TRANSITIONS[self.order.status]:
                raise InvalidOrderState()
        elif isinstance(event,OrderCancelled):
            if self.order.status not in {OrderStatus.PENDING,OrderStatus.CONFIRMED,OrderStatus.PROCESSING}:
                raise InvalidOrderState()
        elif isinstance(event,OrderItemAdded):
            if self.order.status not in {OrderStatus.PENDING,OrderStatus.CONFIRMED} or len(self.order.items)>=100:
                raise InvalidOrderState()
        else:raise ValueError("Evento no soportado")

    def apply(self,event):
        self.check(event)
        if isinstance(event,OrderCreated):
            items=tuple(OrderItem(product_id=i.product_id,quantity=i.quantity,unit_price=Decimal(i.unit_price)) for i in event.items)
            self.order=Order(id=event.aggregate_id,customer_id=event.customer_id,items=items,created_at=event.timestamp)
            self.correlation_id=event.correlation_id
        else:
            data=self.order.model_dump()
            if isinstance(event,OrderStatusChanged):data['status']=event.new_status
            elif isinstance(event,OrderCancelled):data['status']=OrderStatus.CANCELLED
            elif isinstance(event,OrderItemAdded):
                i=event.item
                data['items']=self.order.items+(OrderItem(product_id=i.product_id,quantity=i.quantity,unit_price=Decimal(i.unit_price)),)
            self.order=Order(**data)
        self.version+=1;self.last_event_id=event.event_id

    def snapshot(self):
        return {'order':self.order.model_dump(mode='json'),'correlation_id':str(self.correlation_id),
                'last_event_id':str(self.last_event_id)}

    @classmethod
    def from_snapshot(cls,state,version):
        from uuid import UUID
        instance=cls();instance.order=Order.model_validate(state['order']);instance.version=version
        instance.correlation_id=UUID(state['correlation_id']);instance.last_event_id=UUID(state['last_event_id'])
        return instance
