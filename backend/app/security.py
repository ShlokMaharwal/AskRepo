import threading
import time
from collections import deque

from starlette.responses import JSONResponse

from app.client_ip import client_ip


class RateLimiter:
    def __init__(self, max_buckets=10000, clock=time.monotonic):
        self.buckets = {}
        self.lock = threading.Lock()
        self.max_buckets, self.clock = max_buckets, clock

    def allow(self, address, route, limit, cost=1):
        now = self.clock()
        key = (address, route)
        with self.lock:
            if key not in self.buckets:
                if len(self.buckets) >= self.max_buckets:
                    for old in list(self.buckets):
                        if not self.buckets[old] or self.buckets[old][-1] <= now - 60:
                            del self.buckets[old]
                    if len(self.buckets) >= self.max_buckets:
                        return False
                self.buckets[key] = deque()
            timestamps = self.buckets[key]
            while timestamps and timestamps[0] <= now - 60:
                timestamps.popleft()
            if len(timestamps) + cost > limit:
                return False
            timestamps.extend([now] * cost)
            return True


class RequestGuard:
    """Bound API bodies before JSON parsing, and rate limit by the ASGI peer address."""

    def __init__(self, app, settings, limiter):
        self.app, self.settings, self.limiter = app, settings, limiter

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        resolved = client_ip(scope, self.settings.trusted_proxies)
        scope.setdefault("state", {})["client_ip"] = resolved
        path = scope.get("path", "")
        if scope["method"] != "POST" or path not in {"/ask", "/ask/stream", "/index", "/compare"}:
            return await self.app(scope, receive, send)
        address = resolved
        route = "index" if path == "/index" else "ask"
        limit = (
            self.settings.index_rate_per_minute
            if route == "index"
            else self.settings.ask_rate_per_minute
        )
        if not self.limiter.allow(address, route, limit, cost=3 if path == "/compare" else 1):
            return await JSONResponse(
                {"detail": "Rate limit exceeded; try again shortly"},
                status_code=429,
                headers={"Retry-After": "60"},
            )(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.settings.max_request_bytes:
                return await JSONResponse({"detail": "Request body is too large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
