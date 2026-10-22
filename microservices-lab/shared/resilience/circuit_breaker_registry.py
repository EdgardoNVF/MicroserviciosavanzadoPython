import logging
import threading
import pybreaker
import redis

class TransitionLog(pybreaker.CircuitBreakerListener):
    def __init__(self):
        self.transitions=[]
    def state_change(self,cb,old_state,new_state):
        before=old_state.name if old_state else None
        self.transitions.append({'from':before,'to':new_state.name})
        self.transitions=self.transitions[-20:]
        logging.getLogger(__name__).info('Circuit %s: %s -> %s',cb.name,before,new_state.name)

class CircuitBreakerRegistry:
    """Single-process registry; Redis persists state across restarts.

    Same namespace is deliberately NOT a distributed mutual-exclusion protocol.
    Use one worker/replica for this lab. Redis operations run in the HTTP worker.
    """
    def __init__(self,redis_url,namespace,fail_max=5,reset_timeout=30,excluded=()):
        self.redis=redis.Redis.from_url(redis_url,decode_responses=False,
                                      socket_timeout=.5,socket_connect_timeout=.5)
        self.namespace=namespace
        self.excluded=excluded
        self.fail_max=fail_max
        self.reset_timeout=reset_timeout
        self.breaker=None
        self.creation_lock=threading.Lock()
        self.listener=TransitionLog()

    def get_breaker(self):
        self.redis.ping()
        with self.creation_lock:
            if self.breaker is not None:return self.breaker
            storage=pybreaker.CircuitRedisStorage(pybreaker.STATE_CLOSED,self.redis,
                    namespace=self.namespace,fallback_circuit_state=pybreaker.STATE_OPEN)
            self.breaker=pybreaker.CircuitBreaker(fail_max=self.fail_max,
                    reset_timeout=self.reset_timeout,state_storage=storage,
                    listeners=[self.listener],name='inventory-service',exclude=self.excluded)
        return self.breaker

    def status(self):
        breaker=self.get_breaker()
        return dict(service=breaker.name,state=breaker.current_state,
                    fail_counter=breaker.fail_counter,fail_max=breaker.fail_max,
                    reset_timeout=breaker.reset_timeout,namespace=self.namespace,
                    transitions=list(self.listener.transitions))

    def reset(self):
        self.get_breaker().close()
        return {'state':'closed','service':'inventory-service'}

    def close(self):
        self.redis.close()
