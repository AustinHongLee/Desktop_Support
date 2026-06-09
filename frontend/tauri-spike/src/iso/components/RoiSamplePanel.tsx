import { CircleAlert, CircleCheck, ScanLine } from "lucide-react";
import type { IsoPlanRow, IsoRoiDistribution } from "../../isoWorkflow";

export function RoiSamplePanel({
  distribution,
  error = "",
  loading = false,
  rows,
  threshold,
}: {
  distribution?: IsoRoiDistribution | null;
  error?: string;
  loading?: boolean;
  rows: IsoPlanRow[];
  threshold: number;
}) {
  const fallback = buildFallbackDistribution(rows, threshold);
  const data = distribution ?? fallback;
  const weakestRows = [...data.samples]
    .sort((left, right) => (left.confidence || 0) - (right.confidence || 0) || Number(left.page || 0) - Number(right.page || 0))
    .slice(0, 5);

  return (
    <div className="roi-sample-panel">
      <div className="panel-heading compact">
        <div>
          <span>多頁採樣</span>
          <small>
            {loading ? "載入中" : data.total ? `${data.total} 筆 · 門檻 ${Math.round(data.threshold * 100)}%` : "等待資料"}
          </small>
        </div>
      </div>
      {error ? <div className="roi-sample-error">{error}</div> : null}
      <div className="roi-sample-bars" aria-label="ROI 信心分布">
        <SampleBar label="高信心" count={data.ready} total={data.total} tone="ready" />
        <SampleBar label="低信心" count={data.low} total={data.total} tone="warn" />
        <SampleBar label="未判讀" count={data.missing} total={data.total} tone="idle" />
      </div>
      <div className="roi-sample-list">
        {weakestRows.length ? weakestRows.map((row) => (
          <div className="roi-sample-row" key={`${row.index}-${row.page}-${row.source_name}`}>
            {row.bucket === "ready" ? <CircleCheck size={14} /> : row.bucket === "low" ? <CircleAlert size={14} /> : <ScanLine size={14} />}
            <strong>{row.page}</strong>
            <span title={row.source_name}>{row.source_name}</span>
            <code>{row.confidence ? `${Math.round(row.confidence * 100)}%` : "-"}</code>
          </div>
        )) : (
          <div className="roi-sample-empty">等待批次判讀資料</div>
        )}
      </div>
    </div>
  );
}

function buildFallbackDistribution(rows: IsoPlanRow[], threshold: number): IsoRoiDistribution {
  const samples = rows.map((row, index) => {
    const confidence = Number(row.confidence || 0);
    const bucket = confidence >= threshold ? "ready" : confidence > 0 ? "low" : "missing";
    return {
      index,
      page: row.page,
      source_name: row.source_name,
      confidence,
      bucket,
    };
  }) satisfies IsoRoiDistribution["samples"];
  return {
    schema_version: 1,
    action: "roi_distribution",
    created_at: "",
    threshold,
    total: samples.length,
    ready: samples.filter((row) => row.bucket === "ready").length,
    low: samples.filter((row) => row.bucket === "low").length,
    missing: samples.filter((row) => row.bucket === "missing").length,
    samples,
  };
}

function SampleBar({ count, label, tone, total }: { count: number; label: string; tone: "ready" | "warn" | "idle"; total: number }) {
  const percent = total ? Math.round((count / total) * 100) : 0;
  return (
    <div className={`roi-sample-bar ${tone}`}>
      <div>
        <span>{label}</span>
        <strong>{count}</strong>
      </div>
      <div className="roi-sample-track">
        <span style={{ width: `${percent}%` }} />
      </div>
    </div>
  );
}
