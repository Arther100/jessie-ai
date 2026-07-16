"""
Jessie — backend/gateway/queue.py
asyncio-based concurrency limiter for 20+ simultaneous team members.

Problem: if 20 developers all fire requests at once, hitting Claude with
20 simultaneous API calls is expensive and risks rate-limit errors.

Solution: cap concurrent Claude calls at MAX_CONCURRENT (default 5).
Requests beyond that wait in a virtual queue and receive position updates.

Priority system:
  priority=0  regular developer  (default)
  priority=1  senior dev / team lead — jumps ahead of priority=0 requests

JessieQueue is a singleton — the same instance is shared across all
FastAPI request handlers so the global concurrency cap is enforced.

Raises:
  QueueTimeout  — request waited > 5 minutes without getting a slot
"""

import asyncio
import time
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_CONCURRENT           = 5
QUEUE_TIMEOUT_SECONDS    = 300   # 5 minutes
EST_SECONDS_PER_REQUEST  = 8     # used for wait-time estimate in status updates


class QueueTimeout(Exception):
    """Raised when a request waits longer than QUEUE_TIMEOUT_SECONDS."""
    pass


class _PrioritisedWaiter:
    """
    Internal waiter entry stored in the priority list.
    Lower sort_key = higher priority (runs first).
    sort_key = (-priority, sequence_number)
    """
    __slots__ = ("sort_key", "user_id", "future")

    def __init__(self, priority: int, sequence: int, user_id: str):
        self.sort_key = (-priority, sequence)   # negate so higher priority sorts first
        self.user_id  = user_id
        self.future: asyncio.Future = asyncio.get_running_loop().create_future()

    def __lt__(self, other: "_PrioritisedWaiter") -> bool:
        return self.sort_key < other.sort_key


class JessieQueue:
    """
    Singleton async concurrency limiter with priority support.

    Usage:
        queue = JessieQueue()

        async def my_claude_call():
            return await call_claude(...)

        result = await queue.enqueue(my_claude_call, user_id="vijay", priority=0)
    """
    _instance: Optional["JessieQueue"] = None

    def __new__(cls) -> "JessieQueue":
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._semaphore   = asyncio.Semaphore(MAX_CONCURRENT)
            inst._waiters: list[_PrioritisedWaiter] = []
            inst._processing: set[str] = set()
            inst._sequence    = 0
            cls._instance     = inst
        return cls._instance

    async def enqueue(
        self,
        request_fn: Callable[[], Any],
        user_id: str,
        priority: int = 0,
    ) -> Any:
        """
        Execute request_fn when a concurrency slot is available.

        If all MAX_CONCURRENT slots are busy, this coroutine suspends
        until a slot is freed. The timeout is QUEUE_TIMEOUT_SECONDS.

        Args:
            request_fn: async callable that performs the Claude API call
            user_id:    for tracking position + logging
            priority:   0=normal, 1=senior (higher runs first)

        Returns:
            Whatever request_fn() returns.

        Raises:
            QueueTimeout if no slot becomes available within 5 minutes.
        """
        self._sequence += 1
        waiter = _PrioritisedWaiter(priority, self._sequence, user_id)

        # Fast path — slot immediately available
        if self._semaphore._value > 0:  # type: ignore[attr-defined]
            await self._semaphore.acquire()
        else:
            # Add to wait list and suspend until signalled
            import heapq
            heapq.heappush(self._waiters, waiter)
            logger.info(
                f"Queue: {user_id} waiting (position "
                f"{self._queue_position(user_id)}, "
                f"priority={priority})"
            )
            try:
                await asyncio.wait_for(
                    asyncio.shield(waiter.future),
                    timeout=QUEUE_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                self._waiters = [w for w in self._waiters if w is not waiter]
                raise QueueTimeout(
                    f"{user_id} timed out after "
                    f"{QUEUE_TIMEOUT_SECONDS}s in queue"
                )

        self._processing.add(user_id)
        start = time.monotonic()
        try:
            result = await request_fn()
            elapsed = time.monotonic() - start
            logger.info(f"Queue: {user_id} completed in {elapsed:.1f}s")
            return result
        finally:
            self._processing.discard(user_id)
            self._release_next()

    def get_queue_status(self) -> dict:
        """
        Snapshot of current queue state.

        Returns:
            {
              "waiting":    int,            # requests waiting for a slot
              "processing": int,            # requests currently running
              "positions":  {user_id: int}, # 1-based position per waiter
            }
        """
        return {
            "waiting":    len(self._waiters),
            "processing": len(self._processing),
            "positions":  {
                w.user_id: i + 1
                for i, w in enumerate(sorted(self._waiters))
            },
        }

    def estimated_wait_seconds(self) -> int:
        """Rough wait time estimate based on queue depth."""
        return max(0, len(self._waiters)) * EST_SECONDS_PER_REQUEST

    def queue_position(self, user_id: str) -> int:
        """1-based position for user_id, 0 if not waiting."""
        return self._queue_position(user_id)

    # ── Private ────────────────────────────────────────────────────────────

    def _release_next(self) -> None:
        """
        When a slot is freed, either wake the highest-priority waiter
        or release the semaphore for the fast path.
        """
        if self._waiters:
            import heapq
            next_waiter = heapq.heappop(self._waiters)
            if not next_waiter.future.done():
                next_waiter.future.set_result(True)
            # Semaphore stays acquired — the waiter will use it
        else:
            self._semaphore.release()

    def _queue_position(self, user_id: str) -> int:
        sorted_waiters = sorted(self._waiters)
        for i, w in enumerate(sorted_waiters):
            if w.user_id == user_id:
                return i + 1
        return 0
