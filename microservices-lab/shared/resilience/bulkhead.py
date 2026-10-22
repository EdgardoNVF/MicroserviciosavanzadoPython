import asyncio

class BulkheadFullError(Exception):
    pass

class BulkheadSemaphore:
    """Slots cover both queued worker jobs and running external calls."""
    def __init__(self, service_name, max_concurrent=10, acquire_timeout=.1):
        if max_concurrent < 1 or acquire_timeout <= 0:
            raise ValueError('Bulkhead configuration must be positive')
        self.service_name=service_name
        self.max_concurrent=max_concurrent
        self.acquire_timeout=acquire_timeout
        self.semaphore=asyncio.Semaphore(max_concurrent)
        self.active_calls=0
        self.rejected_calls=0
        self.peak_active=0

    async def acquire(self):
        try:
            await asyncio.wait_for(self.semaphore.acquire(),self.acquire_timeout)
        except TimeoutError as exc:
            self.rejected_calls+=1
            raise BulkheadFullError(self.service_name) from exc
        self.active_calls+=1
        self.peak_active=max(self.peak_active,self.active_calls)

    def release(self):
        if self.active_calls <= 0:
            raise RuntimeError('Unbalanced bulkhead release')
        self.active_calls-=1
        self.semaphore.release()

    @property
    def stats(self):
        return dict(service=self.service_name,max_concurrent=self.max_concurrent,
                    active_calls=self.active_calls,available_slots=self.max_concurrent-self.active_calls,
                    rejected_calls=self.rejected_calls,peak_active=self.peak_active)
