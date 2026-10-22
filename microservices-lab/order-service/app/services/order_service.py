from decimal import Decimal
from threading import Lock
from uuid import UUID
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import OrderCreate

class OrderNotFound(Exception):
    pass

class InvalidOrderState(Exception):
    pass

class OrderService:
    def __init__(self):
        self._orders: dict[UUID, Order] = {}
        self._lock = Lock()

    def prepare_order(self, payload: OrderCreate) -> Order:
        items = tuple(OrderItem(product_id=i.product_id, quantity=i.quantity,
                                unit_price=Decimal(i.unit_price)) for i in payload.items)
        order = Order(customer_id=payload.customer_id, items=items)
        return order

    def save_order(self, order: Order) -> Order:
        with self._lock:
            self._orders[order.id] = order
        return order.model_copy(deep=True)

    def create_order(self, payload: OrderCreate) -> Order:
        return self.save_order(self.prepare_order(payload))

    def get_order(self, order_id: UUID) -> Order | None:
        with self._lock:
            order = self._orders.get(order_id)
            return order.model_copy(deep=True) if order else None

    def list_orders(self) -> list[Order]:
        with self._lock:
            return [o.model_copy(deep=True) for o in self._orders.values()]

    def cancel_order(self, order_id: UUID) -> Order:
        with self._lock:
            order = self._orders.get(order_id)
            if order is None:
                raise OrderNotFound()
            if order.status != OrderStatus.PENDING:
                raise InvalidOrderState()
            cancelled = Order(**{**order.model_dump(), "status": OrderStatus.CANCELLED})
            self._orders[order_id] = cancelled
            return cancelled.model_copy(deep=True)
