import logging
import threading
import time
from collections import deque
from collections.abc import Sequence
from typing import Any

import httpx

from agentscope.processors import EventProcessor

logger = logging.getLogger("agentscope.sdk")


class BackgroundSender:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        batch_size: int,
        flush_interval: float,
        max_queue_size: int,
        timeout: float,
        max_retries: int,
        processors: Sequence[EventProcessor],
    ) -> None:
        self._url = f"{endpoint.rstrip('/')}/v1/ingest/batch"
        self._api_key = api_key
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._max_queue_size = max_queue_size
        self._max_retries = max_retries
        self._processors = processors
        self._events: deque[dict[str, Any]] = deque()
        self._condition = threading.Condition()
        self._closing = False
        self._sending = False
        self.dropped_events = 0
        self._client = httpx.Client(timeout=timeout)
        self._thread = threading.Thread(target=self._run, name="agentscope-telemetry", daemon=True)
        self._thread.start()

    def enqueue(self, event: dict[str, Any]) -> None:
        try:
            processed = event
            for processor in self._processors:
                processed = processor(processed)
        except Exception:
            logger.warning("telemetry processor failed; event dropped", exc_info=True)
            with self._condition:
                self.dropped_events += 1
            return
        with self._condition:
            if self._closing or len(self._events) >= self._max_queue_size:
                self.dropped_events += 1
                return
            self._events.append(processed)
            if len(self._events) >= self._batch_size:
                self._condition.notify_all()

    def _run(self) -> None:
        while True:
            with self._condition:
                if not self._events and not self._closing:
                    self._condition.wait(self._flush_interval)
                if self._closing and not self._events:
                    return
                batch = [
                    self._events.popleft() for _ in range(min(self._batch_size, len(self._events)))
                ]
                if not batch:
                    continue
                self._sending = True
            self._send(batch)
            with self._condition:
                self._sending = False
                self._condition.notify_all()

    def _send(self, events: list[dict[str, Any]]) -> None:
        body = {"sdk": {"name": "agentscope-python", "version": "0.2.0"}, "events": events}
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._url,
                    json=body,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                response.raise_for_status()
                return
            except Exception:
                if attempt >= self._max_retries:
                    logger.warning(
                        "telemetry delivery failed after %s attempt(s)", attempt + 1, exc_info=True
                    )
                    return
                time.sleep(min(0.25 * (2**attempt), 2.0))

    def flush(self, timeout: float = 5.0) -> bool:
        deadline = time.monotonic() + timeout
        with self._condition:
            self._condition.notify_all()
            while (self._events or self._sending) and time.monotonic() < deadline:
                self._condition.wait(max(0.01, deadline - time.monotonic()))
            return not self._events and not self._sending

    def close(self, timeout: float = 5.0) -> None:
        with self._condition:
            if self._closing:
                return
            self._closing = True
            self._condition.notify_all()
        self._thread.join(timeout)
        self._client.close()
