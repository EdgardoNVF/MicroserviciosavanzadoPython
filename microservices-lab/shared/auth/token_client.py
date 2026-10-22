import os
import time
import threading
import httpx

class ServiceAuthenticationError(Exception):pass

class ServiceTokenClient:
    """Sync client used inside the Lab04 worker; cache/refresh is thread-safe."""
    def __init__(self,token_url,client_id,client_secret,scope='inventory.read',transport=None,clock=time.monotonic):
        if not client_id or not client_secret:raise ValueError('Service OAuth credentials are required')
        self.token_url=token_url
        self.client_id=client_id
        self.client_secret=client_secret
        self.scope=scope
        self.clock=clock
        self.http=httpx.Client(timeout=2,transport=transport,trust_env=False,follow_redirects=False)
        self.lock=threading.Lock()
        self.token=None
        self.deadline=0

    @classmethod
    def from_env(cls):
        return cls(os.environ['AUTH_TOKEN_URL'],os.environ['ORDER_SERVICE_CLIENT_ID'],
                   os.environ['ORDER_SERVICE_CLIENT_SECRET'])

    def get_token(self):
        with self.lock:
            if self.token and self.clock()<self.deadline:return self.token
            try:
                response=self.http.post(self.token_url,data={'grant_type':'client_credentials',
                    'client_id':self.client_id,'client_secret':self.client_secret,'scope':self.scope})
                response.raise_for_status()
                data=response.json()
                if not isinstance(data,dict):raise ValueError('Malformed token response')
                token=data['access_token'];lifetime=data['expires_in']
                if (not isinstance(data.get('token_type'),str) or data['token_type'].lower()!='bearer' or not isinstance(token,str) or not token or
                    any(c.isspace() for c in token) or len(token)>16384 or isinstance(lifetime,bool) or
                    not isinstance(lifetime,int) or lifetime<=0):raise ValueError('Malformed token response')
            except (httpx.HTTPError,ValueError,KeyError,TypeError) as exc:
                self.token=None;self.deadline=0
                raise ServiceAuthenticationError('Token acquisition failed') from exc
            self.token=token
            self.deadline=self.clock()+lifetime-min(30,lifetime*.1)
            return token

    def invalidate(self,rejected_token):
        # Do not evict a newer token refreshed by another worker.
        with self.lock:
            if self.token==rejected_token:self.token=None;self.deadline=0

    def close(self):self.http.close()
