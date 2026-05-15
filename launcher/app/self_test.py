from __future__ import annotations

from launcher.core.context_model import LauncherContext
from launcher.core.paths import plugin_root, project_root
from launcher.core.registry import ActionRegistry
from launcher.core.runner import ActionRunner


def run_self_test() -> int:
    registry = ActionRegistry(plugin_root())
    report = registry.load()
    print(f"Loaded {len(registry.plugins)} plugin(s), {len(registry.actions)} action(s).")
    if report.issues:
        print(f"Plugin load issues: {len(report.issues)}")
        for issue in report.issues:
            print(f"- {issue.path}: {issue.message}")

    action = registry.actions.get("diagnostics.echo_context")
    if action is None:
        print("Missing diagnostics.echo_context action.")
        return 1

    context = LauncherContext(folder=project_root(), source="self-test")
    result = ActionRunner().run(action, context)
    for event in result.events:
        print(f"[{event.type}] {event.message}")
    print(f"Result: {'OK' if result.ok else 'FAILED'}")
    return 0 if result.ok else 1
