"""POST SSE transport with heartbeats and deterministic disconnect cleanup."""

import asyncio
import json
from contextlib import suppress
from dataclasses import dataclass
from typing import Any

import anyio
from pydantic import BaseModel
from starlette.responses import StreamingResponse


@dataclass(frozen=True)
class StreamEvent:
    event: str
    data: Any


def format_event(event: StreamEvent) -> str:
    if not event.event or any(char in event.event for char in "\r\n:"):
        raise ValueError("Invalid SSE event name")

    def encode(value):
        if isinstance(value, BaseModel):
            return value.model_dump(by_alias=True)
        raise TypeError("Unsupported SSE payload")

    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"), default=encode)
    return f"event: {event.event}\ndata: {payload}\n\n"


async def heartbeat_events(events, interval=15):
    iterator = events.__aiter__()
    pending = None
    try:
        while True:
            pending = asyncio.create_task(anext(iterator))
            while not pending.done():
                completed, _ = await asyncio.wait({pending}, timeout=interval)
                if not completed:
                    yield ": heartbeat\n\n"
            try:
                event = pending.result()
            except StopAsyncIteration:
                break
            yield format_event(event)
    finally:
        with anyio.CancelScope(shield=True):
            if pending is not None:
                pending.cancel()
                with suppress(asyncio.CancelledError, StopAsyncIteration):
                    await pending
            await iterator.aclose()


class EventStreamResponse(StreamingResponse):
    def __init__(self, events, *, heartbeat_seconds=15):
        super().__init__(
            heartbeat_events(events, heartbeat_seconds),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also close when ASGI 2.4 send() raises between generator yields.
            with anyio.CancelScope(shield=True):
                await self.body_iterator.aclose()
