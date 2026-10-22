import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime,timezone
from sqlalchemy import select,text
from app.eventstore.models import OutboxRecord

log=logging.getLogger(__name__)
RELAY_LOCK=93003002

@dataclass
class StoredMessage:
    order_id: object
    payload: dict
    def to_kafka_value(self):return json.dumps(self.payload,separators=(',',':')).encode()

class OutboxRelay:
    def __init__(self,sessions,publisher):
        self.sessions,self.publisher=sessions,publisher
        self.stop_event=asyncio.Event()
    async def dispatch_once(self):
        async with self.sessions() as session,session.begin():
            # One active dispatcher across processes: prevents overtaking pending rows.
            locked=await session.scalar(text('SELECT pg_try_advisory_xact_lock(:key)'),{'key':RELAY_LOCK})
            if not locked:return False
            row=await session.scalar(select(OutboxRecord).where(OutboxRecord.sent_at.is_(None)).order_by(
                OutboxRecord.id).limit(1).with_for_update())
            if row is None:return False
            await asyncio.to_thread(self.publisher.publish,row.topic,StoredMessage(row.order_id,row.payload))
            row.sent_at=datetime.now(timezone.utc)
            return True
    async def run(self):
        while not self.stop_event.is_set():
            try:
                if await self.dispatch_once():continue
            except Exception:
                log.exception('Publicación pendiente: se conserva outbox para reintentar')
            try:await asyncio.wait_for(self.stop_event.wait(),timeout=1)
            except asyncio.TimeoutError:pass
