from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from launcher.plugins.rename_tools.rename_actions import RenameOperation


CSV_FIELDS = ["apply", "original_name", "new_name", "source_path", "target_path", "status", "note"]


@dataclass(frozen=True)
class RenamePlanRow:
    apply: bool
    source: Path
    target: Path
    status: str
    note: str = ""


@dataclass(frozen=True)
class RenamePlan:
    rows: tuple[RenamePlanRow, ...]

    @property
    def operation_count(self) -> int:
        return sum(1 for row in self.rows if row.apply)

    @property
    def warning_count(self) -> int:
        return sum(1 for row in self.rows if row.note or row.status != "ready")

    def to_csv_text(self) -> str:
        buffer = StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, lineterminator="\n")
        writer.writeheader()
        for row in self.rows:
            writer.writerow(
                {
                    "apply": "YES" if row.apply else "",
                    "original_name": row.source.name,
                    "new_name": row.target.name,
                    "source_path": str(row.source),
                    "target_path": str(row.target),
                    "status": row.status,
                    "note": row.note,
                }
            )
        return buffer.getvalue()

    def write_csv(self, path: Path) -> None:
        path.write_text(self.to_csv_text(), encoding="utf-8-sig")


def build_rename_plan(
    operations: Sequence[RenameOperation],
    review_issues: Mapping[Path, str] | None = None,
) -> RenamePlan:
    issues = review_issues or {}
    rows: list[RenamePlanRow] = []
    for operation in operations:
        note = issues.get(operation.source, "")
        rows.append(
            RenamePlanRow(
                apply=True,
                source=operation.source,
                target=operation.target,
                status="warning" if note else "ready",
                note=note,
            )
        )
    return RenamePlan(tuple(rows))
