import httpx
from tenacity import Retrying,stop_after_attempt,wait_random_exponential,retry_if_exception_type

class TransientInventoryError(Exception):
    """Only transient responses and network errors may be retried."""

class InventoryProtocolError(Exception):
    """Unusable responses: unknown availability, no retry."""

TRANSIENT=(TransientInventoryError,httpx.TransportError)
RETRYABLE_STATUS={408,429,500,502,503,504}

def retry_policy(attempts=3,multiplier=.1,max_wait=.5,sleep=None):
    options=dict(stop=stop_after_attempt(attempts),
                 wait=wait_random_exponential(multiplier=multiplier,max=max_wait),
                 retry=retry_if_exception_type(TRANSIENT),reraise=True)
    if sleep is not None:options['sleep']=sleep
    return Retrying(**options)
