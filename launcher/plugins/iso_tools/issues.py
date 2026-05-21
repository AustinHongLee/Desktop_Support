from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


IssueState = Literal["ready", "warn", "blocked", "pending", "running"]


@dataclass(frozen=True)
class ChecklistIssue:
    key: str
    code: str
    state: IssueState
    title: str
    detail: str
    blocks_run: bool = False


def issue_state_text(state: IssueState) -> str:
    return {
        "ready": "OK",
        "warn": "注意",
        "blocked": "阻擋",
        "running": "執行中",
        "pending": "待檢查",
    }.get(state, state)
