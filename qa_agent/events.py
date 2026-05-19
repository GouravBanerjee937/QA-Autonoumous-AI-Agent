"""Simple event bus so steps can report progress to any consumer (UI, CLI)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Literal

EventLevel = Literal["info", "success", "warn", "error"]


@dataclass
class Event:
    step: str
    message: str
    level: EventLevel = "info"
    timestamp: datetime = field(default_factory=datetime.now)


class EventBus:
    """Push events to one or more sinks (e.g. Streamlit, stdout)."""

    def __init__(self) -> None:
        self._sinks: list[Callable[[Event], None]] = []

    def subscribe(self, sink: Callable[[Event], None]) -> None:
        self._sinks.append(sink)

    def emit(self, step: str, message: str, level: EventLevel = "info") -> None:
        event = Event(step=step, message=message, level=level)
        for sink in self._sinks:
            sink(event)


def stdout_sink(event: Event) -> None:
    ts = event.timestamp.strftime("%H:%M:%S")
    marker = {"info": "•", "success": "✓", "warn": "!", "error": "✗"}[event.level]
    print(f"[{ts}] {marker} [{event.step}] {event.message}")
