"""Provider attempts share quota, backoff, and a hard per-question budget."""

import asyncio
import inspect
import threading
import time
from collections import OrderedDict
from contextlib import aclosing

from app.errors import DemoLimitError
from app.generate.quota import ProviderQuota


class CallBudget:
    def __init__(self, limit):
        self.limit, self._used = limit, 0
        self.lock = threading.Lock()

    @property
    def used(self):
        with self.lock:
            return self._used

    def available(self, reserve=0):
        with self.lock:
            return self._used < self.limit - reserve

    def take(self, reserve=0):
        with self.lock:
            if self._used >= self.limit - reserve:
                raise DemoLimitError()
            self._used += 1


class QuestionBudgets:
    """Share a cap across stream/fallback attempts carrying the same request ID."""

    def __init__(self, max_size=1000, ttl=600, clock=time.monotonic):
        self.max_size, self.ttl, self.clock = max_size, ttl, clock
        self.items = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key, limit):
        with self.lock:
            now = self.clock()
            for stale in [key for key, (expires, _) in self.items.items() if expires <= now]:
                del self.items[stale]
            if key not in self.items:
                if len(self.items) >= self.max_size:
                    raise DemoLimitError()
                self.items[key] = (now + self.ttl, CallBudget(limit))
            return self.items[key][1]


def retryable(error):
    code = getattr(error, "code", None) or getattr(
        getattr(error, "response", None), "status_code", 0
    )
    try:
        return int(code) == 429 or 500 <= int(code) <= 599
    except (ValueError, TypeError):
        return False


class LLMClient:
    def __init__(self, provider, settings, *, quota=None, sleep=asyncio.sleep):
        self.provider, self.settings = provider, settings
        self.quota = quota or ProviderQuota(settings)
        self.sleep = sleep

    async def begin(self, budget, ip, reserve=0):
        if self.provider.name == "extractive":
            return
        if not budget.available(reserve):
            raise DemoLimitError()
        await self.quota.acquire(ip)
        budget.take(reserve)

    async def call(self, operation, *args, budget, reserve=0, ip="local", **kwargs):
        method = getattr(self.provider, operation)
        for attempt in range(self.settings.llm_max_retries + 1):
            await self.begin(budget, ip, reserve)
            try:
                if inspect.iscoroutinefunction(method):
                    return await method(*args, **kwargs)
                return await asyncio.to_thread(method, *args, **kwargs)
            except Exception as error:
                if not retryable(error):
                    raise
                if attempt >= self.settings.llm_max_retries or not budget.available(reserve):
                    raise DemoLimitError() from None
                await self.sleep(self.settings.llm_retry_backoff_seconds * (2**attempt))

    async def stream(self, *args, budget, ip="local", **kwargs):
        for attempt in range(self.settings.llm_max_retries + 1):
            await self.begin(budget, ip)
            sent = False
            try:
                async with aclosing(self.provider.stream(*args, **kwargs)) as pieces:
                    async for piece in pieces:
                        sent = True
                        yield piece
                return
            except Exception as error:
                if not retryable(error):
                    raise
                # Never replay a provider stream once text has reached the user.
                if sent or attempt >= self.settings.llm_max_retries or not budget.available():
                    raise DemoLimitError() from None
                await self.sleep(self.settings.llm_retry_backoff_seconds * (2**attempt))
