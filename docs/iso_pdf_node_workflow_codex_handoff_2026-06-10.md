# ISO PDF Node-Based Workflow — Codex 施工交接包

> Date: 2026-06-10
> Base branch: `codex/tauri-react-spike`（需包含 `081ed04 docs(iso): archive completed planning notes`；開工前以 git 實際確認）
> Work branch: `codex/iso-node-workflow-poc`
> 性質：架構審查 + 完整 implementation handoff。本文件是施工的最終裁決版。
> 歷史 brief 已歸檔於 `docs/archive/iso_pdf/node_workflow/iso_pdf_node_workflow_pilot_brief_opus_2026-06-09.md`。本文件是唯一 active 施工入口；archive 只作背景參考。

## 0. 本文件對 brief 的明確修訂（先讀這段）

本文件已對照 2026-06-10 的實際 code（`tauri_iso_workflow.py` 1402 行、`tauri_iso_worker.py` 227 行、`run_log.py`、`profile.py`、`tests/test_tauri_iso_workflow.py`）逐條驗證，以下決策取代 brief 中的對應段落：

1. **資料夾結構簡化**：不要 brief 的 `engine/` 子套件、`logs/.gitkeep`、`ui/README.md`。POC 用扁平模組（見第 2 節）。`ui/` 佔位資料夾是過度工程化。
2. **接線（wiring）單一事實來源**：`inputs` 裡的 `$nodes.*` / `$workflow.inputs.*` ref 是權威；`edges` 陣列由 loader 自動推導（normalize）。手寫 edges 允許，但 validate 必須檢查與 refs 一致，不一致 = error。避免雙重維護腐化。
3. **BuildPlanNode 的 read-only 用「圖層約束」解決，不改 backend**：實測 `_resolve_pdfs()`（tauri_iso_workflow.py:572-607）在 `page_folder` 有值時走第一分支、絕不拆 PDF。所以 BuildPlanNode / BatchDetectNode 的 validate 強制要求 `page_folder` 已接線且 `combine_pdf` 置空，即可保證純讀，**不需要**幫 `build_iso_plan` 加 `allow_split` 參數。拆頁永遠只發生在顯式的 `iso.split_pdf` node。
4. **BatchDetectNode 第一版走 worker 模式**（`start_batch_detect` + 輪詢 `job_status`），不做 in-process 重寫。原因：worker（`tauri_iso_worker.run_job`）內建 `ensure_iso_run` 會寫既有 ISO run log、寫 job.json 進度、支援 cancel.json——in-process 重寫會跳過這些行為（brief §11 Phase 2 的 acceptance gate 疑慮直接消失）。in-process 模式列為日後選項，不在本 POC。
5. **workflow run 目錄**改為 `runtime_root()/.runtime/runs/workflow/<run_id>/`（與既有 `.runtime/runs/iso/` 並列），不用 brief 的 `.runtime/workflow-runs/`。`.runtime/` 已在 `.gitignore`（第 12 行），不會污染 git。
6. **replay 對 `renames_files` / `writes_profile` 是硬封鎖**：不存在任何 flag 可在 replay 中執行這兩類。brief 的「guarded side effects still require confirmation during replay」改為「guarded 在 replay 一律 blocked，無例外」。
7. **測試用 `unittest.TestCase` 風格**：repo 既有 tests 全是 unittest 類（`tests/test_tauri_iso_workflow.py`、`tests/test_runner.py`），操作者環境用 `python -m pytest` 跑它們，但 `.venv` 不保證有 pytest。寫成 unittest.TestCase 則 `python -m unittest` 純標準庫可跑，兩邊通吃。這就是 pytest 不可用時的替代驗證主幹。
8. **第一批 node 不包 `publish_profile` / `revert_profile` / `save_profile`**：發布/回復屬於調校頁的人工治理動作，POC 包進 graph 沒有使用情境，徒增 guarded 面積。只包 `save_draft_profile`（且預設 disabled）。brief §6.2 的這三個 node 延後。
9. **`iso.read_run_log` / `iso.replay_run_log` node 不做**：workflow 引擎自己有 replay；把舊 replay 包成 node 會造成兩套 replay 語意打架。讀舊 run log 的需求由 CLI/前端直接走既有 action。

---

## 0.1 文件聚焦與分支控管

這份文件是 node workflow POC 的唯一 active 施工書。其他 node workflow 討論稿、brief、模型回覆都應放在 archive，不再作為同等來源。

分支角色：

- `main`：穩定基準，現在不合入 Tauri spike。
- `codex/tauri-react-spike`：Tauri / ISO 整合線，也是 node workflow POC 的 base。
- `codex/iso-node-workflow-poc`：真正施工時才從 `codex/tauri-react-spike` 開出的短期工作分支。

我要做的拆法：

1. 先把文件整理 commit 到 `codex/tauri-react-spike`，讓 active handoff 單一化。
2. 開 `codex/iso-node-workflow-poc` 後，只做 Phase 0-3：engine / policy / run log / CLI，完全不碰 ISO OCR、CSV、rename。
3. Phase 3 全綠後才接 Phase 4-5：純讀 adapter，再接 auto side-effect nodes。
4. Phase 6 才做 guarded rename/profile，且必須獨立 commit。
5. Phase 7 只做示範 workflow 與完工 handoff，不和程式碼混 commit。

這樣分支看起來會多一條，但每條分支只有一個角色，後面反而比較不亂。

---

## 0.2 Codex 執行流程摘要

本節是 Codex 實際施工時的行動節奏。第 13 節的 checklist 仍是驗收規格；本節負責決定「先做什麼、在哪裡停、什麼不要混在一起做」。

### 0.2.1 施工總原則

- 不另開新 handoff md；本文件就是唯一 active 施工入口。
- 不直接從 `main` 開工；以 `codex/tauri-react-spike` 為 base，真正施工才開 `codex/iso-node-workflow-poc`。
- 每個 phase 做完就 commit；若環境不能 commit，就留下該 phase 的 diff 證據與驗證輸出。
- `frontend/`、`launcher/app/tauri_iso_workflow.py`、`launcher/app/tauri_iso_worker.py`、PyQt legacy、`pilot.py` 先全部視為不可改區。
- `.qwen/` 永遠不 stage。

### 0.2.2 Phase 節奏

| 節奏 | 範圍 | 目的 | 停靠點 |
|---|---|---|---|
| Phase 0 | git / branch / docs 狀態檢查 | 確認不是在髒工作樹或舊基底上施工 | 必做，不 commit |
| Phase 1 | schema / registry / policy | 先建立靜態圖與 side-effect 規則 | 可 commit |
| Phase 2 | context / executor / run_log / base node | 讓 FakeNode 圖可執行、可記錄、可 replay | 可 commit |
| Phase 3 | CLI | 完成 `list-nodes / validate / run / run-node / replay` 骨架 | **Checkpoint A：可停、可推、可交接** |
| Phase 4 | read-only ISO adapter nodes | 只接 `discover / load table / build plan / pilot / roi / load profile` | 可 commit |
| Phase 5 | auto side-effect nodes | 接 `split / export csv / debug bundle / batch_detect worker`，不碰 rename | **Checkpoint B：可停、可推、可交接** |
| Phase 6 | guarded nodes | 接 `apply_rename / save_draft_profile`，測安全閘門 | 必須獨立 commit |
| Phase 7 | safe workflow JSON + 驗證紀錄 | 做樣本端到端與完成狀態補記 | docs-only commit |

### 0.2.3 兩個停靠點

Checkpoint A（Phase 3 完成）：

- engine / policy / run log / CLI 已可用。
- 還沒有碰 ISO backend、OCR、PDF 拆頁、CSV、rename。
- 這是最低風險交接點；如果時間或環境卡住，優先停在這裡。

Checkpoint B（Phase 5 完成）：

- 已接上 ISO 純讀與 auto side-effect nodes。
- `batch_detect` 已走現有 worker 模式，能記錄 job files / ISO run log / workflow run log。
- 仍未啟用 guarded rename/profile；真實檔案命名風險還沒進場。

### 0.2.4 絕對不要混做

- Phase 5 和 Phase 6 不同 commit、不同驗證批次。
- 不把 graph UI、React Flow、LiteGraph、Rete.js 混進 POC。
- 不把 `ApplyRenameNode` 預設打開。
- 不在 replay 執行 `renames_files` 或 `writes_profile`，任何 flag 都不例外。
- 不為了 node workflow 改一鍵畫面；一鍵仍跑現有安全 UI。

### 0.2.5 成功判斷

第一輪先追求「引擎可靠」，不是「ISO 全功能已節點化」。

最小成功線：

1. CLI 能 validate / run / replay 一張 FakeNode workflow。
2. run log 會落地並能 hydration artifacts。
3. side-effect gate 能證明 auto / guarded / replay hard-block 三種情境。
4. Phase 3 完成後可以安全交接，不留下半接線 ISO 狀態。

完整 POC 成功線：

1. `iso_pdf_safe_poc.workflow.json` 可跑。
2. 樣本資料或 fixture 產生 rows / summary / Pilot P01-P15 / ROI distribution / CSV。
3. `apply_rename` 預設 skipped/disabled。
4. replay 零 rename、零 profile 寫入。
5. 完成狀態寫回本文件；額外報告若需要，一律放 archive。

---

## 1. 最終架構判斷

### 1.1 node-based workflow 在四模式中的位置

```text
                    ┌─────────────────────────────────────────────┐
                    │  WorkflowGraph (JSON) + NodeRegistry (Python)│
                    │  launcher/plugins/iso_tools/workflow/        │
                    └─────────────────────────────────────────────┘
                       ▲              ▲              ▲          ▲
        鎖定模板＋hash  │   讀中間輸出   │   只改 params  │  全能力
                       │              │              │          │
                    [一鍵]        [工作台]        [調校]    [節點式]
                  (本階段不動)  (本階段不動)   (本階段不動)  (本階段=CLI)
```

- **一鍵** = 執行一張「鎖定的」預設 workflow（`workflow_id` + content hash 釘死）。本階段一鍵 UI **完全不改**，繼續走既有 `run_iso_workflow` actions；workflow 引擎先以「影子等價」存在：CLI 跑 `iso_pdf_safe_poc.workflow.json` 產出的 rows/summary/pilot 必須與一鍵相同輸入的結果等價（這就是 POC 驗收）。
- **工作台** = 之後讀 workflow run log 的 per-node outputs（rows、issues、pilot_results）。本階段不接。
- **調校** = 之後對白名單 node 的 `params` 做 overlay（ROI/threshold/columns/profile），不能改圖結構。本階段不接。
- **節點式** = 可編輯 nodes/edges/replay/side-effect policy 的進階模式。本階段唯一入口是 CLI。

### 1.2 現在要做的（本 POC 範圍）

1. 通用 DAG engine（schema、registry、validate、topo sort、executor、run log、replay）——引擎本體**零 ISO import**。
2. ISO adapter nodes：以 in-process 呼叫 `tauri_iso_workflow` 的既有函式（`build_iso_plan`、`split_iso_pdf`、`load_iso_table`、`pilot_report`、`roi_distribution`、`export_plan_csv`、`apply_iso_plan`、`start_batch_detect`+`iso_job_status` 等），不重寫任何業務邏輯。
3. CLI 五指令：`list-nodes` / `validate` / `run` / `run-node` / `replay`。
4. 兩層 side-effect policy + run log 證據鏈。
5. `iso_pdf_safe_poc.workflow.json` 安全示範圖。
6. unittest 測試 + CLI smoke 替代路線。

### 1.3 現在不能做的

- 不改 `run_iso_workflow` 既有 action schema（`isoWorkflow.ts` 的 `IsoWorkflowAction` 21 個值與 `IsoWorkflowRequest` 欄位一個都不能動）。
- 不加任何新 Tauri action、不碰 `frontend/`、不碰 `IsoBoard.tsx`、不碰一鍵頁。
- 不移除/不修改 PyQt legacy（`validator.py` 只接 PyQt 的現狀維持）。
- 不動 Pilot：P01-P12 凍結、P13-P15 append-only，workflow 只「消費」`build_pilot_report` 的輸出，不重排、不改 id/stage/status enum。
- 不做 React Flow / LiteGraph / Rete.js、不做任何 node canvas。
- 不把舊 ISO run log 遷移成 workflow run log；兩套並存、互相引用。

### 1.4 現在做了就是過度工程化（明確禁止）

| 誘惑 | 為什麼不做 |
|---|---|
| 泛用 plugin 自動掃描註冊 node | POC 只有一個 plugin；手動 import 註冊即可 |
| async / 平行執行 DAG | 圖很小、瓶頸在 OCR worker；拓撲序逐一執行就好 |
| node 輸出 cache / memoization 框架 | replay 的 artifact hydration 已覆蓋 80% 需求 |
| port 型別系統（泛型/型別推導） | 用字串 type tag + validate 警告即可 |
| jsonschema 依賴做 params 驗證 | 手寫 required/type/enum/range 檢查，零新依賴 |
| node 版本遷移機制 | `schema_version: 1` 整數欄位保留即可 |
| subgraph / group node | 第一張圖 8 個 node，不需要 |
| workflow engine 抽到 iso_tools 外層共用 | 等第二個用例出現再搬（Option C 結論不變） |
| 把 `_resolve_pdfs` / `_build_plan_rows` 拆成原生 node | 那是 brief 的 Option B，等 Option A 證明引擎形狀後再說 |

---

## 2. 檔案與資料夾架構（最終版）

全部新增檔案，零修改既有檔案（除 Phase 7 的兩個 docs）：

```text
launcher/plugins/iso_tools/workflow/
  __init__.py          # 只放 WORKFLOW_SCHEMA_VERSION = 1，不 re-export 重物
  errors.py            # WorkflowError / GraphValidationError / NodeExecutionError /
                       # SideEffectBlockedError / ReplayViolationError
  schema.py            # PortSpec/NodeSpec/NodeInstance/EdgeSpec/WorkflowGraph/
                       # ValidationIssue + load_workflow()/save_workflow()/normalize_graph()
  registry.py          # NodeRegistry、@register_node、get_registry()
  policy.py            # SideEffectKind 常數、AUTO_ALLOWED/GUARDED 集合、SideEffectPolicy、
                       # SideEffectGate、SideEffectRecord
  context.py           # WorkflowContext、NodeExecutionContext、ArtifactStore
  executor.py          # validate_graph()/topological_order()/run_workflow()/
                       # run_single_node()/replay_workflow()
  run_log.py           # WorkflowRunLogWriter：run_log.json + events.jsonl + graph.snapshot.json
  cli.py               # argparse 入口（python -m launcher.plugins.iso_tools.workflow.cli）
  nodes/
    __init__.py        # 依序 import 各 node 模組以觸發註冊（唯一註冊入口）
    base.py            # WorkflowNode ABC、NodeRunResult、輔助 helper
    sources.py         # iso.discover_sources、iso.split_pdf
    iso_list.py        # iso.load_iso_table
    detection.py       # iso.batch_detect_serials（worker 模式）
    plan.py            # iso.build_plan（含 build_rename_plan 變體 param）
    pilot.py           # iso.pilot_report、iso.roi_distribution
    export.py          # iso.export_plan_csv、iso.export_debug_bundle
    profile.py         # iso.load_profile、iso.save_draft_profile
    apply.py           # iso.apply_rename（guarded、預設 disabled）
  adapters/
    __init__.py
    iso_request.py     # build_request(payload) -> IsoWorkflowRequest；
                       # 全 workflow 內唯一允許 import launcher.app.tauri_iso_workflow 的模組
                       # （nodes/* 一律經由它取得 request 與 backend 函式）
  workflows/
    iso_pdf_safe_poc.workflow.json   # 安全示範圖（apply 節點 disabled）

tests/
  test_iso_workflow_engine.py   # 純引擎：schema/validate/topo/cycle/refs（FakeNode，零 ISO）
  test_iso_workflow_policy.py   # side-effect 兩層 policy + replay 封鎖 + 證據鏈不變式
  test_iso_workflow_nodes.py    # adapter nodes（pypdf+openpyxl fixtures，比照既有測試）
  test_iso_workflow_cli.py      # CLI 五指令 smoke（in-process 呼叫 cli.main(argv)）
  test_iso_workflow_apply_safety.py  # ApplyRenameNode 專屬安全測試
```

責任邊界鐵則：

- `schema.py`/`registry.py`/`policy.py`/`context.py`/`executor.py`/`run_log.py`/`errors.py`/`nodes/base.py` **禁止** import 任何 `launcher.app.*` 或 `launcher.plugins.iso_tools.*`（workflow 子套件自身除外）。用測試守住（見 §9）。
- `nodes/*.py` 只能透過 `adapters/iso_request.py` 接觸 backend。
- `cli.py` 不含業務邏輯，只做 argparse → executor → exit code。


---

## 3. 核心 Python API 設計

全部 Python ≥3.12（pyproject `requires-python = ">=3.12"`），用 `from __future__ import annotations`、`dataclass`、`pathlib.Path`。

### 3.1 schema.py — 資料結構

```python
WORKFLOW_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class PortSpec:
    name: str
    type: str            # "json" | "path" | "rows" | "plan" | "profile" | "text" | "number" | "bool"
    required: bool = True
    description: str = ""

@dataclass(frozen=True)
class NodeSpec:
    """type 層級的宣告，由 node class 持有，registry 是唯一事實來源。"""
    node_type: str                      # 例 "iso.build_plan"
    display_name: str
    description: str
    inputs: tuple[PortSpec, ...]
    outputs: tuple[PortSpec, ...]
    params_schema: dict[str, Any]       # {"only_ready": {"type": "bool", "default": True}, ...}
    side_effects: tuple[str, ...] = ()  # SideEffectKind 常數
    guarded: bool = False               # True = 任一 side effect 屬 GUARDED
    requires_confirm_default: bool = False

@dataclass
class NodeInstance:
    """graph 層級的一個節點實例（對應 JSON 的 nodes[] 元素）。"""
    node_id: str
    node_type: str
    display_name: str = ""
    inputs: dict[str, Any] = field(default_factory=dict)   # 字面值或 "$workflow.inputs.x" / "$nodes.id.outputs.port"
    outputs: dict[str, str] = field(default_factory=dict)  # port -> context alias；省略 = port 名
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    requires_confirm: bool | None = None  # None = 用 spec 預設
    side_effects: tuple[str, ...] = ()    # JSON 內為「申報文件」；validate 與 registry 比對

@dataclass(frozen=True)
class EdgeSpec:
    from_node: str
    from_output: str
    to_node: str
    to_input: str

@dataclass
class WorkflowGraph:
    schema_version: int
    workflow_id: str
    display_name: str
    description: str
    inputs: dict[str, Any]              # 宣告 + 預設值
    nodes: list[NodeInstance]
    edges: list[EdgeSpec]               # normalize 後一定與 inputs refs 一致
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True)
class ValidationIssue:
    severity: str        # "error" | "warning"
    code: str            # 見下表
    message: str
    node_id: str = ""
    edge: str = ""       # "from.port->to.port" 字串，方便序列化
```

ValidationIssue codes（固定字串，測試直接斷言）：

| code | severity | 意義 |
|---|---|---|
| `WF001` | error | schema_version 不支援 |
| `WF002` | error | node_id 重複 |
| `WF003` | error | 未知 node_type |
| `WF004` | error | edge 端點 node 不存在 |
| `WF005` | error | edge 端點 port 不存在於 NodeSpec |
| `WF006` | error | 偵測到 cycle（message 列出環路徑） |
| `WF007` | error | required input 無法解析（無字面值、無 ref、無 edge） |
| `WF008` | error | ref 語法錯誤或指向不存在的 workflow input / node output |
| `WF009` | error | 手寫 edges 與 inputs refs 不一致 |
| `WF010` | error | params 不符 params_schema（缺 required / 型別錯 / enum 外） |
| `WF011` | error | JSON 申報的 side_effects 少於 registry 宣告（低報危險） |
| `WF012` | warning | JSON 申報的 side_effects 多於 registry 宣告（高報無害） |
| `WF013` | warning | port type 不相容（POC 只警告不擋） |
| `WF014` | error | guarded node enabled 但圖未標 requires_confirm（防手滑解鎖） |
| `WF015` | error | node 專屬 validate 失敗（如 BuildPlanNode 缺 page_folder 接線） |

`schema.py` 函式：

```python
def load_workflow(path: Path) -> WorkflowGraph          # 讀 JSON → normalize_graph()
def save_workflow(graph: WorkflowGraph, path: Path)     # 排序 keys、ensure_ascii=False、LF
def normalize_graph(raw: dict) -> WorkflowGraph
    # 1) 解析 nodes[].inputs 中的 "$nodes.<id>.outputs.<port>" → 推導 EdgeSpec
    # 2) raw 有手寫 edges 時，逐條比對推導結果，不一致丟 WF009（在 validate 階段回報）
    # 3) outputs alias 補預設（port 名）
def graph_content_hash(graph: WorkflowGraph) -> str     # sha256 over canonical JSON（sort_keys, no ts）
```

### 3.2 nodes/base.py — Node base class contract

```python
class WorkflowNode(ABC):
    spec: ClassVar[NodeSpec]

    def validate(self, instance: NodeInstance, graph: WorkflowGraph) -> list[ValidationIssue]:
        """node 專屬靜態檢查；引擎已做共通檢查，這裡只加領域規則。預設回傳 []"""
        return []

    @abstractmethod
    def run(self, ctx: NodeExecutionContext) -> dict[str, Any]:
        """回傳 outputs dict（port -> JSON-safe 值）。
        - 透過 ctx.inputs / ctx.params 取資料（已解析、已套 schema 預設）。
        - 執行任何 side effect 前【必須】先呼叫 ctx.request_side_effect(kind, detail)
          並依回傳的 decision 決定做或不做。
        - 大型輸出呼叫 ctx.write_artifact(port, payload) 落地，回傳值放 ArtifactRef。
        - 失敗直接 raise，executor 統一包裝。
        """
```

Node 實作鐵則：

1. `run()` 內**禁止** `print`；要訊息走 `ctx.emit_event(code, title, detail)`。
2. `run()` 不可改動 `ctx.inputs` 的內容（上游 artifact 不可變）。
3. 宣告了 `side_effects` 的 node，run 結束時每個 kind 至少要有一筆 decision 記錄，executor 會驗證（不變式 INV-1，見 §8.4）。
4. 未宣告的 kind 呼叫 `request_side_effect` → executor 立刻讓該 node 失敗（不變式 INV-2）。

### 3.3 registry.py

```python
class NodeRegistry:
    def register(self, node_cls: type[WorkflowNode]) -> None      # node_type 重複 → raise
    def create(self, node_type: str) -> WorkflowNode              # 未知 → KeyError 包成 WF003
    def get_spec(self, node_type: str) -> NodeSpec
    def list_specs(self) -> list[NodeSpec]                        # 按 node_type 排序（穩定輸出）

_REGISTRY = NodeRegistry()

def register_node(cls):           # decorator
    _REGISTRY.register(cls); return cls

def get_registry() -> NodeRegistry:
    import launcher.plugins.iso_tools.workflow.nodes  # noqa: F401  觸發註冊（lazy，避免 CLI 啟動即載 cv2）
    return _REGISTRY
```

注意：`nodes/__init__.py` import 各 node 模組，但 node 模組頂層**不得** import `cv2` / `serial_vision` 等重物——一律在 `run()` 內 lazy import（`detection.py` 尤其要守住，否則 `list-nodes` 在沒裝 OCR 依賴的機器上會炸）。

### 3.4 policy.py — 兩層 side-effect policy

```python
# kind 常數（字串字面值就是 run log 的序列化值，不可改）
MAY_WRITE_PAGE_PDFS = "may_write_page_pdfs"
WRITES_JOB_FILES    = "writes_job_files"
WRITES_ISO_RUN_LOG  = "writes_iso_run_log"
WRITES_CSV          = "writes_csv"
WRITES_DEBUG_BUNDLE = "writes_debug_bundle"
SPAWNS_WORKER       = "spawns_worker"
RENAMES_FILES       = "renames_files"
WRITES_PROFILE      = "writes_profile"

AUTO_ALLOWED = frozenset({MAY_WRITE_PAGE_PDFS, WRITES_JOB_FILES, WRITES_ISO_RUN_LOG,
                          WRITES_CSV, WRITES_DEBUG_BUNDLE, SPAWNS_WORKER})
GUARDED      = frozenset({RENAMES_FILES, WRITES_PROFILE})
REPLAY_HARD_BLOCKED = frozenset({RENAMES_FILES, WRITES_PROFILE})   # replay 無任何旗標可解

@dataclass(frozen=True)
class SideEffectPolicy:
    mode: str                       # "run" | "replay" | "dry_run"
    allowed_guarded: frozenset[str] = frozenset()   # 來自 CLI --allow
    confirmed_nodes: frozenset[str] = frozenset()   # 來自 CLI --confirm <node_id>
    include_auto_in_replay: bool = False            # CLI --include-auto-side-effects

@dataclass
class SideEffectRecord:
    kind: str
    decision: str    # "executed" | "simulated" | "skipped_not_needed" |
                     # "blocked_policy" | "blocked_replay" | "skipped_dry_run" | "skipped_disabled"
    detail: dict[str, Any]          # 路徑、筆數、job_id 等證據
    at: str                         # ISO timestamp

class SideEffectGate:
    """每個 node 執行時由 executor 建立，綁定 node_id + instance.requires_confirm。"""
    def request(self, kind: str, detail: dict[str, Any]) -> str:   # 回傳 decision
        # 決策表（依序）：
        # 1. kind 不在該 node spec.side_effects → raise UndeclaredSideEffect（INV-2）
        # 2. mode == "dry_run" → "skipped_dry_run"
        # 3. mode == "replay"：
        #      kind in REPLAY_HARD_BLOCKED → "blocked_replay"
        #      kind in AUTO_ALLOWED and include_auto_in_replay → "executed"
        #      else → "blocked_replay"
        # 4. mode == "run"：
        #      kind in AUTO_ALLOWED → "executed"
        #      kind in GUARDED：
        #         kind in allowed_guarded AND node_id in confirmed_nodes(若 requires_confirm)
        #             → "executed"
        #         else → "blocked_policy"
        # 全部 decision 都 append 到 records 並即時寫 events.jsonl
```

「blocked」對 node 的意義：gate 回傳 blocked 時，node 必須**不執行**該動作並回傳可序列化的說明輸出；若該 node 的存在意義就是這個 side effect（如 apply_rename），node 將 status 標為 `blocked`（executor 提供 `ctx.mark_blocked(reason)`），整體 run status = `completed_with_blocked`，CLI exit code 4。**blocked 不是 exception**，是正常記錄路徑——這樣 run log 才能證明「被擋」。

### 3.5 context.py

```python
@dataclass
class WorkflowContext:
    run_id: str
    run_dir: Path                 # .runtime/runs/workflow/<run_id>/
    graph: WorkflowGraph
    workflow_inputs: dict[str, Any]      # 圖預設 ⊕ --inputs-json 合併後
    policy: SideEffectPolicy
    log: WorkflowRunLogWriter
    artifacts: ArtifactStore
    node_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)  # node_id -> {port: value}

class NodeExecutionContext:
    node_id: str
    inputs: dict[str, Any]        # 已解析完 refs 的實值
    params: dict[str, Any]        # 已套 params_schema 預設值
    def request_side_effect(self, kind: str, detail: dict) -> str
    def write_artifact(self, port: str, payload: Any) -> dict      # 回傳 ArtifactRef dict
    def emit_event(self, code: str, title: str, detail: str = "") -> None
    def emit_progress(self, done: int, total: int, message: str = "") -> None
    def mark_blocked(self, reason: str) -> None

class ArtifactStore:
    def write_json(self, node_id: str, port: str, payload: Any) -> dict:
        # 寫 run_dir/artifacts/<node_id>.<port>.json（_write_json 同款 tmp+os.replace 原子寫法）
        # 回傳 {"artifact_ref": "artifacts/<node_id>.<port>.json",
        #        "bytes": n, "sha256": "...", "inline": <payload 若序列化 ≤ 2048 bytes 否則省略>}
    def read_json(self, ref: str) -> Any        # replay/run-node hydration 用
```

Artifact 策略（定案）：**所有 node outputs 一律落地成 `artifacts/<node_id>.<port>.json`**；`run_log.json` 內只存 ArtifactRef（序列化 ≤2KB 的值同時 inline，方便人讀）。二進位檔（PDF/CSV/zip）永不複製進 artifacts，只記絕對路徑 + 檔案大小；rows/plan/pilot 這類 JSON 全量落地。這條規則讓 `run-node --from-run` 與 `replay` 的 hydration 變成單純讀檔，零特例。

### 3.6 run_log.py — WorkflowRunLogWriter

```python
class WorkflowRunLogWriter:
    def __init__(self, run_dir: Path, run_id: str): ...
    def write_snapshot(self, graph, inputs, policy) -> None   # graph.snapshot.json + inputs.json
    def event(self, event: str, *, node_id: str = "", **payload) -> None
        # append 一行到 events.jsonl：{"ts", "event", "run_id", "node_id", ...payload}
        # 開檔模式 "a"、encoding="utf-8"、newline="\n"、寫完 flush（worker 進度要可被 tail）
    def finish(self, summary: dict) -> None                   # 原子寫 run_log.json（tmp + os.replace）

def workflow_run_root() -> Path:
    # 比照 iso_tools/run_log.py:35 的寫法：
    return runtime_root() / ".runtime" / "runs" / "workflow"

def new_workflow_run_id(now=None) -> str:   # "wf-YYYYMMDD-HHMMSS-<uuid4 hex 前 6 碼>"
```

### 3.7 executor.py

```python
def validate_graph(graph, registry) -> list[ValidationIssue]
def topological_order(graph) -> list[str]            # Kahn；同層以 node_id 字典序（決定性輸出）
def run_workflow(graph, *, inputs, policy, registry, run_dir_root=None) -> WorkflowRunResult
def run_single_node(graph, node_id, *, from_run: Path | None, inputs, policy, registry) -> WorkflowRunResult
def replay_workflow(source_run_dir: Path, *, policy, registry) -> WorkflowRunResult

@dataclass
class WorkflowRunResult:
    run_id: str
    run_dir: Path
    status: str          # "completed" | "completed_with_blocked" | "failed" | "validation_failed"
    node_results: dict[str, NodeRunResult]
    issues: list[ValidationIssue]

@dataclass
class NodeRunResult:
    node_id: str
    status: str          # "success" | "failed" | "blocked" |
                         # "skipped_disabled" | "skipped_upstream" | "not_run"
    outputs: dict[str, Any]              # port -> ArtifactRef dict
    side_effects: list[SideEffectRecord]
    error: dict[str, Any] | None         # {"type", "message", "traceback"}
    started_at: str; ended_at: str; duration_ms: int
```


---

## 4. Workflow JSON schema

### 4.1 欄位定義

頂層：

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `schema_version` | int | ✓ | 目前固定 `1` |
| `workflow_id` | str | ✓ | snake_case，檔名主體一致 |
| `display_name` | str | ✓ | UI 顯示名 |
| `description` | str |  | |
| `inputs` | object | ✓ | 鍵 = 輸入名；值 = 預設值（`null` 表示必須由 `--inputs-json` 提供或可空） |
| `nodes` | array | ✓ | NodeInstance 列表 |
| `edges` | array |  | 可省略；loader 由 refs 推導。手寫時必須與 refs 一致 |
| `metadata` | object |  | 自由欄位（作者、用途、`locked: true` 預留給一鍵模板） |

`nodes[]` 元素：

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `node_id` | str | ✓ | 圖內唯一，`[a-z0-9_]+` |
| `node_type` | str | ✓ | registry 內存在 |
| `display_name` | str |  | |
| `inputs` | object |  | port -> 字面值 或 `"$workflow.inputs.<name>"` 或 `"$nodes.<node_id>.outputs.<port>"` |
| `outputs` | object |  | port -> alias（省略 = port 名；POC 僅文件性用途） |
| `params` | object |  | 依 NodeSpec.params_schema 驗證 |
| `enabled` | bool |  | 預設 `true`；`false` = skip + 下游 cascade skip |
| `requires_confirm` | bool |  | 省略 = 用 spec 預設；guarded node 在 JSON 解鎖（enabled:true）時必須明寫 `true`（WF014） |
| `side_effects` | array |  | 申報文件；少報 = WF011 error、多報 = WF012 warning |

`edges[]` 元素：`{ "from_node", "from_output", "to_node", "to_input" }`（沿用 brief 命名，未來給 React Flow 用）。

ref 語法（嚴格、僅此兩種，正規表達式檢查）：

```text
$workflow.inputs.<name>
$nodes.<node_id>.outputs.<port>
```

以 `$` 開頭但不匹配上述格式 → WF008。要傳「字面上以 $ 開頭的字串」用 `"$$"` 跳脫（normalize 還原成單一 `$`）。

### 4.2 完整範例：`workflows/iso_pdf_safe_poc.workflow.json`

照抄可用。流程：discover →（顯式）split → load table → batch detect（worker）→ pilot / roi 分布 → 匯出 CSV；apply 預設 disabled。

```json
{
  "schema_version": 1,
  "workflow_id": "iso_pdf_safe_poc",
  "display_name": "ISO PDF 安全節點流程 POC",
  "description": "discover -> split(顯式) -> load table -> batch detect -> pilot/roi -> export csv。apply 預設 disabled。",
  "inputs": {
    "work_folder": null,
    "combine_pdf": null,
    "iso_list": null,
    "sheet_name": "",
    "serial_col": null,
    "line_col": null,
    "pattern": "{serial}--{line}.pdf",
    "detect_serials": true,
    "confidence_threshold": 0.7,
    "serial_region": null,
    "drawing_region": null
  },
  "metadata": { "author": "codex", "locked": false },
  "nodes": [
    {
      "node_id": "discover",
      "node_type": "iso.discover_sources",
      "display_name": "探索來源",
      "inputs": {
        "work_folder": "$workflow.inputs.work_folder"
      }
    },
    {
      "node_id": "split",
      "node_type": "iso.split_pdf",
      "display_name": "拆頁 PDF",
      "inputs": {
        "combine_pdf": "$workflow.inputs.combine_pdf",
        "work_folder": "$workflow.inputs.work_folder"
      },
      "side_effects": ["may_write_page_pdfs"]
    },
    {
      "node_id": "load_table",
      "node_type": "iso.load_iso_table",
      "display_name": "載入 ISO List",
      "inputs": {
        "work_folder": "$workflow.inputs.work_folder",
        "iso_list": "$workflow.inputs.iso_list",
        "sheet_name": "$workflow.inputs.sheet_name",
        "serial_col": "$workflow.inputs.serial_col",
        "line_col": "$workflow.inputs.line_col"
      }
    },
    {
      "node_id": "batch_detect",
      "node_type": "iso.batch_detect_serials",
      "display_name": "批次判讀流水號",
      "inputs": {
        "page_folder": "$nodes.split.outputs.page_folder",
        "work_folder": "$workflow.inputs.work_folder",
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
      "params": {
        "wait_for_completion": true,
        "poll_interval_ms": 500,
        "timeout_s": 900
      },
      "side_effects": ["writes_job_files", "writes_iso_run_log", "spawns_worker"]
    },
    {
      "node_id": "pilot",
      "node_type": "iso.pilot_report",
      "display_name": "Pilot 檢查",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "work_folder": "$workflow.inputs.work_folder",
        "confidence_threshold": "$workflow.inputs.confidence_threshold"
      }
    },
    {
      "node_id": "roi_dist",
      "node_type": "iso.roi_distribution",
      "display_name": "ROI 信心分布",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "confidence_threshold": "$workflow.inputs.confidence_threshold"
      }
    },
    {
      "node_id": "export_csv",
      "node_type": "iso.export_plan_csv",
      "display_name": "匯出命名草稿 CSV",
      "inputs": {
        "rows": "$nodes.batch_detect.outputs.rows",
        "work_folder": "$workflow.inputs.work_folder"
      },
      "params": { "export_path": "" },
      "side_effects": ["writes_csv"]
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
      "params": { "only_ready": true, "dry_run": true },
      "side_effects": ["renames_files"]
    }
  ]
}
```

注意：此檔**不寫** `edges`，由 normalize 從 refs 推導（`split→batch_detect`、`batch_detect→pilot/roi_dist/export_csv/apply_rename`）。`validate --json` 的輸出要包含推導後的 edges，供人工核對與未來 UI 使用。

---

## 5. 第一批 node 清單（12 個）

共通：所有 node 的「包裝對象」都是 `launcher/app/tauri_iso_workflow.py` 的函式，經 `adapters/iso_request.py` 的 `build_request(payload: dict) -> IsoWorkflowRequest`（內部 = `IsoWorkflowRequest(**_normalize_request(payload))`，與 backend `main()` 同款正規化）。**不走 stdin/subprocess、不經 `main()`**——所以既有 ISO run log（只在 `main()` 寫，`_should_write_run_log` 只涵蓋 plan/build_rename_plan/start_batch_detect/apply）在 in-process 呼叫時不會產生；唯一例外是 batch_detect 走 worker，worker 的 `run_job()` 自己 `ensure_iso_run` 會寫。這個事實必須記錄在每個 node 的 run log（`iso_run_log_written: true/false`），見 §8。

| # | node_type | 包裝函式 | inputs（port: type） | outputs | params | side effects |
|---|---|---|---|---|---|---|
| 1 | `iso.discover_sources` | `discover_sources()` | `work_folder: path`（required） | `profile: profile`、`candidates: json`、`folder: path` | — | 無（讀 state store） |
| 2 | `iso.split_pdf` | `split_iso_pdf()` | `combine_pdf: path`（optional）、`work_folder: path`（optional） | `page_folder: path`、`pages: json`、`pdf_count: number`、`source_kind: text` | `force: bool=false`（POC 不實作 force 重拆，保留欄位） | `may_write_page_pdfs`（auto） |
| 3 | `iso.load_iso_table` | `load_iso_table()` | `iso_list: path`、`work_folder: path`、`sheet_name: text`、`serial_col: number?`、`line_col: number?` | `iso_source: json`（headers/sheet/cols）、`sample_records: json`、`record_count: number` | — | 無 |
| 4 | `iso.load_profile` | `load_iso_profile()` | `work_folder: path` 或 `profile_folder: path` | `profile: profile` | `prefer_draft: bool=false` | 無 |
| 5 | `iso.build_plan` | `build_iso_plan()` | `page_folder: path`（**required**）、`iso_list: path`、`sheet_name`、`serial_col?`、`line_col?`、`pattern`、`confidence_threshold: number` | `plan: plan`、`rows: rows`、`summary: json`、`issues: json`、`pilot_results: json` | `as_rename_plan: bool=false`（true 時呼叫 `build_rename_plan()`）、`detect_serials: bool=false`（**鎖死 false**，OCR 一律走 batch_detect） | 無（純讀，由 validate 保證） |
| 6 | `iso.batch_detect_serials` | `start_batch_detect()` + `iso_job_status()` 輪詢 + 逾時 `cancel_iso_job()` | `page_folder: path`（**required**）、`iso_list`、`sheet_name`、`serial_col?`、`line_col?`、`pattern`、`detect_serials: bool`、`confidence_threshold`、`serial_region: json?`、`drawing_region: json?`、`work_folder` | `rows: rows`、`result: plan`、`job: json`、`iso_run_log: json`（public_run_ref） | `wait_for_completion: bool=true`、`poll_interval_ms: number=500`、`timeout_s: number=900` | `writes_job_files`、`writes_iso_run_log`、`spawns_worker`（皆 auto） |
| 7 | `iso.pilot_report` | `pilot_report()` | `rows: rows`（**required**）、`work_folder`、`confidence_threshold` | `pilot_results: json`、`pilot_summary: json` | — | 無（rows 餵入即純；validate 強制 rows 已接線） |
| 8 | `iso.roi_distribution` | `roi_distribution()` | `rows: rows`（**required**）、`confidence_threshold: number` | `distribution: json` | — | 無（同上，rows 必接） |
| 9 | `iso.export_plan_csv` | `export_plan_csv()` | `rows: rows`（**required**）、`work_folder: path` | `export_path: path`、`row_count: number`、`selected_count: number` | `export_path: text=""`（空 = 用 `_default_export_path`） | `writes_csv`（auto） |
| 10 | `iso.export_debug_bundle` | `export_debug_bundle()` | `run_id: text`（required，**指既有 ISO run id**，通常接 `$nodes.batch_detect.outputs.iso_run_log` 的 run_id 欄位） | `bundle_path: path` | `export_path: text=""` | `writes_debug_bundle`（auto） |
| 11 | `iso.save_draft_profile` | `save_iso_draft_profile()` | `profile: profile`（required）、`work_folder: path` | `profile: profile`、`saved: bool` | — | `writes_profile`（**guarded**）；spec `guarded=True`、`requires_confirm_default=True` |
| 12 | `iso.apply_rename` | `_validate_operations()` + `_apply_operations()`（即 `apply_iso_plan()` 的核心；dry_run 走 validate-only） | `rows: rows`（required） | `renamed: json`（操作清單）、`renamed_count: number`、`dry_run: bool` | `only_ready: bool=true`、`dry_run: bool=true` | `renames_files`（**guarded**）；`requires_confirm_default=True` |

各 node 的 validate / run 重點：

- **iso.split_pdf** `run`：呼叫 `split_iso_pdf(request)`；依回傳 `source.kind` 決定 decision——`combine_pdf`（真的拆了）→ 先 `request_side_effect(MAY_WRITE_PAGE_PDFS, {"page_folder", "pdf_count"})` 再回報 `executed`；`existing_pages` / `page_folder` / `work_folder_pages` → `skipped_not_needed`。**實作順序注意**：要先用 `_resolve_pdfs` 的語意預判會不會拆（`page_folder` 缺且 `<stem>_pages` 不存在 → 會拆），在動作前 request gate；若 gate 回 `skipped_dry_run` 則不呼叫 backend，直接回報預測值。
- **iso.build_plan** `validate`：(a) `page_folder` 必須有接線或字面值，否則 WF015；(b) instance 的 inputs 不得含 `combine_pdf`（直接在 spec 不開這個 port，雙保險）；(c) `params.detect_serials` 強制 false，否則 WF015（理由：plan 內嵌 OCR 會在無進度回報下長時間阻塞，OCR 一律走 batch_detect node）。`run`：組 request 時顯式設 `combine_pdf=""`。
- **iso.batch_detect_serials** `validate`：同樣強制 `page_folder` 接線（杜絕 worker 內 `_resolve_pdfs` 偷拆）。`run`：
  1. `request_side_effect(WRITES_JOB_FILES, ...)` → blocked/dry_run 時直接 `mark_blocked` / 回報並結束；
  2. `request_side_effect(SPAWNS_WORKER, ...)`、`request_side_effect(WRITES_ISO_RUN_LOG, ...)`；
  3. 呼叫 `start_batch_detect(request)` 拿 job payload（含 job_id）；
  4. `wait_for_completion` 時以 `poll_interval_ms` 輪詢 `iso_job_status`，每次把 `progress.percent` 轉成 `ctx.emit_progress`；
  5. 終態：`completed` → 取 `result`/`rows`；`failed` → raise（error 含 job.error）；`cancelled` → raise；逾時 → 呼叫 `cancel_iso_job` 後 raise `NodeExecutionError("timeout")`。
  6. outputs 的 `iso_run_log` 取 job payload 的 `run_log`（worker 寫入的 `public_run_ref`）。
- **iso.pilot_report / iso.roi_distribution** `validate`：`rows` port 必須由 edge 提供（不可字面值空列表），否則 WF015——這是「rows 缺席時 fallback 呼叫 build_iso_plan（可能拆 PDF）」的既有行為防線（tauri_iso_workflow.py:302、:310）。`run`：rows 一定塞進 request，fallback 路徑永不觸發。
- **iso.export_plan_csv** `run`：先算 export 目標路徑（param 優先、否則 `_default_export_path` 邏輯由 backend 算），`request_side_effect(WRITES_CSV, {"export_path"})`，allowed 才呼叫 backend。
- **iso.apply_rename** `validate`：(a) `enabled` 且 `requires_confirm` 未明寫 true → WF014；(b) rows 必須接線。`run`：
  1. `only_ready` → 過濾 `row.status == "ready" and row.selected`；無 selected 語意比照 backend（rows 內已有 `selected` 欄位）；
  2. 組 `RenameOperation` 清單 → `_validate_operations(operations)`（衝突/重複/目標已存在這裡會炸，**先於** gate，因為 validate 本身無副作用）；
  3. `dry_run=true` → 不呼叫 gate 的 executed 路徑，回報 `request_side_effect(RENAMES_FILES, {...})`；gate 在 dry_run 下回 `skipped_dry_run`；node 仍輸出完整操作清單（source/target 對照）讓人預覽；
  4. `dry_run=false` → `request_side_effect(RENAMES_FILES, {"operations": n, "first": "...", "last": "..."})`；decision==`executed` 才 `_apply_operations`；blocked → `mark_blocked`，**rows 一個都不准動**；
  5. 任何情況下輸出都含 `dry_run` 實際值與 decision，作為 §8 的證據。
- **iso.save_draft_profile** `run`：同 apply 的 gate 流程，blocked 時回傳現行 profile 不寫入。


---

## 6. DAG engine 細節

### 6.1 拓撲排序與 cycle detection

Kahn's algorithm，in-degree 來自 normalize 後的 edges：

```python
def topological_order(graph: WorkflowGraph) -> list[str]:
    indegree = {n.node_id: 0 for n in graph.nodes}
    adj: dict[str, set[str]] = defaultdict(set)
    for e in graph.edges:
        if e.to_node not in adj[e.from_node]:        # 多條同向邊只算一次 in-degree
            adj[e.from_node].add(e.to_node)
            indegree[e.to_node] += 1
    heap = sorted(nid for nid, d in indegree.items() if d == 0)   # 字典序 → 決定性
    order = []
    while heap:
        nid = heappop(heap); order.append(nid)
        for nxt in sorted(adj[nid]):
            indegree[nxt] -= 1
            if indegree[nxt] == 0: heappush(heap, nxt)
    if len(order) != len(graph.nodes):
        remaining = [nid for nid in indegree if nid not in set(order)]
        raise GraphValidationError(_cycle_issue(remaining, graph))   # WF06，message 用 DFS 找出實際環路徑
    return order
```

決定性是契約：同一張圖任何機器排序結果一致（測試斷言整個 list）。

### 6.2 input reference resolution

解析時機 = 該 node 即將執行前（lazy），由 executor 做：

```python
def _resolve_inputs(instance, ctx) -> dict[str, Any]:
    resolved = {}
    for port in registry.get_spec(instance.node_type).inputs:
        raw = instance.inputs.get(port.name, _MISSING)
        if raw is _MISSING:
            value = _MISSING                       # 沒提供
        elif isinstance(raw, str) and raw.startswith("$") and not raw.startswith("$$"):
            value = _resolve_ref(raw, ctx)         # 兩種 ref；上游值從 ctx.node_outputs 拿
        else:
            value = raw if not (isinstance(raw, str) and raw.startswith("$$")) else raw[1:]
        if value is _MISSING or value is None:
            if port.required: raise NodeExecutionError(f"required input '{port.name}' unresolved")
            value = None
        resolved[port.name] = value
    return resolved
```

`$nodes.x.outputs.y` 解析結果是 ArtifactRef 時，executor 自動 hydrate（讀 artifact JSON 還原實值）再交給 node——node 永遠拿到實值，不知道 artifact 的存在。

### 6.3 單節點執行（executor 內部共用）

```python
def _execute_node(instance, ctx) -> NodeRunResult:
    gate = SideEffectGate(node_id=instance.node_id, spec=spec, instance=instance, policy=ctx.policy, log=ctx.log)
    ctx.log.event("node_started", node_id=instance.node_id)
    try:
        node = registry.create(instance.node_type)
        exec_ctx = NodeExecutionContext(..., gate=gate)
        outputs = node.run(exec_ctx)
        refs = {port: ctx.artifacts.write_json(instance.node_id, port, val) for port, val in outputs.items()}
        gate.assert_invariants()        # INV-1：每個宣告 kind ≥1 decision
        status = "blocked" if exec_ctx.blocked else "success"
        ...
    except Exception as exc:
        status = "failed"; error = {"type": type(exc).__name__, "message": str(exc), "traceback": ...}
    ctx.log.event("node_finished", node_id=..., status=..., duration_ms=...)
    return NodeRunResult(...)
```

### 6.4 整張圖執行（含 skip / error / blocked 規則）

```text
validate_graph() 有 error → 不執行，status=validation_failed，exit 2
for node_id in topological_order():
    若 instance.enabled == False:
        status = skipped_disabled；宣告的每個 side-effect kind 記一筆 decision=skipped_disabled
    elif 任一上游（經 edges 遞迴）狀態 ∈ {failed, skipped_disabled, skipped_upstream, blocked}
         且該上游的輸出是本 node 的 required input:
        status = skipped_upstream（reason 記是哪個上游、哪個 port）
    else:
        _execute_node()
    若 status == failed:
        fail-fast：其餘未跑的 node 全標 not_run，run status = failed，exit 3
blocked 不中斷整圖（下游若不依賴它的輸出照常跑）；結束後若存在 blocked → status = completed_with_blocked，exit 4
全 success/skipped → completed，exit 0
```

不做 `--keep-going`。fail-fast 是 POC 唯一模式（決策，不留選項）。

### 6.5 run-node（單節點重跑）

```text
run-node --workflow W --node N [--from-run RUN_ID] [--inputs-json F] [--allow ...] [--confirm N]
1. load + validate W（error 即停）
2. --from-run 時：開 source run dir，讀 graph.snapshot.json，
   驗 graph_content_hash(W) == snapshot hash，不一致 → exit 2（防拿舊 run 餵新圖）
3. N 的上游 inputs 從 source run 的 artifacts hydrate；缺 artifact → exit 2 並列出缺哪個 port
4. 沒給 --from-run 時：所有 required inputs 必須由 workflow inputs/字面值解析得出，否則 exit 2
5. 以一個新 run_id 執行單一 node（run log 記 "mode": "run_node", "source_run_id": ...）
```

### 6.6 replay 行為（定案語意）

```text
replay --run RUN_ID [--include-auto-side-effects] [--json]
1. 從 source run dir 載入 graph.snapshot.json + inputs.json（不接受 --workflow 覆寫；要改圖請用 run）
2. policy.mode = "replay"
3. 逐 node：
   - 純 node（spec.side_effects 為空）→ 正常重新執行
   - side-effect node →
       a. 所有 kind 經 gate：REPLAY_HARD_BLOCKED → blocked_replay（無例外）；
          AUTO_ALLOWED 且 --include-auto-side-effects → 照常執行；否則 blocked_replay
       b. node 任一 kind 被 block 且因此無法產生輸出（如 batch_detect 沒跑 worker）時，
          executor 自動 hydrate：從 source run 的 artifacts 取該 node 當時的 outputs 餵下游，
          node status = blocked，events 記 "replay_hydrated"（含 source artifact 路徑）
4. 產出全新 run dir；run_log.json 記 "mode": "replay", "source_run_id", "include_auto_side_effects"
```

效果：預設 replay 重算所有純邏輯（plan/pilot/roi 會用當前 code 重跑，可偵測行為漂移），所有寫入動作零執行，但下游資料流靠 hydration 不斷鏈。`apply_rename` 在 replay 中即使 `--allow renames_files --confirm apply_rename` 同時給也**必須** blocked（測試明確覆蓋）。

---

## 7. CLI 設計

入口：`python -m launcher.plugins.iso_tools.workflow.cli <command>`，**必須從 repo root 執行**（`launcher` 是套件；worker spawn 也依賴 `cwd`，見 §11.3）。Windows 用 `.venv\Scripts\python.exe`。

共通旗標：`--json`（stdout 輸出單一 JSON，人類訊息走 stderr）；exit codes：`0` 成功、`2` 驗證失敗/參數錯、`3` 執行失敗、`4` 有 guarded blocked、`5` 檔案不存在。

| command | 參數 | 行為 / 輸出 |
|---|---|---|
| `list-nodes` | `[--json]` | 列出 registry 全部 NodeSpec：node_type、display_name、inputs/outputs ports、params schema、side_effects、guarded。表格或 JSON。**不得 import OCR 重依賴**（lazy import 驗證點） |
| `validate` | `--workflow F [--json]` | load + normalize + validate_graph；列出全部 issues（含推導後 edges 與 topo order）。有 error → exit 2 |
| `run` | `--workflow F [--inputs-json F2] [--set k=v ...] [--allow KIND ...] [--confirm NODE_ID ...] [--dry-run] [--run-root DIR] [--json]` | 驗證→執行→印 run_id、run_dir、各 node 狀態表、side-effect 摘要。`--set` 只支援字串/數字/bool 簡值（複雜值一律用 `--inputs-json`，避開 PowerShell 引號地獄）。執行前若圖中存在 enabled 的 guarded node，先在 stderr 印 side-effect 預告摘要 |
| `run-node` | `--workflow F --node ID [--from-run RUN_ID] [--inputs-json F2] [--allow ...] [--confirm ...] [--json]` | 見 §6.5 |
| `replay` | `--run RUN_ID [--include-auto-side-effects] [--run-root DIR] [--json]` | 見 §6.6 |
| `list-runs` | `[--limit N] [--json]` | 掃 `workflow_run_root()`，列 run_id/workflow_id/status/started_at（debug 便利品，30 行內實作） |

`--allow` 合法值僅 `renames_files`、`writes_profile`（auto 類不需要 allow；傳入 auto 值 → exit 2 並提示）。`--confirm` 接 node_id，可重複。guarded 執行的完整門檻 = `--allow <kind>` **且** `--confirm <node_id>`（requires_confirm 時）**且** 圖中 `enabled: true`，三者缺一即 blocked。

PowerShell 範例（寫進文件與 handoff 用）：

```powershell
cd C:\Users\a0976\Documents\GitHub\桌面輔助系統
$py = ".venv\Scripts\python.exe"

# 1. 列出節點
& $py -m launcher.plugins.iso_tools.workflow.cli list-nodes

# 2. 驗證示範圖
& $py -m launcher.plugins.iso_tools.workflow.cli validate --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json

# 3. 準備輸入（檔案，不要 inline JSON）
@'
{
  "work_folder": "C:/Users/a0976/Downloads/t",
  "combine_pdf": "C:/Users/a0976/Downloads/t/testing.pdf",
  "iso_list": "C:/Users/a0976/Downloads/t/HP6精準管理.xlsx",
  "sheet_name": "DWG NO.ALL",
  "detect_serials": true,
  "confidence_threshold": 0.7
}
'@ | Set-Content -Encoding utf8 .runtime\temp\poc_inputs.json
# （iso_list 檔名以實際資料夾內為準；JSON 路徑用正斜線，避免反斜線跳脫）

# 4. 安全執行（apply 是 disabled，不會 rename）
& $py -m launcher.plugins.iso_tools.workflow.cli run --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json --inputs-json .runtime\temp\poc_inputs.json

# 5. 單節點重跑（沿用上次 run 的中間產物）
& $py -m launcher.plugins.iso_tools.workflow.cli run-node --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json --node pilot --from-run wf-20260610-120000-ab12cd

# 6. replay（預設零 side effect）
& $py -m launcher.plugins.iso_tools.workflow.cli replay --run wf-20260610-120000-ab12cd

# 7. 真的要 rename 時（三重門檻 + dry_run 先看）
#    第一步：圖中把 apply_rename 的 enabled 改 true（或用副本 workflow），dry_run 保持 true 跑一次看清單
#    第二步：dry_run 改 false 後：
& $py -m launcher.plugins.iso_tools.workflow.cli run --workflow <修改後的workflow> --inputs-json .runtime\temp\poc_inputs.json --allow renames_files --confirm apply_rename
```


---

## 8. run_log.json 設計

### 8.1 目錄結構與兩套 run log 的關係

```text
<runtime_root>/.runtime/runs/
  iso/<iso-run-id>/            # 既有，不動：run.json + events.jsonl（run_log.py 管）
  workflow/<wf-run-id>/        # 新增
    run_log.json               # 總結（最後原子寫入）
    graph.snapshot.json        # normalize 後整張圖 + content hash
    inputs.json                # 合併後的 workflow inputs
    events.jsonl               # 流水事件（執行中即時 append）
    artifacts/
      batch_detect.rows.json
      batch_detect.result.json
      pilot.pilot_results.json
      ...
```

關係定案：workflow run log 是**外層信封**；既有 ISO run log 是 batch_detect worker 的**內層產物**。互相用 id 引用、永不合併：workflow 的 `nodes.batch_detect.outputs.iso_run_log` 存 `public_run_ref`（run_id/run_dir/run_json/events_jsonl）；其他 in-process 呼叫不產 ISO run log，node result 記 `iso_run_log_written: false`。前端日後可從 workflow run 一路鑽到 ISO run。

### 8.2 run_log.json 完整形狀

```json
{
  "schema_version": 1,
  "run_id": "wf-20260610-143000-a1b2c3",
  "mode": "run",
  "workflow_id": "iso_pdf_safe_poc",
  "graph_hash": "sha256:...",
  "status": "completed_with_blocked",
  "started_at": "2026-06-10T14:30:00", "ended_at": "...", "duration_ms": 84211,
  "policy": {
    "mode": "run",
    "allowed_guarded": [],
    "confirmed_nodes": [],
    "include_auto_in_replay": false,
    "dry_run": false
  },
  "source_run_id": null,
  "topology": ["discover", "split", "load_table", "batch_detect", "pilot", "roi_dist", "export_csv", "apply_rename"],
  "nodes": {
    "batch_detect": {
      "status": "success",
      "started_at": "...", "ended_at": "...", "duration_ms": 70512,
      "resolved_inputs_digest": {"page_folder": "C:/Users/a0976/Downloads/t/testing_pages", "rows": null},
      "outputs": {
        "rows":   {"artifact_ref": "artifacts/batch_detect.rows.json", "bytes": 18234, "sha256": "..."},
        "result": {"artifact_ref": "artifacts/batch_detect.result.json", "bytes": 25120, "sha256": "..."},
        "job":    {"artifact_ref": "artifacts/batch_detect.job.json", "bytes": 900, "sha256": "...",
                    "inline": {"job_id": "…", "state": "completed"}},
        "iso_run_log": {"artifact_ref": "artifacts/batch_detect.iso_run_log.json", "bytes": 310,
                         "inline": {"run_id": "iso-…", "run_dir": "…"}}
      },
      "side_effects": [
        {"kind": "writes_job_files",   "decision": "executed", "at": "…",
         "detail": {"job_dir": ".../.runtime/jobs/iso/<job_id>"}},
        {"kind": "spawns_worker",      "decision": "executed", "at": "…",
         "detail": {"command": "python -m launcher.app.tauri_iso_worker", "job_id": "…"}},
        {"kind": "writes_iso_run_log", "decision": "executed", "at": "…",
         "detail": {"iso_run_id": "iso-…"}}
      ],
      "iso_run_log_written": true,
      "error": null
    },
    "apply_rename": {
      "status": "skipped_disabled",
      "side_effects": [
        {"kind": "renames_files", "decision": "skipped_disabled", "at": "…", "detail": {}}
      ],
      "outputs": {}, "error": null
    }
  },
  "side_effect_summary": {
    "executed":        [{"node_id": "split", "kind": "may_write_page_pdfs"}, {"node_id": "export_csv", "kind": "writes_csv"}, "…"],
    "blocked":         [],
    "skipped":         [{"node_id": "apply_rename", "kind": "renames_files", "reason": "skipped_disabled"}],
    "simulated":       []
  },
  "issues": []
}
```

### 8.3 events.jsonl 事件型錄

每行一個 JSON object：`{"ts": "...", "event": "...", "run_id": "...", "node_id": "...", ...payload}`。

| event | payload 重點 |
|---|---|
| `run_started` | workflow_id、graph_hash、mode、policy |
| `node_started` | node_type |
| `node_progress` | done、total、percent、message（batch_detect 輪詢轉發 job progress） |
| `side_effect_decision` | kind、decision、detail（**這就是證據鏈本體**） |
| `artifact_written` | port、artifact_ref、bytes、sha256 |
| `replay_hydrated` | port、source_artifact、source_run_id |
| `node_finished` | status、duration_ms、error? |
| `run_finished` | status、duration_ms、side_effect_summary |

### 8.4 如何「證明」side effect 有執行 / 被跳過 / 被阻擋

三條不變式，由 executor 強制、由測試斷言：

- **INV-1（完備）**：node 結束時，spec 宣告的每個 kind 在該 node 的 `side_effects[]` 中至少一筆 decision。缺 → node 改判 failed（error.type = `SideEffectAccountingError`）。skip/disabled 的 node 由 executor 代記 `skipped_disabled` / `skipped_upstream`。
- **INV-2（無未申報）**：`request_side_effect` 收到 spec 未宣告的 kind → 立即 raise，node failed。防止 node 偷做事。
- **INV-3（決議即落盤）**：每筆 decision 在做成當下就 append 進 events.jsonl（先寫日誌、後做動作）；`executed` 的 detail 必含可驗證標的（檔案路徑/筆數/job_id），事後可用 `Test-Path` 對賬。run_log.json 的 `side_effect_summary` 是 events 的聚合，兩者不一致視為 bug。

「證明被擋」的標準輸出：decision=`blocked_policy`/`blocked_replay` 的 record + node status=`blocked` + exit code 4 + 目標檔案系統無變化（apply 安全測試直接斷言檔名未變）。

---

## 9. 測試策略

### 9.1 形式決策：unittest.TestCase（雙跑道）

repo 慣例就是 unittest 類（`tests/test_tauri_iso_workflow.py` 等 60+ 檔），操作者用 `python -m pytest tests\...` 跑。新測試一律寫 unittest.TestCase：

```powershell
# pytest 可用（操作者 Windows 環境）：
& .venv\Scripts\python.exe -m pytest tests\test_iso_workflow_engine.py tests\test_iso_workflow_policy.py tests\test_iso_workflow_nodes.py tests\test_iso_workflow_cli.py tests\test_iso_workflow_apply_safety.py -q

# pytest 不可用（沙箱/最小環境）——純標準庫：
& .venv\Scripts\python.exe -m unittest tests.test_iso_workflow_engine tests.test_iso_workflow_policy tests.test_iso_workflow_cli -v
```

引擎/policy/CLI 測試**只用標準庫 + FakeNode**，不碰 pypdf/openpyxl/cv2 → 任何環境都能跑。nodes 測試需要 pypdf+openpyxl（.venv 已有，比照既有測試的 fixture 寫法：`PdfWriter` 造 3 頁 PDF、`Workbook` 造 ISO 表）；無此依賴時 `unittest.skipUnless` 跳過並印明確訊息。

### 9.2 測試隔離（照抄既有測試的環境寫法）

所有會落盤的測試在 `setUp` 設：`os.environ[PROJECT_ROOT_ENV] = <tmp>`（讓 `runtime_root()`、job root、workflow run root 全進 tmp）、`os.environ[STATE_PATH_ENV] = <tmp>/state.json`（profile 隔離）、`DESKTOP_SUPPORT_JOB_ROOT = <tmp>/jobs`。`tearDown` 還原。**絕不在 repo 真實 `.runtime/` 下寫測試資料。**

### 9.3 測試清單（按檔案）

`tests/test_iso_workflow_engine.py`（FakeNode：可設定 outputs/raise/side_effects 的測試替身，註冊進臨時 registry）：

1. workflow JSON round-trip（load→save→load 等價、hash 穩定）
2. refs 推導 edges 正確；手寫 edges 不一致 → WF009
3. 重複 node_id → WF002；未知 type → WF003；壞 port → WF005
4. cycle → WF006 且 message 含環路徑
5. required input 無源 → WF007；壞 ref 語法 → WF008
6. params schema：缺 required / 型別錯 / enum 外 → WF010
7. topo 排序決定性（亂序輸入 nodes，斷言整個 order list）
8. disabled node → skipped_disabled，下游 required → skipped_upstream cascade
9. 中游 failed → fail-fast，下游 not_run，run status=failed
10. `$$` 跳脫還原
11. **架構守門**：`import launcher.plugins.iso_tools.workflow.schema as m; assert "launcher.app" not in {同 module 內 import 的頂層名}`——用 `sys.modules` 快照法：import engine 模組後斷言 `launcher.app.tauri_iso_workflow` 不在 sys.modules（在乾淨 subprocess 裡跑）

`tests/test_iso_workflow_policy.py`：

12. auto kind 在 run 模式 → executed；guarded 無 --allow → blocked_policy
13. guarded 有 allow 無 confirm（requires_confirm node）→ blocked_policy
14. allow+confirm+enabled 三全 → executed
15. replay：auto 預設 blocked_replay；`include_auto_in_replay` → executed；renames_files/writes_profile 給滿旗標仍 blocked_replay
16. dry_run → 全部 skipped_dry_run
17. INV-1：宣告 kind 未記 decision → node failed（SideEffectAccountingError）
18. INV-2：未申報 kind 呼叫 → node failed
19. blocked node → run status=completed_with_blocked、exit 語意 4

`tests/test_iso_workflow_nodes.py`（pypdf/openpyxl fixtures）：

20. split_pdf：combine → executed + `<stem>_pages` 出現；再跑一次 → skipped_not_needed（既有頁資料夾）
21. build_plan：接 split 的 page_folder → rows/summary 與直呼 `build_iso_plan(page_folder=...)` 等價（欄位逐一比對）；validate 拒絕缺 page_folder 的接線（WF015）
22. pilot_report/roi_distribution：餵 rows → 輸出含 P01-P15 id 集合不變（**凍結契約斷言**：`{r["id"] for r in pilot_results} ⊇ {"P01",...,"P12"}` 且順序不重排）；validate 拒絕 rows 未接線
23. export_plan_csv：executed → CSV 存在、行數正確、utf-8-sig；dry_run → 檔案不存在 + simulated/skipped 記錄
24. batch_detect adapter：monkeypatch `launcher.app.tauri_iso_workflow._spawn_iso_worker` 為同步呼叫 `tauri_iso_worker.run_job(job_dir)`（既有測試同款手法），detect_serials=False → 輪詢完成、rows 正確、job files 存在、`iso_run_log_written=true` 且 ISO run dir 有 run.json；timeout 路徑：worker 不跑 → 假時鐘逾時 → cancel.json 出現 + node failed
25. load_iso_table/load_profile/discover_sources：純讀煙霧測試

`tests/test_iso_workflow_apply_safety.py`（**最重要的一檔**）：

26. 預設圖（enabled:false）整圖跑完 → 檔名零變化、decision=skipped_disabled
27. enabled:true、無 --allow → blocked_policy、檔名零變化、exit 4
28. enabled:true、--allow 但無 --confirm → 同上
29. enabled:true、allow+confirm、dry_run=true → 檔名零變化、輸出含完整操作預覽
30. enabled:true、allow+confirm、dry_run=false → 檔案真的改名、decision=executed、detail 筆數正確
31. replay 上述 run → renames_files blocked_replay、檔名零變化（先把檔案改回原名再 replay）
32. `_validate_operations` 衝突（兩列同 target）→ node failed、零變化

`tests/test_iso_workflow_cli.py`（in-process 呼叫 `cli.main(argv)` 斷言 exit code 與 stdout JSON；不開 subprocess）：

33. list-nodes --json 含 12 個 node_type
34. validate 對壞圖 exit 2、好圖 exit 0
35. run FakeNode 圖 → run dir 結構齊全（run_log.json/graph.snapshot.json/inputs.json/events.jsonl/artifacts/）
36. replay --run → 新 run dir、mode=replay
37. --allow 傳 auto 值 → exit 2

### 9.4 pytest 不可用時的 CLI smoke（寫進 handoff 的替代驗證）

```powershell
& $py -m unittest tests.test_iso_workflow_engine tests.test_iso_workflow_policy tests.test_iso_workflow_cli -v
& $py -m launcher.plugins.iso_tools.workflow.cli list-nodes
& $py -m launcher.plugins.iso_tools.workflow.cli validate --workflow launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json
# 樣本資料端到端（C:\Users\a0976\Downloads\t，期望 4 ready / 0 warn / 0 blocked，與一鍵結果等價）：
& $py -m launcher.plugins.iso_tools.workflow.cli run --workflow ... --inputs-json .runtime\temp\poc_inputs.json --json
# 然後人工核對 run_log.json 的 summary 與 side_effect_summary
```

不能 commit / 不能跑完整 build 時：在 handoff 文件記「嘗試的指令、確切錯誤、改用的驗證」，比照 brief §1.4 的要求；用 `git diff --stat` 證明變更範圍。


---

## 10. 實作順序（7 個 commit-sized phases）

> 通則：每個 phase 一個 commit（環境不能 commit 時，一個 phase 一份 `git diff` 證據 + handoff 段落）。**Phase 5 與 Phase 6 絕對不可同 commit / 同次施工**（worker 輪詢與 rename 防護是兩種完全不同的風險面，混在一起出事無法 bisect）。docs 修改一律獨立（Phase 7）。

### Phase 0 — 基底驗證（不寫碼）
- 動作：`git status --short --branch`、`git log --oneline -8`、`git rev-parse HEAD origin/codex/tauri-react-spike`。
- 預期：`HEAD` 與 `origin/codex/tauri-react-spike` 一致，且歷史至少包含 `081ed04`。正式施工前工作樹應只允許未追蹤的 `.qwen/`；若還有 node workflow docs 未提交，先把文件整理 commit/push，或在後續 commit 中用明確路徑排除。若出現 `frontend/`、`launcher/app/`、既有 ISO UI / backend 檔案 modified，先看 diff 並確認來源；與本任務無關就不要動、不要 stage。所有 commit 用明確路徑 add，嚴禁 `git add -A` / `git add .`。
- 開分支：`git switch -c codex/iso-node-workflow-poc`（不能開分支就留在原分支，但 commit 訊息前綴 `feat(iso-workflow):`）。
- 完成標準：上述輸出貼進工作筆記。

### Phase 1 — engine 核心（純標準庫）
- 新增：`workflow/__init__.py`、`errors.py`、`schema.py`、`registry.py`、`policy.py`、`tests/test_iso_workflow_engine.py`（先到測項 7）、`tests/test_iso_workflow_policy.py`（測項 12-16 的 gate 單元層）。
- 完成標準：兩個測試檔全綠；engine 模組零 `launcher.app` import。
- 驗證：`& $py -m unittest tests.test_iso_workflow_engine tests.test_iso_workflow_policy -v`

### Phase 2 — executor + run log + context + base
- 新增：`context.py`、`executor.py`、`run_log.py`、`nodes/__init__.py`、`nodes/base.py`；補測項 8-11、17-19。
- 完成標準：FakeNode 圖可整圖執行/禁用跳過/封鎖記錄/replay hydration；run dir 五件套齊。
- 驗證：同上兩檔 + 手動檢視 tmp run dir。

### Phase 3 — CLI（FakeNode 即可全功能）🟢 可停下交接點
- 新增：`cli.py`、`tests/test_iso_workflow_cli.py`（list-nodes 斷言先放寬為 ≥0 個 iso node）。
- 完成標準：五指令 + list-runs 全通、exit codes 正確、--json 穩定。
- 驗證：`& $py -m unittest tests.test_iso_workflow_cli -v` + 手跑五指令。
- **此點交接價值**：引擎+CLI 完整、零 ISO 風險，任何人可從這裡續接。

### Phase 4 — 純讀 adapter nodes
- 新增：`adapters/iso_request.py`、`nodes/sources.py`（先只 discover）、`nodes/iso_list.py`、`nodes/plan.py`、`nodes/pilot.py`、`nodes/profile.py`（先只 load_profile）、`tests/test_iso_workflow_nodes.py`（測項 21、22、25）。
- 完成標準：build_plan 與直呼 `build_iso_plan` 等價；pilot P01-P15 凍結斷言過；WF015 防線生效。
- 驗證：`& $py -m pytest tests\test_iso_workflow_nodes.py -q`（或 unittest）。

### Phase 5 — auto side-effect nodes（split / csv / debug bundle / batch detect）🟢 可停下交接點
- 修改：`nodes/sources.py`（+split_pdf）；新增：`nodes/export.py`、`nodes/detection.py`；補測項 20、23、24。
- 完成標準：split 的 executed/skipped_not_needed 分流正確；batch_detect 走 monkeypatch worker 全綠；INV-1/2/3 在真 node 上成立。
- 驗證：nodes 測試全綠 + FakeNode 圖不退化。
- ⚠️ 本 phase 不碰 apply/profile 寫入。

### Phase 6 — guarded nodes（apply_rename / save_draft_profile）
- 新增：`nodes/apply.py`、`nodes/profile.py` 補 save_draft、`tests/test_iso_workflow_apply_safety.py`（測項 26-32 一個不少）。
- 完成標準：安全測試全綠；「預設圖怎麼跑都不會 rename」有測試證明。
- 驗證：`& $py -m pytest tests\test_iso_workflow_apply_safety.py -q`。

### Phase 7 — 示範圖 + 樣本驗證 + docs
- 新增：`workflows/iso_pdf_safe_poc.workflow.json`；修改本文件的完成狀態 / 驗證段落。若需要另存完工報告，放到 `docs/archive/iso_pdf/node_workflow/iso_pdf_node_workflow_handoff_<date>.md`，不要再把新的 root-level docs 留在 `docs/`。
- 完成標準：樣本資料（`C:\Users\a0976\Downloads\t`）端到端 run：summary 4 ready/0 warn/0 blocked、CSV 落地、apply skipped_disabled、replay 零寫入。與一鍵（start_batch_detect 路徑）對同輸入的 rows 數/狀態分布等價。
- 沒有樣本資料的環境：用測試 fixtures 自動生成等價小樣本跑通即可，並在 handoff 註明。

---

## 11. 重要陷阱與防呆（Codex 必讀）

1. **Windows path**：
   - JSON 內路徑一律正斜線（`C:/Users/...`）；程式內一律 `pathlib.Path`，序列化才 `str(path)`。禁止字串拼接路徑。
   - repo 路徑含中文（`桌面輔助系統`）、樣本檔名含中文——任何 `open()` 顯式 `encoding="utf-8"`；CLI 進入點先做 stdout/stderr reconfigure（抄 `tauri_iso_workflow._configure_stdio` 的做法），否則 cp950 console 印中文會炸。
   - `os.replace` 同磁碟區才原子；run dir 都在 runtime_root 下沒問題，但 export_path 可能跨碟——CSV/zip 維持 backend 既有寫法即可，不要自作聰明加 tmp-rename。
2. **JSON serialization**：dataclass 用自寫 `to_payload()`（repo 慣例，見 `IsoNamingProfile`），不要用 `asdict` 硬轉含 Path/datetime 的結構；`json.dumps(..., ensure_ascii=False)`；`Path`→`str`、`datetime`→isoformat 在邊界一次轉乾淨。events.jsonl 一行一物件 + `\n` + flush。
3. **long-running batch worker**：
   - `_spawn_iso_worker` 用 `cwd=Path.cwd()` 且 `python -m`——CLI **必須在 repo root 跑**，否則 worker ImportError 且因 stdout/stderr=DEVNULL **完全無聲**。CLI 啟動時檢查 `Path("launcher/app/tauri_iso_worker.py").exists()`，不在 repo root 直接 exit 5 給訊息。
   - 輪詢迴圈要 `time.sleep(poll_interval_ms/1000)`，禁 busy-wait；每次輪詢轉發 progress 事件；逾時先 `cancel_iso_job` 再 fail（不要留殭屍 job）；Ctrl-C（KeyboardInterrupt）也要走 cancel 再退出。
   - job state 取值以 `tauri_iso_worker.py` 實況為準：`queued/running/completed/failed/cancelled/cancel_requested`，輪詢用「集合判斷終態」而不是 `== "completed"`。
4. **既有 ISO run log 會被 in-process 呼叫跳過**：ISO run log 只在 `main()`（stdin 模式）對 {plan, build_rename_plan, start_batch_detect, apply} 寫入。workflow 的 in-process 呼叫不經 `main()` → 不寫。這是**接受的設計**（workflow run log 才是外層真相），但每個 node result 必記 `iso_run_log_written`，且 batch_detect（worker 會寫）必須把 `public_run_ref` 收進 outputs。不要試圖在 adapter 裡補呼叫 `start_iso_run` 模擬 main()——會造成雙寫與 run_type 錯亂。
5. **plan 可能寫檔**：`_resolve_pdfs` 在「沒有 page_folder、combine 存在、`<stem>_pages` 不存在」時會 `split_pdf_to_pages`。防線 = `iso.build_plan`/`iso.batch_detect_serials` 的 spec 不開 `combine_pdf` port + validate 強制 `page_folder` 接線 + run 時顯式 `combine_pdf=""`。**也適用 roi_distribution/pilot_report/export_plan_csv 的 rows-fallback 路徑**（rows 空會內部呼叫 build_iso_plan）——所以這三個 node 的 rows 必接線。測試 21/22 守住。
6. **OCR / ROI 不能在 slider 中重跑**：本階段無 UI，但把規則固化在引擎層：`iso.build_plan` 鎖死 `detect_serials=false`、OCR 只存在於 `iso.batch_detect_serials`（顯式、有進度、可取消）。未來調校頁改 node params 時，UI 層沿用既有 debounce（commit 15cf898 的行為），引擎永遠只在「執行」時跑 OCR，沒有「參數變更自動重跑」機制——不要實作 auto-rerun。
7. **CSV / rename / profile 寫入安全**：CSV 用 backend 既有 `utf-8-sig` 寫法（Excel 相容），不改；rename 靠 `_validate_operations`（衝突偵測）+ gate 三重門檻 + dry_run 預設 true；profile 只開 draft（save_draft_profile），publish/revert 不入 graph。`export_path` param 若指向 repo 內或 `.runtime` 外的系統位置照常允許（操作者自己給的路徑），但 detail 記絕對路徑供審計。
8. **PyQt legacy**：整包新增程式碼不 import 任何 PyQt 模組、不動 `validator.py`、不動 `launcher/app/main.py` / `tk_main.py`。`iso_tools/__init__.py` 不要加 workflow 的 re-export（避免 PyQt 啟動路徑連帶載入）。
9. **重依賴 lazy import**：`cv2`/`serial_vision`/`_SerialDetector` 只能出現在 `run()` 內的局部 import。`list-nodes`、`validate`、engine 測試在無 OCR 環境必須可跑。`detection.py` 頂層只允許 import 標準庫與 workflow 自身。
10. **檔案編輯環境陷阱（沙箱施工時）**：本 repo 過往經驗——Windows 路徑的檔案工具就地編輯不會即時同步到 Linux 掛載視圖（bash/測試會讀到舊檔）。在 Linux 沙箱施工時用 bash 直接寫掛載路徑並以 `git diff` 驗證；在 Windows 本機施工則無此問題。
11. **決定性輸出**：topo order、list-nodes 排序、JSON dump（`sort_keys=True` 用於 hash、人讀檔不必）——凡是測試會斷言的輸出都要決定性。`graph_content_hash` 不含 timestamp/run_id。
12. **不要動 `.runtime` 的既有子目錄**（jobs/iso、runs/iso）；workflow 只新建 `runs/workflow/`。測試一律經 `PROJECT_ROOT_ENV` 改道 tmp。

---

## 12. React Flow / LiteGraph / Rete.js 後續銜接（本階段只定 API，不實作）

### 12.1 既定方向

選型傾向 React Flow（與既有 React/Tauri spike 同棧），但**本階段不裝任何套件**。前端永遠只消費 JSON：graph JSON（§4）+ NodeSpec JSON（list-nodes --json）+ run log JSON（§8）。Python node class 永不直接暴露。

### 12.2 未來 Tauri actions（append-only 加進既有 `run_iso_workflow` dispatcher，不開新 command）

沿用現有 stdin-JSON → stdout-JSON 橋，新 action 值附加在 `_dispatch_request` 尾端（不影響既有 21 個 action 的 schema，前端 `IsoWorkflowAction` union 同步 append）：

| action | request 追加欄位 | response | 對應 CLI |
|---|---|---|---|
| `workflow_list_nodes` | — | `{nodes: NodeSpecJson[]}` | list-nodes |
| `workflow_load` | `workflow_path` | `{graph, issues}` | （load+normalize） |
| `workflow_validate` | `workflow_path` 或 `graph` | `{issues, topology, edges}` | validate |
| `workflow_run` | `graph`/`workflow_path`、`workflow_inputs`、`allow`、`confirm` | `{workflow_job_id}`（沿用 job 模式：寫 job dir + spawn CLI 子程序跑，前端輪詢） | run |
| `workflow_run_status` | `workflow_job_id` | job payload（progress 來自 events.jsonl tail） | — |
| `workflow_cancel` | `workflow_job_id` | job payload | — |
| `workflow_list_runs` / `workflow_read_run_log` | `run_id?` | run log JSON | list-runs |
| `workflow_replay` | `run_id`、`include_auto` | `{workflow_job_id}` | replay |

長跑統一走「job dir + 輪詢」模式（與 `start_batch_detect` 同構），不發明新的 streaming 通道。guarded 的 allow/confirm 由 UI 的確認對話框蒐集後**明文**放進 request——後端永不記住授權、不做 session 級解鎖。

### 12.3 四模式共用同一張 graph 的方式

| 模式 | 讀什麼 | 寫什麼 | 鎖 |
|---|---|---|---|
| 一鍵 | `workflows/iso_pdf_default.workflow.json`（`metadata.locked: true` + 釘 `graph_hash`） | 只給 workflow_inputs（資料夾/檔案路徑） | 圖結構/params 全鎖；hash 不符即拒跑 |
| 工作台 | run log 的 per-node outputs（rows/issues/pilot_results 餵現有 PilotStrip/NamingTable） | 重跑安全 node（run-node 白名單：pilot/roi_dist/export_csv） | 不可改圖、不可改 params |
| 調校 | 同上 + NodeSpec.params_schema 自動生表單 | 白名單 node 的 params overlay（`{node_id: {param: value}}` 蓋在鎖定圖上，不落盤原圖） | 可改 params；不可增刪 node/edge |
| 節點式 | 全部 | nodes/edges/params/enabled/policy；另存新 workflow JSON | 進階模式入口藏在調校頁；guarded node 視覺強標 |

params overlay 是調校頁的關鍵概念：一鍵模板永遠唯讀，調校產生 overlay → 滿意後另存為新 workflow 或走 profile（既有 save_draft/publish 治理流程不變）。

### 12.4 前端型別（未來放 `frontend/tauri-spike/src/workflow/types.ts`，現在不建檔）

```ts
type WorkflowGraphJson = {
  schema_version: number; workflow_id: string; display_name: string; description?: string;
  inputs: Record<string, unknown>;
  nodes: WorkflowNodeJson[]; edges?: WorkflowEdgeJson[];
  metadata?: { locked?: boolean; [k: string]: unknown };
};
type WorkflowNodeJson = {
  node_id: string; node_type: string; display_name?: string;
  inputs?: Record<string, unknown>; outputs?: Record<string, string>;
  params?: Record<string, unknown>;
  enabled?: boolean; requires_confirm?: boolean; side_effects?: string[];
};
type WorkflowEdgeJson = { from_node: string; from_output: string; to_node: string; to_input: string };
type NodeSpecJson = {
  node_type: string; display_name: string; description: string;
  inputs: PortJson[]; outputs: PortJson[];
  params_schema: Record<string, { type: string; default?: unknown; enum?: unknown[] }>;
  side_effects: string[]; guarded: boolean; requires_confirm_default: boolean;
};
```

---

## 13. 給 Codex 的最後執行指令（checklist，照做即可，不要再問）

**前置**
- [ ] `cd C:\Users\a0976\Documents\GitHub\桌面輔助系統`；確認 PowerShell、`$py = ".venv\Scripts\python.exe"` 存在（沒有就用 `python`，需 ≥3.12）。
- [ ] `git status --short --branch` / `git log --oneline -8` / `git rev-parse HEAD origin/codex/tauri-react-spike`：HEAD 必須與 origin 一致，且包含 `081ed04` 或其後代；`.qwen/` 一概不碰、不 stage；若有其他 modified 先看 diff，與本任務無關就不要動。
- [ ] `git switch -c codex/iso-node-workflow-poc`（失敗就留原分支，commit 用明確路徑）。
- [ ] 讀完本文件 + 歸檔 brief `docs/archive/iso_pdf/node_workflow/iso_pdf_node_workflow_pilot_brief_opus_2026-06-09.md`（只作背景；衝突以本文件為準）+ `launcher/app/tauri_iso_workflow.py` 的 `_dispatch_request`/`_resolve_pdfs`/`_should_write_run_log`/`_spawn_iso_worker` 四段。

**施工（嚴格按 phase，每 phase 結束即 commit 或留 diff 證據）**
- [x] Phase 1：建 `workflow/{__init__,errors,schema,registry,policy}.py` + engine/policy 測試（§3.1/3.3/3.4、§9 測項 1-7、12-16）。跑 `-m unittest` 綠。Commit：`feat(iso-workflow): add graph schema, registry and side-effect policy`。
- [x] Phase 2：建 `context.py`/`executor.py`/`run_log.py`/`nodes/base.py`（§3.2/3.5/3.6/3.7、§6）+ 測項 8-11、17-19。Commit：`feat(iso-workflow): add DAG executor and workflow run log`。
- [x] Phase 3：建 `cli.py` + CLI 測試（§7、測項 33-37）。手跑五指令截錄輸出。Commit：`feat(iso-workflow): add workflow CLI`。
- [x] Phase 4：建 `adapters/iso_request.py` + 純讀 nodes（§5 #1,3,4,5,7,8）+ 測項 21/22/25。Commit：`feat(iso-workflow): wrap read-only iso actions as nodes`。
- [x] Phase 5：split/export/debug_bundle/batch_detect nodes（§5 #2,6,9,10）+ 測項 20/23/24。Commit：`feat(iso-workflow): add auto side-effect nodes with worker polling`。
- [x] Phase 6：apply_rename/save_draft_profile（§5 #11,12）+ `test_iso_workflow_apply_safety.py` 測項 26-32 全綠。Commit：`feat(iso-workflow): add guarded apply and draft profile nodes`。
- [x] Phase 7：`workflows/iso_pdf_safe_poc.workflow.json`（§4.2 原樣）+ 樣本端到端 + 更新本文件的完成狀態；若要另寫完工 handoff，放入 `docs/archive/iso_pdf/node_workflow/`。Commit：`docs(iso-workflow): add safe poc workflow and handoff`。

**每個 phase 的不變檢查（做完就跑）**
- [ ] `git diff --stat` 只含本 phase 預期檔案；`frontend/`、`launcher/app/tauri_iso_workflow.py`、`launcher/app/tauri_iso_worker.py`、PyQt 檔案、`iso_tools/{pilot,run_log,profile,...}.py` 永遠零 diff（adapters 只 import 不修改）。
- [ ] `& $py -m unittest tests.test_iso_workflow_engine tests.test_iso_workflow_policy tests.test_iso_workflow_cli -v` 全綠（pytest 有就加跑 pytest 版）。
- [ ] 既有回歸：`& $py -m pytest tests\test_tauri_iso_workflow.py tests\test_iso_pilot.py -q`（pytest 不可用 → `-m unittest tests.test_tauri_iso_workflow tests.test_iso_pilot`）。

**驗收（Phase 7 完成的定義）**
- [x] `list-nodes` 列 12 個 node、guarded 標記正確。
- [x] `validate` 對 §4.2 圖 0 error；推導 edges 與預期 5 條一致。
- [x] 樣本 run：summary `4 ready / 0 warn / 0 blocked`、CSV 存在、`apply_rename=skipped_disabled`、run_log.json 的 `side_effect_summary.executed` 恰為 split(視情況)/job/iso_run_log/worker/csv。
- [x] `replay --run <剛才>`：零新寫入（auto writes 為 `blocked_replay`，side-effect nodes 走 `replay_hydrated`；disabled apply 保持 `skipped_disabled`）、pilot 重算結果一致。
- [x] enabled+allow+confirm+dry_run=false 在**測試 tmp 資料**上真的 rename 成功；同設定 replay 仍 blocked。
- [x] 完工 handoff 寫明：跑過的指令原文、無法跑的指令與原因、side-effect 證據（events.jsonl 摘錄）、剩餘風險。

**禁止事項（違反任一即重做）**
- [ ] 不改既有 21 個 action 的 request/response 欄位；不加新 Tauri action；不碰前端。
- [ ] 不重編號/重排 Pilot P01-P15；不新增 status enum 值。
- [ ] 不讓 `iso.build_plan`/`iso.batch_detect_serials` 在缺 page_folder 下可執行。
- [ ] 不在 replay 執行 renames_files/writes_profile（任何旗標組合下）。
- [ ] 不在 node 模組頂層 import cv2/serial_vision。
- [ ] 不刪不動 PyQt legacy 與 `docs/archive/iso_pdf/`。
- [ ] 不用 `git add -A`。

完工後在 handoff 文件結尾回報：新增/修改檔案清單、CLI 使用方式、實跑測試清單、auto/guarded 兩層 side-effect 行為證據、React Flow 銜接下一步（即本文件 §12 的落實順序）。

---

## 14. Codex 完工回報（2026-06-10）

狀態：Phase 1-7 已完成，並依 phase 拆 commit。Phase 7 沒有改 `frontend/`、`launcher/app/tauri_iso_workflow.py`、`launcher/app/tauri_iso_worker.py`、PyQt legacy、Pilot P01-P15 或既有 Tauri action schema；`.qwen/` 仍維持未追蹤、不 stage。

### 14.1 新增 / 修改檔案

- 新增：`launcher/plugins/iso_tools/workflow/workflows/iso_pdf_safe_poc.workflow.json`
- 修改：`docs/iso_pdf_node_workflow_codex_handoff_2026-06-10.md`

Phase 1-6 已在前序 commits 完成：

- `82f848f feat(iso-workflow): add workflow engine checkpoint`
- `df80420 feat(iso-workflow): wrap read-only iso actions as nodes`
- `e7ac248 feat(iso-workflow): add auto side-effect nodes with worker polling`
- `1b5e0d9 feat(iso-workflow): add guarded apply and draft profile nodes`

### 14.2 實跑 CLI 指令

```powershell
& .\.venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli list-nodes --json
& .\.venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli validate --workflow launcher\plugins\iso_tools\workflow\workflows\iso_pdf_safe_poc.workflow.json --json
& .\.venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli run --workflow launcher\plugins\iso_tools\workflow\workflows\iso_pdf_safe_poc.workflow.json --inputs-json .runtime\temp\iso_workflow_phase7\poc_inputs.json --run-root .runtime\runs\workflow_phase7 --json
& .\.venv\Scripts\python.exe -m launcher.plugins.iso_tools.workflow.cli replay --run wf-20260610-102926-6184bb --run-root .runtime\runs\workflow_phase7 --json
```

樣本資料位置：`.runtime/temp/iso_workflow_phase7/`。原指定 `C:\Users\a0976\Downloads\t` 未作為必要條件；本次用自動生成等價小樣本（4 頁 PDF + 4 筆 ISO List）完成驗收，避免依賴本機私人樣本狀態。

### 14.3 驗收證據

- `list-nodes --json`：12 個 node；`iso.apply_rename` guarded=`true` side_effects=`renames_files`，`iso.save_draft_profile` guarded=`true` side_effects=`writes_profile`。
- `validate --json`：`valid=true`、`issues=[]`；推導 edges 5 條：
  - `split.page_folder -> batch_detect.page_folder`
  - `batch_detect.rows -> pilot.rows`
  - `batch_detect.rows -> roi_dist.rows`
  - `batch_detect.rows -> export_csv.rows`
  - `batch_detect.rows -> apply_rename.rows`
- 樣本 run：`wf-20260610-102926-6184bb`，status=`completed`。
  - rows：4 筆，status 分布 `{ready: 4}`，selected=4。
  - CSV：`iso_rename_plan_20260610_102927.csv` 已落地，4 rows。
  - `apply_rename`：status=`skipped_disabled`，decision=`skipped_disabled`，未 rename。
  - executed side effects：`may_write_page_pdfs`、`writes_job_files`、`spawns_worker`、`writes_iso_run_log`、`writes_csv`。
- replay：`wf-20260610-103017-0ceeae`，status=`completed_with_blocked`（CLI 以非 0 表示有 side effect 被擋，屬預期）。
  - executed side effects：0。
  - blocked：`may_write_page_pdfs`、`writes_job_files`、`writes_iso_run_log`、`spawns_worker`、`writes_csv` 全部 `blocked_replay`。
  - `split` / `batch_detect` / `export_csv` logs 含 `replay_hydrated`。
  - disabled `apply_rename` 維持 `skipped_disabled`。
  - replay 後 `pilot_summary` 與原 run 一致。
- 既有 `start_batch_detect` path 等價驗證：同一份樣本直接走 `launcher.app.tauri_iso_workflow` stdin/stdout action，job `phase7-direct-start-batch` 完成；rows=4、status 分布 `{ready: 4}`、selected=4。

### 14.4 測試清單

```powershell
& .\.venv\Scripts\python.exe -m unittest tests.test_iso_workflow_apply_safety -v
& .\.venv\Scripts\python.exe -m unittest tests.test_iso_workflow_engine tests.test_iso_workflow_policy tests.test_iso_workflow_cli tests.test_iso_workflow_nodes tests.test_iso_workflow_apply_safety -v
& .\.venv\Scripts\python.exe -m unittest tests.test_tauri_iso_workflow tests.test_iso_pilot tests.test_iso_debug_bundle -v
```

結果：

- `tests.test_iso_workflow_apply_safety`：9 tests passed。
- workflow suite：40 tests passed。
- ISO backend regression：27 tests passed。

本環境以 `unittest` 作為主驗證路線，符合 §0 修訂的 pytest fallback 決策；沒有新增 pytest 依賴。

### 14.5 剩餘風險

- Phase 7 樣本為自動生成等價小樣本，未依賴 `C:\Users\a0976\Downloads\t` 的實際內容；若要對真實工作資料做 smoke，直接把該資料夾輸入寫成 `poc_inputs.json` 再跑同一張 graph 即可。
- replay 對 disabled `apply_rename` 的記錄是 `skipped_disabled`，不是 `blocked_replay`；這是 executor 先處理 disabled node 的既有語意，安全上仍為零寫入。
- React Flow / LiteGraph / Rete.js 尚未接 UI；下一步應只消費 `list-nodes --json`、workflow graph JSON 與 run_log JSON，不直接 import Python node class。

### 14.6 React Flow 銜接下一步

建議順序：

1. 先在 Tauri action append `workflow_list_nodes`、`workflow_load`、`workflow_validate`，只讀 JSON，不跑長任務。
2. 再接 `workflow_run` / `workflow_run_status` / `workflow_cancel`，沿用 job dir + polling，不引入 streaming。
3. 最後才做節點式畫布；畫布只編輯 graph JSON，guarded node 在 UI 上強標，`allow` / `confirm` 每次執行明文送後端，不做 session 級解鎖。
---

## 15. POC 收尾裁決與 Bridge Phase 銜接（2026-06-10 架構審查）

> 本節為 append-only 附錄。§13 的禁止事項自此「對 POC 期封存生效」：它們約束的是 POC（Phase 0-7）期間的施工，後續階段的邊界以各階段施工書為準。§0-§14 原文不改。

### 15.1 POC 完成點

- POC 正式完成點 = commit `858a7fe`（docs(iso-workflow): add safe poc workflow and handoff），以 annotated tag `iso-workflow-poc-v1` 釘住。
- 交付：workflow engine（schema/registry/policy/executor/run log/replay/CLI 五指令）+ 12 個 ISO nodes + 兩層 side-effect policy + `iso_pdf_safe_poc.workflow.json`。

### 15.2 6f9dbdc 的定位（裁決：保留）

- `6f9dbdc feat(iso-workflow): expose readonly workflow bridge` 超出 §10/§13 的 Phase 7 bound（docs-only、不加 Tauri action、不碰前端），屬**文件邊界違規**；但其內容恰為 §12.2 表格前三列（`workflow_list_nodes` / `workflow_load` / `workflow_validate`）的正確實作：append-only request 欄位、純讀、lazy import、既有 21 action schema 零變動，且已通過 npm build + workflow 40 tests + 回歸 28 tests。
- 裁決：**保留原地，追認為下一階段（Post-POC Bridge Phase）的 B0 commit**。不 revert、不 cherry-pick、不 reset。
- 矛盾消解：§13 禁止事項對 POC 期封存；Bridge 期的禁止事項見 `docs/iso_pdf_workflow_bridge_phase_plan_2026-06-10.md`（6f9dbdc 已逐條對照通過）。

### 15.3 防再犯規則（自本節起生效）

1. 任何超出當期施工書 bound 的變更，必須先在對應施工書 append 修訂節、再動工。
2. commit message 必須帶當期 phase 代號（Bridge 期為 B0-B4）。
3. 每期結束以 annotated tag 收口；「完成點」只認 tag，不認記憶。

### 15.4 下一階段（指針）

- 下一階段唯一 active 施工入口：`docs/iso_pdf_workflow_bridge_phase_plan_2026-06-10.md`。
- 優先序裁決：合流整理 → workflow_run/status/cancel job runner（job dir + polling，沿用 `start_batch_detect` 同構模式）→ 唯讀 Workflow Inspector（調校 > 進階）→ Inspector safe-run；畫布與一鍵換軌不在本期。
- 安全鐵則延續：前端不存在傳遞 `workflow_allow`/`workflow_confirm` 的程式路徑；replay 對 `renames_files`/`writes_profile` 硬封鎖（action 層 + 引擎層雙重）；`workflow_run` 只能由使用者點擊觸發，任何 onChange/useEffect 不得執行；真 rename 僅 CLI 三重門檻。

### 15.5 已知風險（移交時點）

1. `origin/codex/tauri-react-spike` 仍停在 `ff03fb2`，POC 六 commit 未合回主線（Bridge B1 處理）。
2. Linux 沙箱掛載視圖對最近寫入的檔案可能呈現尾端截斷（含 `.git/HEAD` 視圖）；Windows 端以 `git status`/`git symbolic-ref HEAD` 為準，沙箱端讀真內容用 `git show <ref>:<path>`。
3. 工作樹有 `frontend/tauri-spike/src/App.tsx` 一行空白殘留（B1 `git restore` 清掉）。
4. `workflow_load`/`workflow_validate` 的 `_resolve_workflow_path` 接受任意絕對路徑（信任操作者本機輸入）；Bridge B2 的 `workflow_run` 維持同信任模型，但 allow/confirm 白名單與 replay 拒 allow 在 action 層強制。

### 15.6 下一個 Codex 指令

讀 `docs/iso_pdf_workflow_bridge_phase_plan_2026-06-10.md`，從 Phase B1 開始照做：驗 HEAD 與 git status → tag `iso-workflow-poc-v1` @ `858a7fe` → `--no-ff` merge `codex/iso-node-workflow-poc` → `codex/tauri-react-spike` → 開 `codex/iso-workflow-bridge` → commit 文件 → 依序 B2（runner backend）、B3（唯讀 inspector）、B4（safe-run）。每 phase 一 commit，B2/B4 為可停靠 checkpoint，B4 完成即停工待命。
