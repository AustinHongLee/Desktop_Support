from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from launcher.plugins.iso_tools.workflow.errors import UndeclaredSideEffectError

MAY_WRITE_PAGE_PDFS = "may_write_page_pdfs"
WRITES_JOB_FILES = "writes_job_files"
WRITES_ISO_RUN_LOG = "writes_iso_run_log"
WRITES_CSV = "writes_csv"
WRITES_DEBUG_BUNDLE = "writes_debug_bundle"
SPAWNS_WORKER = "spawns_worker"
RENAMES_FILES = "renames_files"
WRITES_PROFILE = "writes_profile"

AUTO_ALLOWED = frozenset(
    {
        MAY_WRITE_PAGE_PDFS,
        WRITES_JOB_FILES,
        WRITES_ISO_RUN_LOG,
        WRITES_DEBUG_BUNDLE,
        SPAWNS_WORKER,
    }
)
GUARDED = frozenset({RENAMES_FILES, WRITES_PROFILE, WRITES_CSV})
REPLAY_HARD_BLOCKED = frozenset({RENAMES_FILES, WRITES_PROFILE, WRITES_CSV})
KNOWN_SIDE_EFFECTS = AUTO_ALLOWED | GUARDED


@dataclass(frozen=True)
class SideEffectPolicy:
    mode: str = "run"
    allowed_guarded: frozenset[str] = frozenset()
    confirmed_nodes: frozenset[str] = frozenset()
    include_auto_in_replay: bool = False

    def to_payload(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "allowed_guarded": sorted(self.allowed_guarded),
            "confirmed_nodes": sorted(self.confirmed_nodes),
            "include_auto_in_replay": self.include_auto_in_replay,
        }


@dataclass(frozen=True)
class SideEffectRecord:
    kind: str
    decision: str
    detail: dict[str, Any] = field(default_factory=dict)
    at: str = ""
    node_id: str = ""

    def to_payload(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "kind": self.kind,
            "decision": self.decision,
            "detail": self.detail,
            "at": self.at,
        }


class SideEffectGate:
    def __init__(
        self,
        *,
        node_id: str,
        declared_effects: tuple[str, ...],
        requires_confirm: bool,
        policy: SideEffectPolicy,
        on_record: Callable[[SideEffectRecord], None] | None = None,
    ) -> None:
        self.node_id = node_id
        self.declared_effects = set(declared_effects)
        self.requires_confirm = requires_confirm
        self.policy = policy
        self.records: list[SideEffectRecord] = []
        self._on_record = on_record

    def request(self, kind: str, detail: dict[str, Any] | None = None) -> str:
        if kind not in self.declared_effects:
            raise UndeclaredSideEffectError(self.node_id, kind)
        decision = self._decision(kind)
        self.record(kind, decision, detail or {})
        return decision

    def record(self, kind: str, decision: str, detail: dict[str, Any] | None = None) -> SideEffectRecord:
        record = SideEffectRecord(
            node_id=self.node_id,
            kind=kind,
            decision=decision,
            detail=detail or {},
            at=datetime.now().isoformat(timespec="seconds"),
        )
        self.records.append(record)
        if self._on_record is not None:
            self._on_record(record)
        return record

    def _decision(self, kind: str) -> str:
        if self.policy.mode == "dry_run":
            return "skipped_dry_run"
        if self.policy.mode == "replay":
            if kind in REPLAY_HARD_BLOCKED:
                return "blocked_replay"
            if kind in AUTO_ALLOWED and self.policy.include_auto_in_replay:
                return "executed"
            return "blocked_replay"
        if kind in AUTO_ALLOWED:
            return "executed"
        if kind in GUARDED:
            if kind not in self.policy.allowed_guarded:
                return "blocked_policy"
            if self.requires_confirm and self.node_id not in self.policy.confirmed_nodes:
                return "blocked_policy"
            return "executed"
        return "blocked_policy"
