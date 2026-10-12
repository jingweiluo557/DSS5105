"""A per-client limit on the endpoints that spend model calls.

The demo is meant to be opened on phones by an audience, from a shared link. Without a limit, one stuck client or one
script can spend the whole OpenAI budget in minutes. This is a sliding window per client (the first address in
X-Forwarded-For when a gateway such as CloudBase sets it, otherwise the socket address), kept in memory. It is a cost
guard, not security: each cloud-function instance keeps its own window, and the OpenAI spending limit is still the real cap.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

MODEL_PATHS = frozenset({'/chat', '/api/v1/workflow/chat', '/api/v1/workflow/chat/stream', '/api/ai/ask'})


class SlidingWindow:
    def __init__(self, limit: int, window_seconds: float = 60.0, clock=time.monotonic) -> None:
        self.limit, self.window, self.clock = limit, window_seconds, clock
        self.hits: dict[str, deque[float]] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """(allowed, seconds until the next request would be allowed). A limit of 0 turns the guard off."""
        if self.limit <= 0:
            return True, 0
        now = self.clock()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (now - q[0])) + 1)
            q.append(now)
            if len(self.hits) > 10_000:          # forget idle clients so memory stays bounded
                for k in [k for k, v in self.hits.items() if not v]:
                    del self.hits[k]
            return True, 0


def client_key(headers, host: str | None) -> str:
    forwarded = headers.get('x-forwarded-for', '')
    return forwarded.split(',')[0].strip() or host or 'unknown'
