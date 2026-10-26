# Bounded contexts — continuidad de Lab 01 a Lab 02

| Contexto | Entidades | Responsabilidad y almacenamiento |
|---|---|---|
| Pedidos | Order, OrderItem | API y cálculo de importes; almacenamiento de pedidos todavía en memoria |
| Inventario | Product, StockReservation | API y reservas por evento; Redis para productos, reservas y resultados idempotentes |

Se comparten contratos de eventos e identificadores, no modelos de dominio.
OrderCreated transporta todas las líneas del pedido, sin precios: Inventario solo necesita IDs y cantidades.
Redis pertenece a Inventario; Pedidos no modifica sus claves.
El consumidor consolida líneas repetidas y reserva el pedido completo o no descuenta ningún producto.
Las respuestas StockReserved/StockReservationFailed se publican para observación; Pedidos todavía no las consume.
El pedido conserva pending. Cancelar no publica un evento ni libera reservas.
Los productos del Lab 01 en memoria deben recrearse al pasar al almacenamiento Redis.

