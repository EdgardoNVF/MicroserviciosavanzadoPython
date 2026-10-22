"""Inventario y resultado idempotente en una misma transacción Redis."""
import hashlib
import json
from uuid import UUID
from redis import WatchError
from app.models.product import Product, StockReservation
from app.services.inventory_service import ProductNotFound, InsufficientStock
from shared.events import StockReserved, StockReservationFailed, ReservedItem

TTL = 86400

class EventIdCollision(ValueError):
    pass

class RedisInventoryService:
    def __init__(self, client, prefix="lab02:"):
        self.client, self.prefix = client, prefix

    def product_key(self, product_id):
        return f"{self.prefix}product:{product_id}"

    def event_key(self, event_id):
        return f"{self.prefix}idempotency:inventory:{event_id}"

    def reservation_key(self, reservation_id):
        return f"{self.prefix}reservation:{reservation_id}"

    def add_product(self, payload):
        product = Product(**payload.model_dump())
        self.client.set(self.product_key(product.id), product.model_dump_json())
        return product

    def get_product(self, product_id):
        raw = self.client.get(self.product_key(product_id))
        return Product.model_validate_json(raw) if raw else None

    def list_products(self):
        result = []
        for key in self.client.scan_iter(match=f"{self.prefix}product:*"):
            raw = self.client.get(key)
            if raw:
                result.append(Product.model_validate_json(raw))
        return result

    def reservation_count(self):
        return sum(1 for _ in self.client.scan_iter(match=f"{self.prefix}reservation:*"))

    def create_reservation(self, payload):
        key = self.product_key(payload.product_id)
        for _ in range(50):
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    if raw is None:
                        raise ProductNotFound()
                    product = Product.model_validate_json(raw)
                    if product.stock_quantity < payload.quantity:
                        raise InsufficientStock()
                    reservation = StockReservation(**payload.model_dump())
                    updated = Product(**{**product.model_dump(),
                        "stock_quantity": product.stock_quantity - payload.quantity})
                    pipe.multi()
                    pipe.set(key, updated.model_dump_json())
                    pipe.set(self.reservation_key(reservation.id), reservation.model_dump_json())
                    pipe.execute()
                    return reservation
                except WatchError:
                    continue
        raise RuntimeError("Contención Redis: reintentar")

    def process_event(self, event):
        # Consolidar líneas repetidas sin perder pedidos con varios productos.
        quantities = {}
        for item in event.items:
            quantities[item.product_id] = quantities.get(item.product_id, 0) + item.quantity
        event_key = self.event_key(event.event_id)
        fingerprint = hashlib.sha256(event.to_kafka_value()).hexdigest()
        keys = [self.product_key(pid) for pid in quantities]
        for _ in range(50):
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(event_key, *keys)
                    existing = pipe.get(event_key)
                    if existing:
                        record = json.loads(existing)
                        if record["input_hash"] != fingerprint:
                            raise EventIdCollision("Mismo event_id con contenido diferente")
                        return record, False
                    products = {}
                    failure = None
                    for pid, qty in quantities.items():
                        raw = pipe.get(self.product_key(pid))
                        product = Product.model_validate_json(raw) if raw else None
                        available = product.stock_quantity if product else 0
                        if product is None or available < qty:
                            failure = StockReservationFailed(
                                order_id=event.order_id, product_id=pid,
                                quantity_requested=qty, available_stock=available,
                                reason="PRODUCT_NOT_FOUND" if product is None else "INSUFFICIENT_STOCK",
                                correlation_id=event.correlation_id, causation_id=event.event_id)
                            break
                        products[pid] = product
                    updates, reservations, items = [], [], []
                    if failure is None:
                        for pid, product in products.items():
                            qty = quantities[pid]
                            updated = Product(**{**product.model_dump(),
                                "stock_quantity": product.stock_quantity - qty})
                            reservation = StockReservation(product_id=pid, order_id=event.order_id, quantity=qty)
                            updates.append(updated)
                            reservations.append(reservation)
                            items.append(ReservedItem(product_id=pid, quantity_reserved=qty,
                                remaining_stock=updated.stock_quantity, reservation_id=reservation.id))
                        reply = StockReserved(order_id=event.order_id, items=items,
                            correlation_id=event.correlation_id, causation_id=event.event_id)
                    else:
                        reply = failure
                    record = {"input_hash": fingerprint, "published": False,
                              "reply": reply.model_dump(mode="json")}
                    pipe.multi()
                    for product in updates:
                        pipe.set(self.product_key(product.id), product.model_dump_json())
                    for reservation in reservations:
                        pipe.set(self.reservation_key(reservation.id), reservation.model_dump_json())
                    pipe.set(event_key, json.dumps(record), ex=TTL)
                    pipe.execute()
                    return record, True
                except WatchError:
                    continue
        raise RuntimeError("Contención Redis: reintentar")

    def mark_published(self, event_id):
        key = self.event_key(event_id)
        for _ in range(50):
            with self.client.pipeline() as pipe:
                try:
                    pipe.watch(key)
                    raw = pipe.get(key)
                    if raw is None:
                        raise RuntimeError("Registro idempotente expirado antes de publicar")
                    record = json.loads(raw)
                    record["published"] = True
                    pipe.multi()
                    pipe.set(key, json.dumps(record), xx=True, keepttl=True)
                    pipe.execute()
                    return
                except WatchError:
                    continue
        raise RuntimeError("Contención Redis al confirmar publicación")
