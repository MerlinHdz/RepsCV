"""Small bounded, single-process authentication throttle; no request data logged."""

from collections import OrderedDict, deque
import threading
import time
from fastapi import HTTPException


class AuthThrottle:
    def __init__(self, limit=20, window=60, clock=time.monotonic):
        self.limit, self.window, self.clock = limit, window, clock
        self.requests = OrderedDict()
        self.lock = threading.Lock()

    def check(self, key):
        with self.lock:
            now = self.clock()
            times = self.requests.pop(key, deque())
            while times and times[0] <= now - self.window:
                times.popleft()
            self.requests[key] = times
            if len(self.requests) > 10000:
                self.requests.popitem(last=False)
            if len(times) >= self.limit:
                raise HTTPException(429, "Too many sign-in attempts. Try again in a minute.",
                                    headers={"Retry-After": str(self.window)})
            times.append(now)
