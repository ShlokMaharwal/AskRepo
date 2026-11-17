"""Pace embedding inputs and respect provider RetryInfo without logging its message."""

import re
import time
from collections import deque


class EmbeddingQuotaError(ValueError):
    pass


def retry_delay(error):
    headers = getattr(getattr(error, "response", None), "headers", {})
    try:
        return max(0, min(86400, float(headers.get("retry-after"))))
    except (TypeError, ValueError):
        pass
    data = getattr(error, "response_json", {}) or {}
    details = data.get("error", data).get("details", []) if isinstance(data, dict) else []
    for detail in details:
        match = re.fullmatch(r"(\d+(?:\.\d+)?)s", str(detail.get("retryDelay", "")))
        if match:
            return min(86400, float(match[1]))
    # Gemini currently also returns human-readable 22h13m35s durations.
    message = getattr(error, "message", "") or ""
    match = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(\d+(?:\.\d+)?)s", message)
    if match:
        return min(86400, int(match[1] or 0) * 3600 + int(match[2] or 0) * 60 + float(match[3]))
    if "per day" in message.lower() or "daily" in message.lower():
        return 86400
    return 0


class EmbeddingPacer:
    def __init__(self, settings, stop, clock=time.monotonic):
        self.settings, self.stop, self.clock = settings, stop, clock
        self.events = deque()

    def acquire(self, texts):
        inputs = len(texts)
        tokens = sum(max(1, (len(text.encode("utf-8")) + 2) // 3) for text in texts)
        if (
            inputs > self.settings.gemini_embedding_rpm
            or tokens > self.settings.gemini_embedding_tpm
        ):
            raise EmbeddingQuotaError(
                "Embedding batch exceeds the configured minute budget; reduce batch size."
            )
        while True:
            now = self.clock()
            while self.events and self.events[0][0] <= now - 60:
                self.events.popleft()
            if (
                sum(item[1] for item in self.events) + inputs <= self.settings.gemini_embedding_rpm
                and sum(item[2] for item in self.events) + tokens
                <= self.settings.gemini_embedding_tpm
            ):
                self.events.append((now, inputs, tokens))
                return
            if self.stop.wait(max(0.01, 60 - (now - self.events[0][0]))):
                raise EmbeddingQuotaError("Embedding work stopped")
