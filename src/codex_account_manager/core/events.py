"""A tiny thread-safe, sync in-process event bus.

Services publish domain events (e.g. ``switch.stage``, ``account.updated``) and
UI/monitoring layers subscribe. This keeps the core decoupled from the GUI: the
GUI subscribes and marshals events onto its own thread.
"""

from __future__ import annotations

import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

Handler = Callable[["Event"], None]


@dataclass(frozen=True)
class Event:
    """An immutable domain event."""

    topic: str
    payload: dict[str, Any] = field(default_factory=dict)
    at: datetime = field(default_factory=lambda: datetime.now(UTC))


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.RLock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        """Subscribe to ``topic``. Returns an unsubscribe callable."""
        with self._lock:
            self._subscribers[topic].append(handler)

        def _unsubscribe() -> None:
            with self._lock:
                if handler in self._subscribers.get(topic, []):
                    self._subscribers[topic].remove(handler)

        return _unsubscribe

    def publish(self, topic: str, **payload: Any) -> None:
        event = Event(topic=topic, payload=payload)
        with self._lock:
            handlers = list(self._subscribers.get(topic, ()))
            handlers += list(self._subscribers.get("*", ()))
        for handler in handlers:
            try:
                handler(event)
            except Exception:  # a bad subscriber must not break publishers
                pass


#: Process-wide default bus.
bus = EventBus()
