# ISO PDF Docs Current Status

> Last organized: 2026-06-09
> Branch: `codex/tauri-react-spike`
> Status: ISO PDF Pilot uplift is complete. Old ISO PDF planning docs are archived history, not active TODO.

## Read This First

- Current completion handoff: `docs/iso_pdf_pilot_uplift_handoff_codex_2026-06-09.md`
- Historical design archive: `docs/archive/iso_pdf/`
- Current source of truth: code plus the verification commands in the completion handoff.

The old design files were useful while deciding the shape of the ISO PDF workbench, but they now describe past planning. They should not be read as "still needs to be built".

## Current State

| Area | Status | Notes |
|---|---|---|
| Pilot schema v2 | Done | P01-P15 are wired into backend and frontend flows. |
| Workbench Pilot guidance | Done | Summary strip, problem navigation, and table layout polish are in place. |
| Engineer tuning page | Done | Layout was rebuilt around settings, PDF visual check, ROI tools, Pilot list, and legacy fallback. |
| Autopilot page | Done | Shows human-readable progress and failure guidance without exposing engineer-only controls. |
| ROI slider freeze risk | Fixed | ROI preview/OCR is debounced so dragging sliders does not rerun recognition on every movement. |
| Verification | Done | Frontend build, targeted Python tests, sample batch, and layout checks are recorded in the handoff. |

## Optional Backlog

These are future enhancements, not blockers for the current uplift:

1. P16 `export_log`: CSV / run log / debug bundle readiness check.
2. P17 `apply_safety`: target file lock / rollback / disk safety check before apply.
3. Let `stateMachine` apply guard consume Pilot `blocks_apply` after parity tests prove it matches row-count behavior.
4. Add fuller Tauri UI automation beyond the focused checks already used.
5. Long-term convergence between legacy PyQt validator and Tauri Pilot.

## Archive Map

| Archived file | Role |
|---|---|
| `docs/archive/iso_pdf/iso_pdf_pilot_uplift_plan_2026-06-09.md` | Design mother file for the completed uplift. |
| `docs/archive/iso_pdf/iso_pdf_workbench_integrated_execution_plan_2026-06-08.md` | Earlier combined execution route and boundary decision. |
| `docs/archive/iso_pdf/iso_pdf_next_stage_design_2026-06-08.md` | Broad next-stage design exploration. |
| `docs/archive/iso_pdf/iso_pdf_workbench_blueprint_v0.2.md` | Workbench pilot blueprint reference. |
| `docs/archive/iso_pdf/iso_pdf_workbench_pilot_plan_v0.1.md` | Earlier three-layer workbench / recovery plan. |
| `docs/archive/iso_pdf/iso_pdf_workbench_next_stage_v0.1.md` | Earlier PyQt-oriented next-stage proposal. |
| `docs/archive/iso_pdf/iso_pdf_workbench_audit.md` | Historical PyQt audit and UX/OCR pain-point analysis. |
| `docs/archive/iso_pdf/ISO工作台_舊版轉新版_功能落差與UI重分配_v0.1.md` | Historical PyQt-to-Tauri gap analysis. |
| `docs/archive/iso_pdf/codex_指令書_ISO一鍵工作台_重做_v0.1.md` | Historical implementation prompt/spec. |

When in doubt, trust this file, the completion handoff, and the current source code over archived planning notes.
