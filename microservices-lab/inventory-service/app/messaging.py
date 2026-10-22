import logging
import time
from threading import Event, Thread
from confluent_kafka import Consumer, KafkaError
from pydantic import ValidationError
from shared.events import OrderCreated, StockReserved, StockReservationFailed
from app.services.redis_inventory import EventIdCollision

log = logging.getLogger(__name__)

class InventoryWorker:
    def __init__(self, service, publisher, bootstrap, consumer=None):
        self.service, self.publisher = service, publisher
        self.consumer = consumer if consumer is not None else Consumer({
            "bootstrap.servers": bootstrap, "group.id": "inventory-service-group",
            "auto.offset.reset": "earliest", "enable.auto.commit": False,
            "enable.auto.offset.store": False, "max.poll.interval.ms": 300000,
        })
        self.stop_event, self.ready = Event(), Event()
        self.thread = None

    def handle(self, message):
        event = OrderCreated.model_validate_json(message.value())
        if message.key() != str(event.order_id).encode():
            raise ValueError("La key Kafka debe ser order_id")
        record, fresh = self.service.process_event(event)
        if not record["published"]:
            data = record["reply"]
            success = data["event_type"] == "StockReserved"
            reply = (StockReserved if success else StockReservationFailed).model_validate(data)
            topic = "inventory.stock-reserved" if success else "inventory.stock-failed"
            self.publisher.publish(topic, reply)
            self.service.mark_published(event.event_id)
        # Solo después del efecto y de confirmar la publicación.
        self.consumer.commit(message=message, asynchronous=False)
        log.info("event_id=%s nuevo=%s partition=%s offset=%s", event.event_id,
                 fresh, message.partition(), message.offset())

    def run(self):
        try:
            self.consumer.subscribe(["orders.created"],
                on_assign=lambda consumer, parts: self.ready.set(),
                on_revoke=lambda consumer, parts: self.ready.clear())
            while not self.stop_event.is_set():
                message = self.consumer.poll(1)
                if message is None:
                    continue
                if message.error():
                    if message.error().code() != KafkaError._PARTITION_EOF:
                        raise RuntimeError(message.error())
                    continue
                # Reintentar EL MISMO mensaje; no avanzar y confirmar offsets posteriores.
                retry_deadline = time.monotonic() + 60
                while not self.stop_event.is_set():
                    try:
                        self.handle(message)
                        self.ready.set()
                        break
                    except (ValidationError, EventIdCollision, ValueError):
                        log.exception("Evento inválido: detener consumidor sin commit; corregir antes de reiniciar")
                        return
                    except Exception:
                        self.ready.clear()
                        log.exception("Fallo transitorio: sin commit; reintento del mismo mensaje")
                        if time.monotonic() >= retry_deadline:
                            log.error("Reintentos agotados: detener sin commit; reiniciar tras corregir dependencia")
                            return
                        self.stop_event.wait(1)
        except Exception:
            log.exception("Consumidor detenido")
        finally:
            self.ready.clear()
            self.consumer.close()

    def start(self):
        self.thread = Thread(target=self.run, name="inventory-kafka", daemon=False)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=30)
        if self.thread.is_alive():
            raise RuntimeError("El consumidor no terminó; no cerrar recursos compartidos")
