# ISO PDF Node-Based Workflow Pilot Brief for Opus 4.8 Max

> Date: 2026-06-09
> Branch: `codex/tauri-react-spike`
> Goal: build a first node-based workflow POC for the existing ISO PDF flow.
> UI goal: no node canvas yet. CLI first; React Flow / LiteGraph / Rete.js later.

## 0. Executive Decision

Node-based workflow should become the full-power layer behind the existing ISO PDF modes:

| Mode | Role | Relationship to graph |
|---|---|---|
| 一鍵 | user-safe execution | Runs a sealed default workflow template. |
| 工作台 | review and correction | Reads intermediate graph outputs and reruns selected safe nodes. |
| 調校 | engineer tuning | Edits node params such as ROI, threshold, columns, profile. |
| 節點式 | architect / full-control | Edits graph structure, node params, replay strategy, and side-effect execution. |

Important framing:

- Do not replace 一鍵 / 工作台 / 調校.
- Build the workflow engine underneath them.
- The first UI exposure should be hidden behind 調校 > 進階, or CLI only.
- Node mode has all identities, so it must mark dangerous nodes clearly and default to dry-run / replay-safe behavior.

Recommended pilot path:

1. Build a small generic DAG engine.
2. Wrap the current ISO PDF backend actions as nodes.
3. Run one safe default graph from JSON.
4. Write `run_log.json` with per-node inputs, outputs, errors, timings, and side effects.
5. Do not build the visual node editor yet.

## 1. Current ISO PDF Flow

Current truth sources:

- `docs/iso_pdf_current_status.md`
- `docs/iso_pdf_pilot_uplift_handoff_codex_2026-06-09.md`
- `launcher/app/tauri_iso_workflow.py`
- `launcher/app/tauri_iso_worker.py`
- `launcher/plugins/iso_tools/*`
- `frontend/tauri-spike/src/isoWorkflow.ts`
- `frontend/tauri-spike/src/iso/IsoBoard.tsx`

### 1.0 Branch and Workspace Order

Before implementing, verify the local branch state instead of trusting stale handoff text:

```powershell
git status --short --branch
git log --oneline -8
git rev-parse HEAD origin/codex/tauri-react-spike
```

Expected current line as of this brief:

- Branch: `codex/tauri-react-spike`
- ISO Pilot uplift is already committed and pushed.
- Recent commits include:
  - `081ed04 docs(iso): archive completed planning notes`
  - `24528a7 docs(iso): summarize pilot uplift completion`
  - `15cf898 fix(iso): debounce roi preview while tuning`
  - `6bfb7db fix(iso): keep batch pilot freshness aligned`
  - `9604205 feat(iso): refine tuning layout and autopilot guidance`
  - `9247dbf feat(iso): add pilot list panel and P13-P15 calibration checks`

If the implementation workspace shows uncommitted Pilot uplift files, stop and reconcile first. Do not stack the node workflow POC on top of unrelated uncommitted Pilot / UI changes.

Recommended branch strategy:

```text
base: codex/tauri-react-spike after Pilot uplift commits
work branch: codex/iso-node-workflow-poc
```

The node workflow POC should not touch `.qwen/` or unrelated docs.

### 1.1 Inputs

The current request payload is centered on `IsoWorkflowRequest` in `launcher/app/tauri_iso_workflow.py`.

Core inputs:

| Input | Meaning |
|---|---|
| `work_folder` | Main user-selected folder, used for discovery and profile lookup. |
| `profile_folder` | Explicit profile scope when different from work folder. |
| `combine_pdf` | Combined source PDF to split or inspect. |
| `page_folder` | Existing folder of single-page PDFs. |
| `iso_list` | Excel / CSV ISO list. |
| `sheet_name` | ISO workbook sheet. |
| `serial_col` | Column index for serial number. |
| `line_col` | Column index for drawing / file basename / line. |
| `pattern` | Rename pattern, usually `{serial}--{line}.pdf`. |
| `serial_region` | ROI for serial OCR. |
| `drawing_region` | ROI for drawing OCR / visual crop. |
| `confidence_threshold` | OCR acceptance threshold. |
| `detect_serials` | Whether to run image-based serial detection. |
| `rows` | Current plan rows passed back for export/apply/pilot. |
| `run_id` | Existing ISO run log id. |
| `job_id` | Batch OCR worker job id. |
| `export_path` | CSV or debug bundle export destination. |

### 1.2 Main Current Flows

Autopilot 一鍵:

```text
choose source
  -> start_batch_detect(detect_serials=true)
  -> poll job_status until completed
  -> receive batch_detect_result with rows + pilot_results
  -> if blocked/warn: move to review/workbench
  -> export_plan_csv
  -> apply selected ready rows
  -> update UI and run log
```

Workbench 工作台:

```text
load/discover sources
  -> split_pdf or use existing pages
  -> load_iso_table
  -> plan / build_rename_plan
  -> show rows, issues, PilotStrip
  -> export_plan_csv
  -> apply selected rows after confirmation
```

Engineer 調校:

```text
load profile / draft
  -> edit columns, pattern, threshold, ROI
  -> preview / roi_distribution / pilot_report
  -> save_draft_profile
  -> publish_profile or revert_profile
  -> rerun plan / batch detect
```

### 1.3 Existing Backend Actions and Side Effects

| Action / function | Reads | Outputs | Side effects | Node candidate |
|---|---|---|---|---|
| `discover_sources` | folders, profile store | profile payload, candidates | reads state store only | `DiscoverSourcesNode` |
| `split_pdf` / `_resolve_pdfs` | PDF / folder | page list | may create `*_pages` PDFs | `SplitPdfNode` / `ResolvePdfPagesNode` |
| `load_iso_table` | Excel / CSV | headers, records sample, sheet metadata | none | `LoadIsoListNode` |
| `plan` / `build_iso_plan` | PDFs, ISO list, profile, optional OCR | rows, summary, issues, pilot | may split PDF through `_resolve_pdfs`; may write run log when called through CLI bridge | `BuildPlanNode` |
| `build_rename_plan` | same as plan | rows with rename targets | same caveat as plan | `BuildRenamePlanNode` |
| `start_batch_detect` | request | job payload | writes job files, request JSON, run log; spawns worker subprocess | `BatchDetectSerialNode` |
| `job_status` | job dir | job payload | none | `JobStatusNode` |
| `cancel_job` | job dir | job payload | writes `cancel.json`, updates job | `CancelJobNode` |
| `pilot_report` | rows or plan request | P01-P15 report | can call plan if rows absent | `PilotReportNode` |
| `roi_distribution` | rows or plan request | confidence distribution | can call plan if rows absent | `RoiDistributionNode` |
| `export_plan_csv` | rows / plan | export metadata | writes CSV | `ExportPlanCsvNode` |
| `apply` / `_apply_operations` | selected rows | rename result | renames files | `ApplyRenameNode` |
| `load_profile` | state store | profile payload | none | `LoadProfileNode` |
| `save_profile` | state store | profile payload | writes published profile | `SaveProfileNode` |
| `save_draft_profile` | state store | profile payload | writes draft profile | `SaveDraftProfileNode` |
| `publish_profile` | state store | profile payload | writes published profile, changes profile state | `PublishProfileNode` |
| `revert_profile` | state store | profile payload | mutates profile state | `RevertProfileNode` |
| `list_run_logs` | run log folder | run summaries | none | `ListRunLogsNode` |
| `read_run_log` | run log folder | run details | none | `ReadRunLogNode` |
| `replay_run_log` | run log request snapshot | dry-run plan | may call plan and inherit plan side effects | `ReplayRunLogNode` |
| `export_debug_bundle` | run log folder | zip metadata | writes debug bundle zip | `ExportDebugBundleNode` |

Important finding:

`plan` currently is not purely read-only, because `_resolve_pdfs()` can split a combine PDF when no page folder exists. For the POC this can be documented as `side_effects: ["may_write_page_pdfs"]`. Long term, split this into:

```text
ResolvePdfSourceNode: read-only, finds existing pages / combine PDF
SplitPdfNode: explicit write node, creates pages
BuildPlanNode: read-only after pages are resolved
```

### 1.4 Environment and Verification Notes

The target operator environment is Windows + PowerShell. However, the model or sandbox doing the build may have limits. Record them instead of pretending validation happened.

Known possible constraints from prior runs:

- `pytest` may not be installed.
- Full Vite / Tauri build may be unavailable or too slow.
- Some hosted sandboxes cannot commit or push to git.
- Windows path edits may not sync correctly when a Linux-mounted workspace is used. Prefer direct workspace file edits in the active environment and verify with `git diff`.
- If a command cannot run, write the exact command attempted, exact failure, and the fallback validation used.

Minimum acceptable verification ladder:

1. Static graph unit tests if `pytest` is available.
2. CLI `validate` against the sample workflow JSON.
3. CLI `list-nodes`.
4. CLI dry-run / replay tests that do not rename files.
5. If fixture data is available, run the safe workflow without `ApplyRenameNode`.

Do not claim the workflow POC is fully verified unless at least the graph validation and CLI paths ran successfully.

## 2. Architecture Possibilities

### Option A - Adapter Wrapper Over Existing ISO Actions

Build nodes that call existing `tauri_iso_workflow` actions.

Pros:

- Lowest risk.
- Does not rewrite business logic.
- Fastest path to a running POC.
- Matches current Tauri action schema.

Cons:

- Some nodes are coarse.
- Existing side effects stay bundled inside actions.
- `start_batch_detect` remains async job based.

Verdict: recommended for first pilot.

### Option B - Extract Pure Domain Functions Into Native Nodes

Split `_resolve_pdfs`, `_resolve_iso_records`, `_build_plan_rows`, `build_pilot_report`, and profile operations into first-class node implementations.

Pros:

- Cleaner graph semantics.
- Better replay and partial rerun.
- Side effects can be isolated accurately.

Cons:

- Higher refactor risk.
- More tests required before UI work.
- Easy to accidentally break current 一鍵.

Verdict: do after Option A proves the workflow engine shape.

### Option C - Generic Desktop Support Workflow Engine

Make a reusable engine for ISO PDF, shutdown safety, cleanup, locks, and future tools.

Pros:

- Good long-term architecture.
- Shared run log / replay / graph UI.

Cons:

- Too broad for a first pilot.
- Risk of abstracting before one real graph proves the model.

Verdict: design the engine generically, but implement only ISO PDF in the POC.

## 3. Recommended First Folder Structure

Keep the POC inside the ISO plugin boundary first. Avoid top-level framework churn.

```text
launcher/plugins/iso_tools/workflow/
  __init__.py
  cli.py
  schema.py
  context.py
  engine/
    __init__.py
    graph.py
    executor.py
    run_log.py
  nodes/
    __init__.py
    base.py
    registry.py
    sources.py
    pdf.py
    iso_list.py
    detection.py
    plan.py
    pilot.py
    profile.py
    export.py
    apply.py
  adapters/
    __init__.py
    tauri_iso_workflow_adapter.py
  workflows/
    iso_pdf_safe_poc.workflow.json
  logs/
    .gitkeep
  ui/
    README.md
tests/
  test_iso_node_workflow_engine.py
  test_iso_node_workflow_poc.py
```

The `ui/` folder is intentionally a placeholder. It exists only to reserve the future boundary.

## 4. Node Contract

Each node should have this shape:

```python
class WorkflowNode:
    node_id: str
    node_type: str
    display_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    params: dict[str, Any]
    side_effects: list[str]

    def validate(self, context: WorkflowContext) -> list[ValidationIssue]:
        ...

    def run(self, context: WorkflowContext) -> NodeRunResult:
        ...
```

Minimum dataclasses:

```python
@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    node_type: str
    display_name: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    params: dict[str, Any]
    side_effects: tuple[str, ...] = ()
    enabled: bool = True
    requires_confirm: bool = False

@dataclass(frozen=True)
class EdgeSpec:
    from_node: str
    from_output: str
    to_node: str
    to_input: str

@dataclass
class NodeRunResult:
    node_id: str
    status: str  # pending/running/completed/skipped/failed/blocked
    outputs: dict[str, Any]
    logs: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    side_effects: list[dict[str, Any]]
    started_at: str
    ended_at: str
    duration_ms: int
```

Context rules:

- Context stores JSON-safe artifacts only.
- Large files are represented by path + optional hash, not embedded bytes.
- Each node reads from named inputs and writes to named outputs.
- Nodes must not silently mutate upstream artifacts.
- Side-effect nodes must log exactly what they wrote or changed.

## 5. Workflow Graph Requirements

The engine must support:

- Load workflow JSON.
- Save workflow JSON.
- Validate graph:
  - unique `node_id`
  - known `node_type`
  - edge endpoints exist
  - required inputs resolvable from workflow inputs or upstream outputs
  - cycle detection
- DAG topological sort.
- Execute whole graph.
- Execute one node with a supplied context / prior run log.
- Skip disabled nodes.
- Enforce two levels of side-effect policy:
  - auto-allowed side effects may run after being logged and summarized.
  - guarded side effects require `--confirm-side-effects` or a node-specific confirmation.
- Produce `run_log.json`.
- Replay from `run_log.json`:
  - default replay skips all side-effect nodes
  - explicit replay can rerun auto-allowed side effects only when requested
  - guarded side effects still require confirmation during replay

## 6. First Node List

### 6.1 Safe / Replay-Friendly Nodes

| node_type | display_name | Inputs | Outputs | Notes |
|---|---|---|---|---|
| `iso.discover_sources` | 探索來源 | `work_folder`, optional paths | `profile`, `candidates` | Wrap `discover_sources`. |
| `iso.load_profile` | 載入 Profile | folder/path inputs | `profile` | Read-only. |
| `iso.load_iso_table` | 載入 ISO List | `iso_list`, `sheet_name`, columns | `headers`, `sample_records`, `source` | Wrap `load_iso_table`. |
| `iso.build_rename_plan` | 產生命名草稿 | source/profile/ISO params | `plan`, `rows`, `summary`, `issues` | Mark as `may_write_page_pdfs` until split is explicit. |
| `iso.pilot_report` | Pilot 檢查 | rows or plan | `pilot_results`, `pilot_summary` | Prefer rows input so it stays pure. |
| `iso.roi_distribution` | 多頁採樣 | rows, threshold | `distribution` | Prefer rows input. |
| `iso.read_run_log` | 讀取 Run Log | `run_id` | `run` | Read-only. |
| `iso.replay_run_log` | 回放試算 | `run_id` | `plan` | Dry-run by contract, but watch plan split caveat. |

### 6.2 Side-Effect Nodes

| node_type | display_name | Inputs | Outputs | Side effects | Default |
|---|---|---|---|---|---|
| `iso.split_pdf` | 拆頁 PDF | `combine_pdf` | `pages`, `page_folder` | writes page PDFs | auto-allowed with log |
| `iso.batch_detect_serials` | 批次判讀流水號 | source/ISO/ROI params | `job`, `rows`, `plan` | writes job files, run logs, spawns worker | auto-allowed, wait by default |
| `iso.export_plan_csv` | 匯出 CSV | rows | `export_path` | writes CSV | auto-allowed |
| `iso.export_debug_bundle` | 匯出問題包 | run_id | zip path | writes zip | auto-allowed |
| `iso.apply_rename` | 套用更名 | selected rows | result | renames files | disabled / guarded confirm required |
| `iso.save_draft_profile` | 儲存草稿 | profile params | profile | writes state store | guarded confirm or engineer unlock |
| `iso.publish_profile` | 發布 Profile | profile params | profile | writes state store | guarded confirm required |
| `iso.revert_profile` | 回復 Profile | folder | profile | writes state store | guarded confirm required |

## 7. Example Workflow JSON

This is the recommended first safe workflow. It runs through planning, Pilot, ROI distribution, and CSV export. It does not apply rename.

```json
{
  "schema_version": 1,
  "workflow_id": "iso_pdf_safe_poc",
  "display_name": "ISO PDF safe node workflow POC",
  "description": "Safe first graph: discover -> load ISO -> batch detect -> plan -> pilot -> export CSV. No apply by default.",
  "inputs": {
    "work_folder": "",
    "combine_pdf": "",
    "page_folder": "",
    "iso_list": "",
    "sheet_name": "",
    "serial_col": null,
    "line_col": null,
    "pattern": "{serial}--{line}.pdf",
    "detect_serials": true,
    "confidence_threshold": 0.7,
    "serial_region": null,
    "drawing_region": null
  },
  "nodes": [
    {
      "node_id": "discover",
      "node_type": "iso.discover_sources",
      "display_name": "探索來源",
      "inputs": {
        "work_folder": "$workflow.inputs.work_folder",
        "combine_pdf": "$workflow.inputs.combine_pdf",
        "page_folder": "$workflow.inputs.page_folder",
        "iso_list": "$workflow.inputs.iso_list"
      },
      "outputs": {
        "profile": "profile",
        "candidates": "candidates"
      },
      "params": {}
    },
    {
      "node_id": "load_iso",
      "node_type": "iso.load_iso_table",
      "display_name": "載入 ISO List",
      "inputs": {
        "work_folder": "$workflow.inputs.work_folder",
        "iso_list": "$workflow.inputs.iso_list",
        "sheet_name": "$workflow.inputs.sheet_name",
        "serial_col": "$workflow.inputs.serial_col",
        "line_col": "$workflow.inputs.line_col"
      },
      "outputs": {
        "source": "iso_source",
        "sample_records": "sample_records"
      },
      "params": {}
    },
    {
      "node_id": "batch_detect",
      "node_type": "iso.batch_detect_serials",
      "display_name": "批次判讀流水號",
      "inputs": {
        "work_folder": "$workflow.inputs.work_folder",
        "combine_pdf": "$workflow.inputs.combine_pdf",
        "page_folder": "$workflow.inputs.page_folder",
        "iso_list": "$workflow.inputs.iso_list",
        "sheet_name": "$workflow.inputs.sheet_name",
        "serial_col": "$workflow.inputs.serial_col",
        "line_col": "$workflow.inputs.line_col",
        "pattern": "$workflow.inputs.pattern",
        "detect_serials": "$workflow.inputs.detect_serials",
        "confidence_threshold": "$workflow.inputs.confidence_threshold",
        "serial_region": "$workflow.inputs.serial_region",
        "drawing_region": "$workflow.inputs.drawing_region"
      },
      "outputs": {
        "rows": "rows",
        "plan": "plan",
        "run_log": "run_log"
      },
      "params": {
        "wait_for_completion": true,
        "poll_interval_ms": 400,
        "timeout_s": 900
      },
      "side_effects": [
        "writes_job_files",
        "writes_iso_run_log",
        "spawns_worker",
        "may_write_page_pdfs"
      ]
    },
    {
      "node_id": "pilot",
      "node_type": "iso.pilot_report",
      "display_name": "Pilot 檢查",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "plan": "$nodes.batch_detect.outputs.plan"
      },
      "outputs": {
        "pilot_results": "pilot_results",
        "pilot_summary": "pilot_summary"
      },
      "params": {}
    },
    {
      "node_id": "roi_distribution",
      "node_type": "iso.roi_distribution",
      "display_name": "多頁信心分布",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "confidence_threshold": "$workflow.inputs.confidence_threshold"
      },
      "outputs": {
        "distribution": "roi_distribution"
      },
      "params": {}
    },
    {
      "node_id": "export_csv",
      "node_type": "iso.export_plan_csv",
      "display_name": "匯出命名草稿 CSV",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "work_folder": "$workflow.inputs.work_folder",
        "combine_pdf": "$workflow.inputs.combine_pdf",
        "page_folder": "$workflow.inputs.page_folder",
        "iso_list": "$workflow.inputs.iso_list"
      },
      "outputs": {
        "export_path": "export_path"
      },
      "params": {},
      "side_effects": [
        "writes_csv"
      ]
    },
    {
      "node_id": "apply_rename",
      "node_type": "iso.apply_rename",
      "display_name": "套用更名",
      "enabled": false,
      "requires_confirm": true,
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows"
      },
      "outputs": {
        "renamed": "renamed"
      },
      "params": {
        "only_ready": true
      },
      "side_effects": [
        "renames_files"
      ]
    }
  ],
  "edges": [
    { "from_node": "batch_detect", "from_output": "rows", "to_node": "pilot", "to_input": "rows" },
    { "from_node": "batch_detect", "from_output": "plan", "to_node": "pilot", "to_input": "plan" },
    { "from_node": "batch_detect", "from_output": "rows", "to_node": "roi_distribution", "to_input": "rows" },
    { "from_node": "batch_detect", "from_output": "rows", "to_node": "export_csv", "to_input": "rows" }
  ]
}
```

The example includes edges even though input refs are explicit. That is intentional: edges support future graph UI and DAG validation.

## 8. CLI POC Commands

Minimum CLI:

```powershell
python -m launcher.plugins.iso_tools.workflow.cli list-nodes
python -m launcher.plugins.iso_tools.workflow.cli validate --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json
python -m launcher.plugins.iso_tools.workflow.cli run --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json --inputs sample_inputs.json --out .runtime/workflow-runs
python -m launcher.plugins.iso_tools.workflow.cli run-node --run-log .runtime/workflow-runs/<run_id>/run_log.json --node pilot
python -m launcher.plugins.iso_tools.workflow.cli replay --run-log .runtime/workflow-runs/<run_id>/run_log.json --skip-side-effects
```

`sample_inputs.json` shape:

```json
{
  "work_folder": "C:/Users/a0976/Downloads/t",
  "combine_pdf": "C:/Users/a0976/Downloads/t/testing.pdf",
  "page_folder": "C:/Users/a0976/Downloads/t/testing_pages",
  "iso_list": "C:/Users/a0976/Downloads/t/HP6精準...xlsx",
  "sheet_name": "DWG NO.ALL",
  "serial_col": null,
  "line_col": null,
  "pattern": "{serial}--{line}.pdf",
  "detect_serials": true,
  "confidence_threshold": 0.7
}
```

Do not hard-code the sample paths into tests. They are only an operator example.

## 9. Run Log Shape

Write workflow run logs separately from existing ISO run logs:

```text
.runtime/workflow-runs/<workflow_run_id>/run_log.json
.runtime/workflow-runs/<workflow_run_id>/events.jsonl
.runtime/workflow-runs/<workflow_run_id>/artifacts/
```

Minimum `run_log.json`:

```json
{
  "schema_version": 1,
  "workflow_run_id": "wf-20260609-120000-ab12cd",
  "workflow_id": "iso_pdf_safe_poc",
  "status": "completed",
  "started_at": "...",
  "ended_at": "...",
  "inputs": {},
  "workflow": {},
  "topology": ["discover", "load_iso", "batch_detect", "pilot", "roi_distribution", "export_csv"],
  "nodes": {
    "batch_detect": {
      "status": "completed",
      "started_at": "...",
      "ended_at": "...",
      "duration_ms": 12345,
      "inputs": {},
      "outputs": {
        "rows": { "artifact_ref": "artifacts/batch_detect.rows.json" },
        "plan": { "artifact_ref": "artifacts/batch_detect.plan.json" }
      },
      "side_effects": [
        { "type": "writes_job_files", "path": ".runtime/jobs/iso/..." },
        { "type": "writes_iso_run_log", "run_id": "iso-..." }
      ],
      "logs": [],
      "errors": []
    }
  }
}
```

Artifact policy:

- Small JSON payloads may be embedded.
- Rows, plans, Pilot reports, and job payloads should be stored as artifact JSON files once they become large.
- Binary files are never embedded.

## 10. Safety Rules

Non-negotiable:

1. Do not change `run_iso_workflow` existing action schema.
2. Pilot contract wording:
   - `P01`-`P12` id / stage are frozen.
   - `P13`-`P15` are append-only additions from the Pilot uplift.
   - New checks must append after `P15`; do not renumber or reorder existing items.
3. Do not remove PyQt legacy.
4. Do not make 一鍵 more complex.
5. Do not make `ApplyRenameNode` enabled by default.
6. Do not run guarded side-effect nodes during replay unless explicitly confirmed.
7. Do not rerun OCR on every slider movement. Node workflow must not reintroduce the old ROI freeze behavior.
8. Do not write graph UI before CLI POC and tests exist.

Side-effect policy:

| Policy | Categories | Default run | Default replay |
|---|---|---|---|
| `read_only` | `read_only` | allowed | allowed |
| `auto_allowed` | `may_write_page_pdfs`, `writes_job_files`, `writes_iso_run_log`, `writes_csv`, `writes_debug_bundle`, `spawns_worker`, `external_process` when non-destructive | allowed after summary + log | skipped unless `--include-auto-side-effects` |
| `guarded` | `renames_files`, `writes_profile`, destructive external process | blocked unless confirmed | blocked unless confirmed |

Side-effect categories are:

```text
read_only
may_write_page_pdfs
writes_job_files
spawns_worker
writes_iso_run_log
writes_csv
writes_debug_bundle
writes_profile
renames_files
external_process
```

The executor must print a side-effect summary before running any node with side effects and must write the same summary into `run_log.json`.

## 11. First Implementation Plan for Opus

### Phase 1 - Static Graph Engine

Deliver:

- `schema.py` dataclasses and JSON load/save.
- Node registry.
- DAG validation.
- Topological sort.
- Unit tests for:
  - valid graph
  - duplicate node ids
  - unknown node type
  - missing edge endpoint
  - cycle detection

No ISO business logic yet.

### Phase 2 - ISO Action Adapter Nodes

Deliver:

- Adapter that can call existing ISO action handlers with an `IsoWorkflowRequest`.
- Typed node wrappers for:
  - `iso.discover_sources`
  - `iso.load_iso_table`
  - `iso.batch_detect_serials`
  - `iso.pilot_report`
  - `iso.roi_distribution`
  - `iso.export_plan_csv`
- For `iso.batch_detect_serials`, support `wait_for_completion=true` by polling `job_status`.

Implementation note:

- In-process calls are acceptable for the POC.
- If in-process calls skip existing ISO run log behavior, the workflow run log must still capture enough replay data.
- Long term, the adapter can switch between in-process and subprocess bridge.

Acceptance gate:

- Prove whether the adapter triggers existing ISO run log behavior for each wrapped action.
- If it does not, record that explicitly and compensate in workflow run log artifacts.
- For `iso.batch_detect_serials`, prove that job files, worker execution, and ISO run log references are captured in the node run result.

### Phase 3 - CLI and Run Logs

Deliver:

- `list-nodes`
- `validate`
- `run`
- `run-node`
- `replay`
- `run_log.json`
- `events.jsonl`
- JSON artifacts for large node outputs.

### Phase 4 - Safe POC Workflow

Deliver:

- `iso_pdf_safe_poc.workflow.json`
- It must run without `ApplyRenameNode`.
- It must output:
  - rows
  - summary
  - Pilot P01-P15
  - ROI distribution
  - CSV path
  - workflow run log

### Phase 5 - Tests and Handoff

Deliver:

- Focused pytest suite.
- If `pytest` is unavailable, provide equivalent CLI smoke commands and exact environment limitation.
- One markdown handoff with:
  - what works
  - commands run
  - remaining risks
  - whether side effects were triggered
  - proof that side effects were logged, or proof that they were blocked/skipped
  - proof that replay skips side effects by default

## 12. Later UI Bridge

React Flow / LiteGraph / Rete.js should not call Python node classes directly. The frontend should see a graph API:

```ts
type WorkflowGraph = {
  schema_version: number;
  workflow_id: string;
  display_name: string;
  inputs: Record<string, unknown>;
  nodes: WorkflowNodeSpec[];
  edges: WorkflowEdgeSpec[];
};

type WorkflowNodeSpec = {
  node_id: string;
  node_type: string;
  display_name: string;
  inputs: Record<string, unknown>;
  outputs: Record<string, string>;
  params: Record<string, unknown>;
  side_effects: string[];
  enabled: boolean;
  requires_confirm: boolean;
};
```

Future Tauri actions:

| Action | Purpose |
|---|---|
| `workflow_list_templates` | List saved workflow templates. |
| `workflow_load` | Load workflow JSON. |
| `workflow_validate` | Validate graph. |
| `workflow_run` | Execute whole graph. |
| `workflow_run_node` | Execute one node. |
| `workflow_replay` | Replay from run log. |
| `workflow_cancel` | Cancel active workflow run. |
| `workflow_read_run_log` | Read workflow run log. |

UI mapping:

- 一鍵 uses a locked `iso_pdf_default.workflow.json`.
- 工作台 reads node outputs like `rows`, `summary`, `pilot_results`.
- 調校 edits node params like ROI / threshold / columns / profile.
- 節點式 edits `nodes` and `edges`, but starts as a hidden advanced view.

## 13. Prompt for Opus 4.8 Max

Use this as the next-model instruction:

```text
請先閱讀：
- docs/iso_pdf_current_status.md
- docs/iso_pdf_pilot_uplift_handoff_codex_2026-06-09.md
- docs/iso_pdf_node_workflow_pilot_brief_opus_2026-06-09.md
- launcher/app/tauri_iso_workflow.py
- launcher/app/tauri_iso_worker.py
- launcher/plugins/iso_tools/*
- frontend/tauri-spike/src/isoWorkflow.ts

目標：只針對 ISO PDF 做 Node-Based Workflow POC。不要做視覺節點 UI，不要重寫一鍵/工作台/調校，不要破壞現有 run_iso_workflow action schema。

請實作：
1. launcher/plugins/iso_tools/workflow/ 底下的 graph schema、node registry、DAG validation、topological sort、executor、workflow run log。
2. ISO action adapter nodes，先包裝現有函式，不重寫業務邏輯。
3. CLI：
   - list-nodes
   - validate
   - run
   - run-node
   - replay
4. workflow JSON 範例：iso_pdf_safe_poc.workflow.json。
5. 測試：
   - graph validation / cycle detection
   - safe workflow can execute with fixture or temporary test data
   - guarded side-effect nodes are blocked unless confirmed
   - auto-allowed side effects are summarized and logged
   - replay skips side effects by default

限制：
- ApplyRenameNode 預設 disabled / requires_confirm。
- replay 不可執行 renames_files。
- Pilot P01-P12 id / stage 凍結；P13-P15 是 append-only，後續只能再 append，不可重排或重編號。
- 不移除 PyQt legacy。
- 不做 React Flow UI。
- 文件與測試要清楚列出哪些節點有 side effects。
- 開工前先跑 git status / git log / rev-parse，確認 Pilot uplift 已在基底分支，避免疊在未提交工作樹上。
- 若環境沒有 pytest、不能 commit、不能跑完整 build，要在 handoff 寫明限制與替代驗證。

完成後回報：
- 新增/修改檔案
- CLI 使用方式
- 實際跑過的測試
- side-effect 行為證明，包括 auto-allowed 與 guarded 兩層
- 下一步如何接 React Flow / LiteGraph / Rete.js
```
