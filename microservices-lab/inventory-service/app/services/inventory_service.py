from uuid import UUID
from threading import Lock
from app.models.product import Product, StockReservation
from app.schemas.product import ProductCreate, StockReservationCreate

class ProductNotFound(Exception):
    pass

class InsufficientStock(Exception):
    pass

class InventoryService:
    """Estado volátil local. El lock protege un solo proceso, no réplicas."""
    def __init__(self):
        self._products: dict[UUID, Product] = {}
        self._reservations: dict[UUID, StockReservation] = {}
        self._lock = Lock()

    def add_product(self, payload: ProductCreate) -> Product:
        product = Product(**payload.model_dump())
        with self._lock:
            self._products[product.id] = product
        return product.model_copy(deep=True)

    def get_product(self, product_id: UUID) -> Product | None:
        with self._lock:
            product = self._products.get(product_id)
            return product.model_copy(deep=True) if product else None

    def list_products(self) -> list[Product]:
        with self._lock:
            return [p.model_copy(deep=True) for p in self._products.values()]

    def reservation_count(self) -> int:
        with self._lock:
            return len(self._reservations)

    def create_reservation(self, payload: StockReservationCreate) -> StockReservation:
        with self._lock:
            product = self._products.get(payload.product_id)
            if product is None:
                raise ProductNotFound()
            if product.stock_quantity < payload.quantity:
                raise InsufficientStock()
            reservation = StockReservation(**payload.model_dump())
            # Construir objetos válidos antes de modificar el estado.
            updated = Product(**{**product.model_dump(),
                                 "stock_quantity": product.stock_quantity - payload.quantity})
            self._products[product.id] = updated
            self._reservations[reservation.id] = reservation
            return reservation.model_copy(deep=True)
