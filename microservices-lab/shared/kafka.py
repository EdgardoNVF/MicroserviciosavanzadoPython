"""confluent-kafka 2.4 es síncrono; usar desde hilo o asyncio.to_thread."""
from threading import Lock
from confluent_kafka import Producer

class PublicationError(RuntimeError):
    pass

class EventPublisher:
    def __init__(self, bootstrap, client_id, producer=None):
        self.producer = producer if producer is not None else Producer({
            "bootstrap.servers": bootstrap, "client.id": client_id,
            "enable.idempotence": True, "acks": "all",
            "partitioner": "murmur2_random", "message.timeout.ms": 10000,
        })
        self.lock = Lock()

    def publish(self, topic, event):
        with self.lock:
            delivery = []
            def delivered(error, message):
                delivery.append((error, message))
            self.producer.produce(topic, key=str(event.order_id).encode(),
                                  value=event.to_kafka_value(), on_delivery=delivered)
            remaining = self.producer.flush(12)
            if remaining or not delivery or delivery[0][0] is not None:
                raise PublicationError(f"Entrega no confirmada: {delivery}, pendientes={remaining}")
            message = delivery[0][1]
            return message.partition(), message.offset()

    def ready(self):
        metadata = self.producer.list_topics(timeout=2)
        return bool(metadata.brokers)

    def close(self):
        if self.producer.flush(12):
            raise PublicationError("Mensajes pendientes al cerrar")
