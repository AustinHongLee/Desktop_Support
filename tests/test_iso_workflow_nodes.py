from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from launcher.app.tauri_iso_workflow import IsoWorkflowRequest, build_iso_plan
from launcher.core.state_store import AppStateStore
from launcher.plugins.iso_tools.pilot import PILOT_ITEM_IDS
from launcher.plugins.iso_tools.profile import IsoNamingProfile, save_iso_naming_profile
from launcher.plugins.iso_tools.workflow.executor import run_workflow, validate_graph
from launcher.plugins.iso_tools.workflow.nodes.iso_list import LoadIsoTableNode
from launcher.plugins.iso_tools.workflow.nodes.pilot import PilotReportNode, RoiDistributionNode
from launcher.plugins.iso_tools.workflow.nodes.plan import BuildPlanNode
from launcher.plugins.iso_tools.workflow.nodes.profile import LoadProfileNode
from launcher.plugins.iso_tools.workflow.nodes.sources import DiscoverSourcesNode
from launcher.plugins.iso_tools.workflow.registry import NodeRegistry
from launcher.plugins.iso_tools.workflow.schema import normalize_graph
from tests.test_tauri_iso_workflow import _write_iso_list, _write_pdf


class IsoWorkflowNodeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = NodeRegistry()
        for node_cls in (
            DiscoverSourcesNode,
            LoadIsoTableNode,
            LoadProfileNode,
            BuildPlanNode,
            PilotReportNode,
            RoiDistributionNode,
        ):
            self.registry.register(node_cls)

    def test_discover_load_table_and_profile_nodes_wrap_existing_read_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state_path = root / "state.json"
            folder = root / "job"
            folder.mkdir()
            pdf = folder / "combine.pdf"
            iso_list = folder / "HP6-ISO圖號清單.xlsx"
            _write_pdf(pdf, pages=1)
            _write_iso_list(iso_list)
            save_iso_naming_profile(
                AppStateStore(state_path),
                folder,
                IsoNamingProfile(pattern="{serial}_{line}.pdf", iso_list_path=iso_list, sheet_name="ISO", serial_col=0, line_col=1),
            )
            graph = _graph(
                [
                    {"node_id": "discover", "node_type": "iso.discover_sources", "inputs": {"work_folder": "$workflow.inputs.work_folder"}},
                    {
                        "node_id": "table",
                        "node_type": "iso.load_iso_table",
                        "inputs": {"work_folder": "$workflow.inputs.work_folder", "iso_list": "$workflow.inputs.iso_list"},
                    },
                    {"node_id": "profile", "node_type": "iso.load_profile", "inputs": {"work_folder": "$workflow.inputs.work_folder"}},
                ],
                inputs={"work_folder": str(folder), "iso_list": str(iso_list)},
            )

            with patch.dict("os.environ", {"DESKTOP_SUPPORT_STATE_PATH": str(state_path)}):
                result = run_workflow(graph, registry=self.registry, run_root=root / "runs")

            run_dir = Path(result["run_dir"])
            candidates = _read_output(run_dir, "discover", "candidates")
            table_source = _read_output(run_dir, "table", "iso_source")
            profile = _read_output(run_dir, "profile", "profile")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(candidates["detected_combine_pdf"], str(pdf))
        self.assertEqual(candidates["detected_iso_list"], str(iso_list))
        self.assertEqual(table_source["record_count"], 2)
        self.assertEqual(profile["pattern"], "{serial}_{line}.pdf")

    def test_build_plan_pilot_and_roi_match_backend_outputs_without_ocr(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            page_folder = folder / "combine_pages"
            page_folder.mkdir()
            _write_pdf(page_folder / "page_001.pdf", pages=1)
            _write_pdf(page_folder / "page_002.pdf", pages=1)
            iso_list = folder / "iso_list.xlsx"
            _write_iso_list(iso_list)
            direct = build_iso_plan(
                IsoWorkflowRequest(
                    action="plan",
                    page_folder=page_folder,
                    iso_list=iso_list,
                    detect_serials=False,
                    confidence_threshold=0.7,
                )
            )
            graph = _graph(
                [
                    {
                        "node_id": "plan",
                        "node_type": "iso.build_plan",
                        "inputs": {
                            "page_folder": "$workflow.inputs.page_folder",
                            "iso_list": "$workflow.inputs.iso_list",
                            "confidence_threshold": "$workflow.inputs.confidence_threshold",
                        },
                    },
                    {
                        "node_id": "pilot",
                        "node_type": "iso.pilot_report",
                        "inputs": {
                            "rows": "$nodes.plan.outputs.rows",
                            "work_folder": "$workflow.inputs.work_folder",
                            "confidence_threshold": "$workflow.inputs.confidence_threshold",
                        },
                    },
                    {
                        "node_id": "roi",
                        "node_type": "iso.roi_distribution",
                        "inputs": {"rows": "$nodes.plan.outputs.rows", "confidence_threshold": "$workflow.inputs.confidence_threshold"},
                    },
                ],
                inputs={
                    "work_folder": str(folder),
                    "page_folder": str(page_folder),
                    "iso_list": str(iso_list),
                    "confidence_threshold": 0.7,
                },
            )

            result = run_workflow(graph, registry=self.registry, run_root=folder / "runs")
            run_dir = Path(result["run_dir"])
            rows = _read_output(run_dir, "plan", "rows")
            summary = _read_output(run_dir, "plan", "summary")
            pilot_results = _read_output(run_dir, "pilot", "pilot_results")
            distribution = _read_output(run_dir, "roi", "distribution")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(summary, direct["summary"])
        self.assertEqual([row["new_name"] for row in rows], [row["new_name"] for row in direct["rows"]])
        self.assertEqual([item["id"] for item in direct["pilot_results"]], list(PILOT_ITEM_IDS))
        self.assertEqual([item["id"] for item in pilot_results], list(PILOT_ITEM_IDS))
        self.assertEqual(distribution["action"], "roi_distribution")

    def test_readonly_nodes_validate_against_fallbacks_that_can_split_or_rebuild(self) -> None:
        graph = _graph(
            [
                {
                    "node_id": "plan",
                    "node_type": "iso.build_plan",
                    "inputs": {
                        "page_folder": "$workflow.inputs.page_folder",
                        "combine_pdf": "$workflow.inputs.combine_pdf",
                    },
                    "params": {"detect_serials": True},
                },
                {"node_id": "pilot", "node_type": "iso.pilot_report", "inputs": {"rows": []}},
                {"node_id": "roi", "node_type": "iso.roi_distribution", "inputs": {"rows": "$workflow.inputs.rows"}},
            ],
            inputs={"page_folder": "C:/safe/pages", "combine_pdf": "C:/unsafe/combine.pdf", "rows": []},
        )

        issues = validate_graph(graph, self.registry)
        wf015 = [issue for issue in issues if issue.code == "WF015"]

        self.assertGreaterEqual(len(wf015), 4)
        self.assertTrue(any("combine_pdf" in issue.message for issue in wf015))
        self.assertTrue(any("detect_serials" in issue.message for issue in wf015))
        self.assertTrue(any("pilot_report rows" in issue.message for issue in wf015))
        self.assertTrue(any("roi_distribution rows" in issue.message for issue in wf015))


def _graph(nodes: list[dict], *, inputs: dict):
    return normalize_graph(
        {
            "schema_version": 1,
            "workflow_id": "iso_node_test",
            "display_name": "ISO Node Test",
            "description": "Phase 4 node tests",
            "inputs": inputs,
            "nodes": nodes,
        }
    )


def _read_output(run_dir: Path, node_id: str, port: str) -> object:
    run_log = json.loads((run_dir / "run_log.json").read_text(encoding="utf-8"))
    artifact_ref = run_log["nodes"][node_id]["outputs"][port]["artifact_ref"]
    return json.loads((run_dir / artifact_ref).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
