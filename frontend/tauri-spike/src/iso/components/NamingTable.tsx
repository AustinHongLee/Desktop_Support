import type { IsoPlanRow } from "../../isoWorkflow";
import { isoIssueKind, isoIssueLabel, localizeIsoDisplayText } from "../helpers";

export function IsoPlanTable({
  rows,
  selectedRowId,
  selectRow,
  toggleRow,
  toggleAll,
  updateRow,
}: {
  rows: IsoPlanRow[];
  selectedRowId: string;
  selectRow: (rowId: string) => void;
  toggleRow: (rowId: string) => void;
  toggleAll: (select: boolean) => void;
  updateRow: (rowId: string, field: "serial" | "line_no" | "new_name", value: string) => void;
}) {
  const selectable = rows.filter((row) => row.status !== "blocked");
  const allSelected = selectable.length > 0 && selectable.every((row) => row.selected);
  const statusLabel = (status: IsoPlanRow["status"]) => status === "ready" ? "通過" : status === "warn" ? "待確認" : status === "blocked" ? "需處理" : status;
  return (
    <div className="iso-table live">
      <div className="iso-table-head">
        <label className="row-check" title="全選 / 全不選（不含需處理）" onClick={(event) => event.stopPropagation()}>
          <input type="checkbox" checked={allSelected} onChange={(event) => toggleAll(event.target.checked)} />
        </label>
        <span>頁</span>
        <span>原檔名</span>
        <span>流水號</span>
        <span>圖號</span>
        <span>信心</span>
        <span>狀態</span>
        <span>新檔名</span>
      </div>
      {rows.map((row) => (
        <div className={`iso-table-row ${row.status} ${isoIssueKind(row)} ${selectedRowId === row.id ? "selected" : ""}`} key={row.id} onClick={() => selectRow(row.id)}>
          <label className="row-check">
            <input type="checkbox" checked={row.selected} disabled={row.status === "blocked"} onChange={() => toggleRow(row.id)} onClick={(event) => event.stopPropagation()} />
          </label>
          <span>{String(row.page).padStart(3, "0")}</span>
          <strong title={row.source_path}>{row.source_name}</strong>
          <input className="table-cell-input serial" value={row.serial} onChange={(event) => updateRow(row.id, "serial", event.target.value)} onClick={(event) => event.stopPropagation()} />
          <input className="table-cell-input" value={row.line_no} onChange={(event) => updateRow(row.id, "line_no", event.target.value)} onClick={(event) => event.stopPropagation()} />
          <span className={`confidence-chip ${row.confidence >= 0.8 ? "ready" : row.confidence > 0 ? "warn" : "idle"}`}>{row.confidence ? `${Math.round(row.confidence * 100)}%` : "-"}</span>
          <span className={`plan-state ${row.status}`} title={localizeIsoDisplayText(row.note || isoIssueLabel(row))}>
            {statusLabel(row.status)}
            {row.note === "manual corrected" ? <em className="row-review-flag">未確認</em> : null}
          </span>
          <input className="table-cell-input mono" value={row.new_name} title={row.note ? localizeIsoDisplayText(row.note) : row.target_path} onChange={(event) => updateRow(row.id, "new_name", event.target.value)} onClick={(event) => event.stopPropagation()} />
        </div>
      ))}
    </div>
  );
}
