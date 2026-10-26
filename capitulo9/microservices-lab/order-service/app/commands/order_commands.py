from app.domain.order_aggregate import OrderAggregate
from app.eventstore.store import VersionConflict
from app.services.order_service import OrderNotFound

class OrderCommands:
    def __init__(self,store):self.store=store
    
    async def create(self,payload):
        event=OrderAggregate.creation(payload)
        return await self.store.append_events(event.aggregate_id,[event],0)
    
    async def change(self,order_id,kind,payload=None,expected_version=None):
        aggregate=await self.store.load(order_id)
        if aggregate.order is None:raise OrderNotFound()
        if expected_version is not None and expected_version != aggregate.version:
            raise VersionConflict('Versión enviada por el cliente obsoleta')
        if kind=='status':event=aggregate.change_status(payload.new_status)
        elif kind=='cancel':event=aggregate.cancel(payload.reason if payload else '')
        elif kind=='item':event=aggregate.add_item(payload)
        else:raise ValueError('Comando desconocido')
        return await self.store.append_events(order_id,[event],aggregate.version)
