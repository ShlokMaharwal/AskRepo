"""A bounded FIFO wait queue sharing one global and per-IP provider allowance."""

import asyncio
import threading
import time
from collections import deque

from app.errors import DemoLimitError


class ProviderQuota:
    def __init__(self, settings, *, clock=time.monotonic, sleep=asyncio.sleep):
        self.settings, self.clock, self.sleep = settings, clock, sleep
        self.lock = threading.Lock()
        self.global_calls, self.queue = deque(), deque()
        self.peers = {}

    def take(self, ip):
        now = self.clock()
        while self.global_calls and self.global_calls[0] <= now - 60:
            self.global_calls.popleft()
        if ip not in self.peers:
            if len(self.peers) >= 10000:
                self.peers = {
                    peer: calls
                    for peer, calls in self.peers.items()
                    if calls and calls[-1] > now - 60
                }
                if len(self.peers) >= 10000:
                    return False
            self.peers[ip] = deque()
        calls = self.peers[ip]
        while calls and calls[0] <= now - 60:
            calls.popleft()
        if (
            len(self.global_calls) >= self.settings.llm_global_rpm
            or len(calls) >= self.settings.llm_per_ip_rpm
        ):
            return False
        self.global_calls.append(now)
        calls.append(now)
        return True

    async def acquire(self, ip):
        ticket = object()
        with self.lock:
            if not self.queue and self.take(ip):
                return
            if len(self.queue) >= self.settings.llm_max_queued:
                raise DemoLimitError()
            self.queue.append(ticket)
        deadline = self.clock() + self.settings.llm_queue_wait_seconds
        try:
            while True:
                with self.lock:
                    if self.queue and self.queue[0] is ticket and self.take(ip):
                        self.queue.popleft()
                        return
                remaining = deadline - self.clock()
                if remaining <= 0:
                    raise DemoLimitError()
                await self.sleep(min(0.05, remaining))
        finally:
            with self.lock:
                if ticket in self.queue:
                    self.queue.remove(ticket)
