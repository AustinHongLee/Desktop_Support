from __future__ import annotations

import json
from pathlib import Path

from launcher.plugins.iso_tools.workflow.policy import (
    AUTO_ALLOWED,
    GUARDED,
    REPLAY_HARD_BLOCKED,
    RENAMES_FILES,
    WRITES_CSV,
    WRITES_PROFILE,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = PROJECT_ROOT / "frontend" / "tauri-spike" / "src"
SAFE_POC = PROJECT_ROOT / "launcher" / "plugins" / "iso_tools" / "workflow" / "workflows" / "iso_pdf_safe_poc.workflow.json"


def test_frontend_never_passes_workflow_allow_or_confirm_outside_request_type() -> None:
    for path in _frontend_sources():
        text = path.read_text(encoding="utf-8")
        if path.name == "isoWorkflow.ts":
            text = _remove_interface_block(text, "IsoWorkflowRequest")
        assert "workflow_allow" not in text, f"{path} must not pass workflow_allow from frontend code"
        assert "workflow_confirm" not in text, f"{path} must not pass workflow_confirm from frontend code"


def test_safe_workflow_run_has_single_frontend_call_path_and_no_effect_autorun() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in _frontend_sources()}
    call_count = sum(text.count("runIsoNodeWorkflowSafe(") for text in sources.values())
    assert call_count <= 2

    forbidden = (
        '"workflow_run"',
        "'workflow_run'",
        "startIsoBatchDetect(",
        "runIsoNodeWorkflowSafe(",
        "runIsoOneClickWorkflow(",
        "loadIsoOneClickEngine(",
        "setIsoOneClickEngine(",
        "runIsoShadowVerify(",
        "setIsoShadowFlag(",
    )
    for path, text in sources.items():
        for block in _call_blocks(text, "useEffect"):
            for token in forbidden:
                assert token not in block, f"{path} has {token} inside useEffect; workflow/OCR must stay click-triggered"


def test_safe_poc_keeps_csv_export_and_apply_disabled() -> None:
    graph = json.loads(SAFE_POC.read_text(encoding="utf-8"))
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    assert nodes["export_csv"]["enabled"] is False
    assert nodes["export_csv"]["requires_confirm"] is True
    assert nodes["apply_rename"]["enabled"] is False
    assert nodes["apply_rename"]["requires_confirm"] is True


def test_workflow_canvas_is_readonly_display_only() -> None:
    text = (FRONTEND_SRC / "iso" / "WorkflowCanvas.tsx").read_text(encoding="utf-8")
    for token in ("runIsoNodeWorkflowSafe", "workflow_run", "applyIsoPlan", "exportIsoPlanCsv"):
        assert token not in text
    assert "nodesConnectable={false}" in text
    assert "deleteKeyCode={null}" in text
    assert "onConnect" not in text
    assert "onNodesDelete" not in text
    assert "guarded：需 CLI 三因子授權" in text


def test_workbench_param_changes_do_not_execute_workflow_actions() -> None:
    workbench_paths = [
        FRONTEND_SRC / "iso" / "WorkflowInspector.tsx",
        FRONTEND_SRC / "iso" / "WorkflowCanvas.tsx",
        FRONTEND_SRC / "iso" / "workbench" / "NodeWorkbench.tsx",
        FRONTEND_SRC / "iso" / "workbench" / "NodeDetailPanel.tsx",
        FRONTEND_SRC / "iso" / "workbench" / "nodeCards.tsx",
    ]
    forbidden = (
        "runIsoNodeWorkflowSafe(",
        "runIsoOneClickWorkflow(",
        "startIsoBatchDetect(",
        "applyIsoPlan(",
        "exportIsoPlanCsv(",
        '"workflow_run"',
        "'workflow_run'",
    )
    for path in workbench_paths:
        text = path.read_text(encoding="utf-8")
        for block in [*_call_blocks(text, "useEffect"), *_jsx_attribute_blocks(text, "onChange")]:
            for token in forbidden:
                assert token not in block, f"{path} has {token} in useEffect/onChange; workbench edits must stay dirty-only"


def test_workbench_apply_is_confirmed_and_uses_sanctioned_action() -> None:
    text = (FRONTEND_SRC / "iso" / "WorkflowInspector.tsx").read_text(encoding="utf-8")
    assert "exportIsoPlanCsv(" in text
    apply_index = text.find("applyIsoPlan(")
    assert apply_index >= 0
    assert "window.confirm" in text[max(0, apply_index - 900) : apply_index]


def test_shadow_verify_has_single_click_path_and_no_generic_ui_action() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in _frontend_sources()}
    assert sum(text.count("runIsoShadowVerify(") for text in sources.values()) == 2
    assert sum(text.count("setIsoShadowFlag(") for text in sources.values()) == 2
    for path, text in sources.items():
        if path.name == "isoWorkflow.ts":
            continue
        assert "workflow_shadow_run" not in text


def test_one_click_workflow_primary_is_click_gated_and_switch_is_single_path() -> None:
    sources = {path: path.read_text(encoding="utf-8") for path in _frontend_sources()}
    assert sum(text.count("runIsoOneClickWorkflow(") for text in sources.values()) == 2
    assert sum(text.count("setIsoOneClickEngine(") for text in sources.values()) == 2

    for path, text in sources.items():
        if path.name == "isoWorkflow.ts":
            continue
        assert "workflow_one_click_engine" not in text
        assert "workflow_set_one_click_engine" not in text


def test_policy_keeps_guarded_side_effects_out_of_auto_and_replay() -> None:
    guarded = {RENAMES_FILES, WRITES_PROFILE, WRITES_CSV}
    assert GUARDED == guarded
    assert REPLAY_HARD_BLOCKED == guarded
    assert WRITES_CSV not in AUTO_ALLOWED
    assert guarded.isdisjoint(AUTO_ALLOWED)


def _frontend_sources() -> list[Path]:
    return sorted(path for path in FRONTEND_SRC.rglob("*") if path.suffix in {".ts", ".tsx"})


def _remove_interface_block(text: str, interface_name: str) -> str:
    marker = f"interface {interface_name}"
    start = text.find(marker)
    if start < 0:
        return text
    brace = text.find("{", start)
    if brace < 0:
        return text
    end = _matching_delimiter(text, brace, "{", "}")
    if end < 0:
        return text
    return text[:start] + text[end + 1 :]


def _call_blocks(text: str, call_name: str) -> list[str]:
    blocks: list[str] = []
    offset = 0
    needle = f"{call_name}("
    while True:
        start = text.find(needle, offset)
        if start < 0:
            return blocks
        paren = text.find("(", start)
        end = _matching_delimiter(text, paren, "(", ")")
        if end < 0:
            return blocks
        blocks.append(text[start : end + 1])
        offset = end + 1


def _jsx_attribute_blocks(text: str, attr_name: str) -> list[str]:
    blocks: list[str] = []
    offset = 0
    needle = f"{attr_name}={{"
    while True:
        start = text.find(needle, offset)
        if start < 0:
            return blocks
        brace = text.find("{", start)
        end = _matching_delimiter(text, brace, "{", "}")
        if end < 0:
            return blocks
        blocks.append(text[start : end + 1])
        offset = end + 1


def _matching_delimiter(text: str, start: int, open_char: str, close_char: str) -> int:
    depth = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    for index in range(start, len(text)):
        char = text[index]
        next_char = text[index + 1] if index + 1 < len(text) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            continue
        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char == "/" and next_char == "/":
            line_comment = True
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            continue
        if char in {'"', "'", "`"}:
            quote = char
            continue
        if char == open_char:
            depth += 1
        elif char == close_char:
            depth -= 1
            if depth == 0:
                return index
    return -1
