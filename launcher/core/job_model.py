from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class JobEvent:
    type: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "JobEvent":
        return cls(
            type=str(payload.get("type") or "message"),
            message=str(payload.get("message") or ""),
            data={key: value for key, value in payload.items() if key not in {"type", "message"}},
        )


@dataclass(frozen=True)
class JobResult:
    action_id: str
    return_code: int
    started_at: datetime
    finished_at: datetime
    events: tuple[JobEvent, ...]

    @property
    def ok(self) -> bool:
        return self.return_code == 0 and not any(
            event.type in {"error", "cancelled", "timeout"} for event in self.events
        )
