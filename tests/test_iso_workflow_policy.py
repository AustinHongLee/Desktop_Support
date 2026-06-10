from __future__ import annotations

import unittest

from launcher.plugins.iso_tools.workflow.errors import UndeclaredSideEffectError
from launcher.plugins.iso_tools.workflow.policy import (
    RENAMES_FILES,
    WRITES_CSV,
    SideEffectGate,
    SideEffectPolicy,
)


class IsoWorkflowPolicyTests(unittest.TestCase):
    def test_auto_allowed_runs_without_confirm(self) -> None:
        gate = SideEffectGate(
            node_id="export",
            declared_effects=(WRITES_CSV,),
            requires_confirm=False,
            policy=SideEffectPolicy(mode="run"),
        )

        self.assertEqual(gate.request(WRITES_CSV), "executed")

    def test_guarded_blocks_without_allow_and_confirm(self) -> None:
        gate = SideEffectGate(
            node_id="apply",
            declared_effects=(RENAMES_FILES,),
            requires_confirm=True,
            policy=SideEffectPolicy(mode="run"),
        )

        self.assertEqual(gate.request(RENAMES_FILES), "blocked_policy")

    def test_guarded_executes_with_allow_and_confirm(self) -> None:
        gate = SideEffectGate(
            node_id="apply",
            declared_effects=(RENAMES_FILES,),
            requires_confirm=True,
            policy=SideEffectPolicy(
                mode="run",
                allowed_guarded=frozenset({RENAMES_FILES}),
                confirmed_nodes=frozenset({"apply"}),
            ),
        )

        self.assertEqual(gate.request(RENAMES_FILES), "executed")

    def test_dry_run_skips_any_side_effect(self) -> None:
        gate = SideEffectGate(
            node_id="apply",
            declared_effects=(RENAMES_FILES,),
            requires_confirm=True,
            policy=SideEffectPolicy(mode="dry_run", allowed_guarded=frozenset({RENAMES_FILES}), confirmed_nodes=frozenset({"apply"})),
        )

        self.assertEqual(gate.request(RENAMES_FILES), "skipped_dry_run")

    def test_replay_hard_blocks_renames_even_when_confirmed(self) -> None:
        gate = SideEffectGate(
            node_id="apply",
            declared_effects=(RENAMES_FILES,),
            requires_confirm=True,
            policy=SideEffectPolicy(mode="replay", allowed_guarded=frozenset({RENAMES_FILES}), confirmed_nodes=frozenset({"apply"}), include_auto_in_replay=True),
        )

        self.assertEqual(gate.request(RENAMES_FILES), "blocked_replay")

    def test_replay_auto_side_effect_requires_include_flag(self) -> None:
        blocked = SideEffectGate(
            node_id="export",
            declared_effects=(WRITES_CSV,),
            requires_confirm=False,
            policy=SideEffectPolicy(mode="replay"),
        )
        allowed = SideEffectGate(
            node_id="export",
            declared_effects=(WRITES_CSV,),
            requires_confirm=False,
            policy=SideEffectPolicy(mode="replay", include_auto_in_replay=True),
        )

        self.assertEqual(blocked.request(WRITES_CSV), "blocked_replay")
        self.assertEqual(allowed.request(WRITES_CSV), "executed")

    def test_undeclared_side_effect_raises(self) -> None:
        gate = SideEffectGate(
            node_id="export",
            declared_effects=(),
            requires_confirm=False,
            policy=SideEffectPolicy(mode="run"),
        )

        with self.assertRaises(UndeclaredSideEffectError):
            gate.request(WRITES_CSV)


if __name__ == "__main__":
    unittest.main()
