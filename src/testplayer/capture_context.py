"""In-memory context shared by the player and the local capture host."""

from __future__ import annotations

import secrets
import threading
import time
import uuid
from dataclasses import dataclass


@dataclass
class PublishedContext:
    session_id: str
    case_id: int
    step_id: int
    execution_generation: str
    source_client_id: str
    event_id: str
    context_revision: int
    valid: bool
    code: str = ""


class CaptureBroker:
    """Process-local broker. The capability stays in memory and is never written to disk."""

    def __init__(self) -> None:
        self.token = secrets.token_urlsafe(32)
        self.instance_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        self.context: PublishedContext | None = None
        self.events: list[dict] = []
        self.seen_events: set[str] = set()
        self.pulses: dict[str, float] = {}
        self.prepare_id: str | None = None
        self.prepare_ack: str | None = None
        self.host_seen = False
        self.hotkey_ok: bool | None = None
        self.hotkey_label = "PrintScreen"
        self._record_hotkey = False
        self._seq = 0

    def mark_host(self, hotkey_ok: bool | None, label: str | None = None) -> None:
        with self._lock:
            self.host_seen = True
            if hotkey_ok is not None:
                self.hotkey_ok = hotkey_ok
            if isinstance(label, str) and label.strip():
                self.hotkey_label = label.strip()[:80]

    def request_hotkey_record(self) -> None:
        with self._lock:
            self._record_hotkey = True

    def hotkey_record_pending(self) -> bool:
        with self._lock:
            return self._record_hotkey

    def accept_hotkey_record(self) -> None:
        with self._lock:
            self._record_hotkey = False

    def pulse(self, client_id: str) -> None:
        if not client_id:
            return
        with self._lock:
            self.pulses[client_id] = time.monotonic()

    def online_clients(self) -> int:
        now = time.monotonic()
        with self._lock:
            return sum(1 for seen in self.pulses.values() if now - seen < 2.5)

    def remember(self, event_id: str) -> bool:
        """Return True when this event was already applied."""
        with self._lock:
            if not event_id or event_id in self.seen_events:
                return True
            self.seen_events.add(event_id)
            if len(self.seen_events) > 400:
                self.seen_events = set(list(self.seen_events)[-200:])
            return False

    def publish(self, context: PublishedContext, payload: dict) -> dict:
        with self._lock:
            self.context = context
            return self._event(payload)

    def invalidate(self, code: str) -> None:
        with self._lock:
            if self.context is not None:
                self.context.valid = False
                self.context.code = code

    def poll(self, after: int) -> tuple[list[dict], int, bool | None, str]:
        with self._lock:
            events = [item for item in self.events if item["seq"] > after]
            cursor = self.events[-1]["seq"] if self.events else after
            return events, cursor, self.hotkey_ok, self.hotkey_label

    def request_prepare(self) -> str:
        request_id = uuid.uuid4().hex
        with self._lock:
            self.prepare_id = request_id
            self.prepare_ack = None
            self._event({"type": "prepare", "request_id": request_id})
            return request_id

    def ack_prepare(self, request_id: str) -> None:
        with self._lock:
            if request_id and request_id == self.prepare_id:
                self.prepare_ack = request_id

    def prepare_ready(self, request_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            online = sum(1 for seen in self.pulses.values() if now - seen < 2.5)
            if online == 0:
                return True
            return self.prepare_ack == request_id

    def _event(self, payload: dict) -> dict:
        self._seq += 1
        item = {"seq": self._seq, **payload}
        self.events.append(item)
        if len(self.events) > 200:
            self.events = self.events[-200:]
        return item
