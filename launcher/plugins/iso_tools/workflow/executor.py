from __future__ import annotations

import heapq
import json
import time
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from launcher.plugins.iso_tools.workflow import WORKFLOW_SCHEMA_VERSION
from launcher.plugins.iso_tools.workflow.context import ArtifactStore, NodeExecutionContext, WorkflowContext, json_safe
from launcher.plugins.iso_tools.workflow.errors import GraphValidationError, WorkflowCancelledError
from launcher.plugins.iso_tools.workflow.policy import GUARDED, REPLAY_HARD_BLOCKED, SideEffectGate, SideEffectPolicy
from launcher.plugins.iso_tools.workflow.registry import NodeRegistry, get_registry
from launcher.plugins.iso_tools.workflow.run_log import WorkflowRunLogWriter
from launcher.plugins.iso_tools.workflow.schema import (
    EdgeSpec,
    NodeInstance,
    ValidationIssue,
    WorkflowGraph,
    load_workflow,
    normalize_graph,
    parse_node_output_ref,
    parse_workflow_input_ref,
)


def validate_graph(graph: WorkflowGraph, registry: NodeRegistry | None = None) -> list[ValidationIssue]:
    registry = registry or get_registry()
    issues: list[ValidationIssue] = []
    if graph.schema_version != WORKFLOW_SCHEMA_VERSION:
        issues.append(_issue("WF001", f"unsupported schema_version: {graph.schema_version}"))

    counts = Counter(node.node_id for node in graph.nodes)
    for node_id, count in counts.items():
        if count > 1:
            issues.append(_issue("WF002", f"duplicate node_id: {node_id}", node_id=node_id))

    node_map = graph.node_map()
    for node in graph.nodes:
        if not registry.has(node.node_type):
            issues.append(_issue("WF003", f"unknown node_type: {node.node_type}", node_id=node.node_id))

    for edge in graph.edges:
        if edge.from_node not in node_map or edge.to_node not in node_map:
            issues.append(_issue("WF004", "edge endpoint node does not exist", edge=edge.label()))
            continue
        from_node = node_map[edge.from_node]
        to_node = node_map[edge.to_node]
        if registry.has(from_node.node_type) and edge.from_output not in registry.get_spec(from_node.node_type).output_names():
            issues.append(_issue("WF005", f"unknown output port: {edge.from_output}", node_id=edge.from_node, edge=edge.label()))
        if registry.has(to_node.node_type) and edge.to_input not in registry.get_spec(to_node.node_type).input_names():
            issues.append(_issue("WF005", f"unknown input port: {edge.to_input}", node_id=edge.to_node, edge=edge.label()))

    inferred = graph.metadata.get("_inferred_edges")
    declared = graph.metadata.get("_declared_edges")
    if inferred is not None and declared is not None and _edge_set(inferred) != _edge_set(declared):
        issues.append(_issue("WF009", "declared edges differ from input refs"))

    for node in graph.nodes:
        if not registry.has(node.node_type):
            continue
        spec = registry.get_spec(node.node_type)
        for input_name, raw_value in node.inputs.items():
            _validate_ref(raw_value, graph, node_map, registry, issues, node, input_name)
        incoming = {(edge.to_node, edge.to_input) for edge in graph.edges}
        for port in spec.inputs:
            has_input = port.name in node.inputs and node.inputs.get(port.name) is not None
            has_edge = (node.node_id, port.name) in incoming
            if port.required and not has_input and not has_edge:
                issues.append(_issue("WF007", f"required input unresolved: {port.name}", node_id=node.node_id))
        issues.extend(_validate_params(node, spec.params_schema))
        spec_effects = set(spec.side_effects)
        instance_effects = set(node.side_effects)
        if not instance_effects:
            instance_effects = spec_effects
        missing = spec_effects - instance_effects
        extra = instance_effects - spec_effects
        if missing:
            issues.append(_issue("WF011", f"side_effects under-report: {sorted(missing)}", node_id=node.node_id))
        if extra:
            issues.append(_issue("WF012", f"side_effects over-report: {sorted(extra)}", node_id=node.node_id, severity="warning"))
        guarded = spec.guarded or bool(spec_effects & GUARDED)
        if guarded and node.enabled and node.requires_confirm is not True:
            issues.append(_issue("WF014", "guarded node must set requires_confirm: true", node_id=node.node_id))
        try:
            issues.extend(registry.create(node.node_type).validate(node, graph))
        except Exception as exc:  # noqa: BLE001 - validation should surface as issue, not crash
            issues.append(_issue("WF015", f"node validation failed: {exc}", node_id=node.node_id))

    try:
        topological_order(graph)
    except GraphValidationError as exc:
        issues.extend(exc.issues)
    return issues


def topological_order(graph: WorkflowGraph) -> list[str]:
    node_ids = [node.node_id for node in graph.nodes]
    indegree = {node_id: 0 for node_id in node_ids}
    adjacency: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        if edge.from_node not in indegree or edge.to_node not in indegree:
            continue
        if edge.to_node not in adjacency[edge.from_node]:
            adjacency[edge.from_node].add(edge.to_node)
            indegree[edge.to_node] += 1
    heap = [node_id for node_id, degree in indegree.items() if degree == 0]
    heapq.heapify(heap)
    order: list[str] = []
    while heap:
        node_id = heapq.heappop(heap)
        order.append(node_id)
        for next_node in sorted(adjacency[node_id]):
            indegree[next_node] -= 1
            if indegree[next_node] == 0:
                heapq.heappush(heap, next_node)
    if len(order) != len(node_ids):
        remaining = [node_id for node_id in node_ids if node_id not in set(order)]
        raise GraphValidationError([_issue("WF006", f"cycle detected around: {' -> '.join(remaining)}")])
    return order


def run_workflow(
    graph: WorkflowGraph,
    *,
    inputs: dict[str, Any] | None = None,
    registry: NodeRegistry | None = None,
    run_root: Path | None = None,
    policy: SideEffectPolicy | None = None,
    source_run_dir: Path | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    registry = registry or get_registry()
    policy = policy or SideEffectPolicy()
    issues = validate_graph(graph, registry)
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise GraphValidationError(errors)
    topology = topological_order(graph)
    workflow_inputs = {**graph.inputs, **(inputs or {})}
    run_id = _new_run_id()
    root = run_root or (Path.cwd() / ".runtime" / "runs" / "workflow")
    run_dir = root / run_id
    log = WorkflowRunLogWriter(
        run_id=run_id,
        run_dir=run_dir,
        graph=graph,
        mode=policy.mode,
        policy=policy,
        source_run_id=source_run_dir.name if source_run_dir else None,
    )
    artifacts = ArtifactStore(run_dir, on_artifact=log.record_artifact)
    ctx = WorkflowContext(run_id, run_dir, graph, workflow_inputs, policy, log, artifacts, should_cancel=should_cancel)
    source_log = _read_source_log(source_run_dir)
    log.start(inputs=workflow_inputs, topology=topology)
    _notify(
        on_update,
        {
            "event": "run_started",
            "run_id": run_id,
            "run_dir": str(run_dir),
            "topology": topology,
            "total": len(topology),
            "done": 0,
            "current_node": "",
        },
    )

    run_status = "completed"
    node_map = graph.node_map()
    for index, node_id in enumerate(topology):
        if _cancel_requested(should_cancel):
            run_status = "cancelled"
            _record_not_run_nodes(log, ctx, node_map, registry, topology[index:], on_update=on_update, done=index, total=len(topology))
            break
        instance = node_map[node_id]
        spec = registry.get_spec(instance.node_type)
        declared_effects = _declared_effects(instance, spec)
        if not instance.enabled:
            ended_at = _now()
            records = [_skip_record(log, node_id, kind, "skipped_disabled") for kind in declared_effects]
            log.node_finished(
                node_id=node_id,
                status="skipped_disabled",
                started_at=ended_at,
                ended_at=ended_at,
                duration_ms=0,
                outputs={},
                side_effects=records,
            )
            ctx.node_outputs[node_id] = {}
            _notify_node_finished(on_update, node_id, "skipped_disabled", index + 1, len(topology))
            continue
        if _should_hydrate_replay(policy, declared_effects):
            records = _record_replay_blocks(log, node_id, declared_effects)
            outputs, output_refs = _hydrate_outputs(source_log, source_run_dir, node_id)
            ctx.node_outputs[node_id] = outputs
            status = "blocked" if records else "success"
            ended_at = _now()
            log.node_finished(
                node_id=node_id,
                status=status,
                started_at=ended_at,
                ended_at=ended_at,
                duration_ms=0,
                outputs=output_refs,
                side_effects=records,
                logs=[{"code": "replay_hydrated", "node_id": node_id}],
            )
            if records:
                run_status = "completed_with_blocked"
            _notify_node_finished(on_update, node_id, status, index + 1, len(topology))
            continue

        started_at = _now()
        started = time.perf_counter()
        log.node_started(node_id, instance.node_type)
        _notify(
            on_update,
            {
                "event": "node_started",
                "node_id": node_id,
                "node_type": instance.node_type,
                "done": index,
                "total": len(topology),
                "current_node": node_id,
            },
        )
        gate = SideEffectGate(
            node_id=node_id,
            declared_effects=declared_effects,
            requires_confirm=bool(instance.requires_confirm),
            policy=policy,
            on_record=log.record_side_effect,
        )
        exec_ctx = NodeExecutionContext(
            workflow=ctx,
            node_id=node_id,
            inputs=_resolve_inputs(instance, spec, ctx),
            params=_resolve_params(instance, spec.params_schema),
            gate=gate,
        )
        try:
            node = registry.create(instance.node_type)
            raw_outputs = node.run(exec_ctx)
            missing_effects = set(declared_effects) - {record.kind for record in gate.records}
            if missing_effects:
                raise RuntimeError(f"missing side-effect decisions: {sorted(missing_effects)}")
            ctx.node_outputs[node_id] = raw_outputs
            output_refs = {
                port: artifacts.write_json(node_id, port, value)
                for port, value in raw_outputs.items()
            }
            status = "blocked" if exec_ctx.blocked_reason else "success"
            if status == "blocked":
                run_status = "completed_with_blocked"
            log.node_finished(
                node_id=node_id,
                status=status,
                started_at=started_at,
                ended_at=_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
                outputs=output_refs,
                side_effects=[record.to_payload() for record in gate.records],
                logs=exec_ctx.logs,
                error={"message": exec_ctx.blocked_reason} if exec_ctx.blocked_reason else None,
                resolved_inputs_digest=_digest_inputs(exec_ctx.inputs),
            )
            _notify_node_finished(on_update, node_id, status, index + 1, len(topology))
        except WorkflowCancelledError as exc:
            run_status = "cancelled"
            log.node_finished(
                node_id=node_id,
                status="cancelled",
                started_at=started_at,
                ended_at=_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
                outputs={},
                side_effects=[record.to_payload() for record in gate.records],
                logs=exec_ctx.logs,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            _notify_node_finished(on_update, node_id, "cancelled", index + 1, len(topology))
            _record_not_run_nodes(log, ctx, node_map, registry, topology[index + 1 :], on_update=on_update, done=index + 1, total=len(topology))
            break
        except Exception as exc:  # noqa: BLE001 - executor records node failure
            run_status = "failed"
            log.node_finished(
                node_id=node_id,
                status="failed",
                started_at=started_at,
                ended_at=_now(),
                duration_ms=int((time.perf_counter() - started) * 1000),
                outputs={},
                side_effects=[record.to_payload() for record in gate.records],
                logs=exec_ctx.logs,
                error={"type": type(exc).__name__, "message": str(exc)},
            )
            _notify_node_finished(on_update, node_id, "failed", index + 1, len(topology))
            break

    result = log.finish(status=run_status, topology=topology)
    _notify(
        on_update,
        {
            "event": "run_finished",
            "status": run_status,
            "run_id": run_id,
            "run_dir": str(run_dir),
            "done": len(topology),
            "total": len(topology),
            "current_node": "",
        },
    )
    return result


def replay_workflow(
    source_run_dir: Path,
    *,
    registry: NodeRegistry | None = None,
    run_root: Path | None = None,
    policy: SideEffectPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = _read_source_log(source_run_dir)
    graph = normalize_graph(source["workflow"])
    inputs = dict(source.get("inputs") or {})
    replay_policy = policy or SideEffectPolicy(mode="replay")
    return run_workflow(
        graph,
        inputs=inputs,
        registry=registry,
        run_root=run_root,
        policy=replay_policy,
        source_run_dir=source_run_dir,
        should_cancel=should_cancel,
        on_update=on_update,
    )


def run_single_node(
    source_run_dir: Path,
    node_id: str,
    *,
    registry: NodeRegistry | None = None,
    run_root: Path | None = None,
    policy: SideEffectPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = _read_source_log(source_run_dir)
    graph = normalize_graph(source["workflow"])
    target = graph.node_map().get(node_id)
    if target is None:
        raise KeyError(f"unknown node_id: {node_id}")
    target_inputs = _hydrate_node_ref_inputs(source, source_run_dir, target.inputs)
    target = NodeInstance(
        node_id=target.node_id,
        node_type=target.node_type,
        display_name=target.display_name,
        inputs=target_inputs,
        outputs=dict(target.outputs),
        params=dict(target.params),
        enabled=target.enabled,
        requires_confirm=target.requires_confirm,
        side_effects=tuple(target.side_effects),
    )
    graph = WorkflowGraph(
        schema_version=graph.schema_version,
        workflow_id=f"{graph.workflow_id}_single_{node_id}",
        display_name=f"Single node: {node_id}",
        description=graph.description,
        inputs=dict(source.get("inputs") or {}),
        nodes=[target],
        edges=[],
        metadata={},
    )
    return run_workflow(
        graph,
        registry=registry,
        run_root=run_root,
        policy=policy or SideEffectPolicy(),
        source_run_dir=source_run_dir,
        should_cancel=should_cancel,
        on_update=on_update,
    )


def run_from_node(
    source_run_dir: Path,
    start_node: str,
    *,
    inputs: dict[str, Any] | None = None,
    registry: NodeRegistry | None = None,
    run_root: Path | None = None,
    policy: SideEffectPolicy | None = None,
    should_cancel: Callable[[], bool] | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    source = _read_source_log(source_run_dir)
    graph = normalize_graph(source["workflow"])
    topology = topological_order(graph)
    if start_node not in graph.node_map():
        raise KeyError(f"unknown node_id: {start_node}")
    rerun_ids = _downstream_node_ids(graph, start_node, topology)
    nodes = [_rerun_node_with_hydrated_upstream_inputs(source, source_run_dir, node, rerun_ids) for node in graph.nodes if node.node_id in rerun_ids]
    rerun_graph = WorkflowGraph(
        schema_version=graph.schema_version,
        workflow_id=f"{graph.workflow_id}_from_{start_node}",
        display_name=f"Rerun from: {start_node}",
        description=graph.description,
        inputs=dict(source.get("inputs") or {}),
        nodes=nodes,
        edges=[edge for edge in graph.edges if edge.from_node in rerun_ids and edge.to_node in rerun_ids],
        metadata={"source_workflow_id": graph.workflow_id, "rerun_from": start_node},
    )
    return run_workflow(
        rerun_graph,
        inputs={**dict(source.get("inputs") or {}), **(inputs or {})},
        registry=registry,
        run_root=run_root,
        policy=policy or SideEffectPolicy(),
        source_run_dir=source_run_dir,
        should_cancel=should_cancel,
        on_update=on_update,
    )


def _record_not_run_nodes(
    log: WorkflowRunLogWriter,
    ctx: WorkflowContext,
    node_map: dict[str, NodeInstance],
    registry: NodeRegistry,
    node_ids: list[str],
    *,
    on_update: Callable[[dict[str, Any]], None] | None,
    done: int,
    total: int,
) -> None:
    for offset, node_id in enumerate(node_ids):
        instance = node_map[node_id]
        spec = registry.get_spec(instance.node_type)
        effects = _declared_effects(instance, spec)
        records = [_skip_record(log, node_id, kind, "not_run") for kind in effects]
        ended_at = _now()
        log.node_finished(
            node_id=node_id,
            status="not_run",
            started_at=ended_at,
            ended_at=ended_at,
            duration_ms=0,
            outputs={},
            side_effects=records,
        )
        ctx.node_outputs[node_id] = {}
        _notify_node_finished(on_update, node_id, "not_run", done + offset + 1, total)


def _downstream_node_ids(graph: WorkflowGraph, start_node: str, topology: list[str]) -> set[str]:
    selected = {start_node}
    changed = True
    while changed:
        changed = False
        for edge in graph.edges:
            if edge.from_node in selected and edge.to_node not in selected:
                selected.add(edge.to_node)
                changed = True
    return {node_id for node_id in topology if node_id in selected}


def _rerun_node_with_hydrated_upstream_inputs(
    source_log: dict[str, Any],
    source_run_dir: Path,
    node: NodeInstance,
    rerun_ids: set[str],
) -> NodeInstance:
    inputs: dict[str, Any] = {}
    for input_name, raw in node.inputs.items():
        parsed = parse_node_output_ref(raw)
        if parsed is not None and parsed[0] not in rerun_ids:
            value = _read_output_artifact(source_log, source_run_dir, parsed[0], parsed[1])
            if value is None:
                raise KeyError(f"missing source artifact for {raw}")
            inputs[input_name] = value
        else:
            inputs[input_name] = raw
    return NodeInstance(
        node_id=node.node_id,
        node_type=node.node_type,
        display_name=node.display_name,
        inputs=inputs,
        outputs=dict(node.outputs),
        params=dict(node.params),
        enabled=node.enabled,
        requires_confirm=node.requires_confirm,
        side_effects=tuple(node.side_effects),
    )


def _notify_node_finished(
    on_update: Callable[[dict[str, Any]], None] | None,
    node_id: str,
    status: str,
    done: int,
    total: int,
) -> None:
    _notify(
        on_update,
        {
            "event": "node_finished",
            "node_id": node_id,
            "status": status,
            "done": done,
            "total": total,
            "current_node": "" if done >= total else node_id,
        },
    )


def _notify(on_update: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if on_update is not None:
        on_update(json_safe(payload))


def _cancel_requested(should_cancel: Callable[[], bool] | None) -> bool:
    return bool(should_cancel and should_cancel())


def _validate_ref(
    raw_value: Any,
    graph: WorkflowGraph,
    node_map: dict[str, NodeInstance],
    registry: NodeRegistry,
    issues: list[ValidationIssue],
    node: NodeInstance,
    input_name: str,
) -> None:
    if not isinstance(raw_value, str) or not raw_value.startswith("$") or raw_value.startswith("$$"):
        return
    workflow_input = parse_workflow_input_ref(raw_value)
    if workflow_input is not None:
        if workflow_input not in graph.inputs:
            issues.append(_issue("WF008", f"unknown workflow input ref: {workflow_input}", node_id=node.node_id))
        return
    parsed = parse_node_output_ref(raw_value)
    if parsed is None:
        issues.append(_issue("WF008", f"invalid ref syntax for {input_name}: {raw_value}", node_id=node.node_id))
        return
    from_node_id, from_output = parsed
    from_node = node_map.get(from_node_id)
    if from_node is None:
        issues.append(_issue("WF008", f"unknown node ref: {from_node_id}", node_id=node.node_id))
        return
    if registry.has(from_node.node_type) and from_output not in registry.get_spec(from_node.node_type).output_names():
        issues.append(_issue("WF008", f"unknown node output ref: {from_node_id}.{from_output}", node_id=node.node_id))


def _validate_params(node: NodeInstance, schema: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    for name, rules in schema.items():
        if not isinstance(rules, dict):
            continue
        if rules.get("required") and name not in node.params:
            issues.append(_issue("WF010", f"missing required param: {name}", node_id=node.node_id))
            continue
        if name not in node.params:
            continue
        value = node.params[name]
        expected = rules.get("type")
        if expected and not _type_matches(value, expected):
            issues.append(_issue("WF010", f"param type mismatch: {name}", node_id=node.node_id))
        if "enum" in rules and value not in rules["enum"]:
            issues.append(_issue("WF010", f"param enum mismatch: {name}", node_id=node.node_id))
    return issues


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "text":
        return isinstance(value, str)
    if expected == "json":
        return True
    return True


def _resolve_inputs(instance: NodeInstance, spec: Any, ctx: WorkflowContext) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    for port in spec.inputs:
        raw = instance.inputs.get(port.name)
        if isinstance(raw, str) and raw.startswith("$$"):
            value = raw[1:]
        elif parse_workflow_input_ref(raw) is not None:
            value = ctx.workflow_inputs.get(parse_workflow_input_ref(raw))
        elif parse_node_output_ref(raw) is not None:
            source_node, source_port = parse_node_output_ref(raw) or ("", "")
            value = ctx.node_outputs.get(source_node, {}).get(source_port)
        else:
            value = raw
        if value is None and port.required:
            raise RuntimeError(f"required input unresolved: {port.name}")
        resolved[port.name] = value
    return resolved


def _resolve_params(instance: NodeInstance, params_schema: dict[str, Any]) -> dict[str, Any]:
    params = dict(instance.params)
    for name, rules in params_schema.items():
        if isinstance(rules, dict) and "default" in rules and name not in params:
            params[name] = rules["default"]
    return params


def _declared_effects(instance: NodeInstance, spec: Any) -> tuple[str, ...]:
    return tuple(instance.side_effects or spec.side_effects)


def _should_hydrate_replay(policy: SideEffectPolicy, effects: tuple[str, ...]) -> bool:
    if policy.mode != "replay" or not effects:
        return False
    if set(effects) & REPLAY_HARD_BLOCKED:
        return True
    return not policy.include_auto_in_replay


def _record_replay_blocks(log: WorkflowRunLogWriter, node_id: str, effects: tuple[str, ...]) -> list[dict[str, Any]]:
    records = []
    for kind in effects:
        record = {
            "node_id": node_id,
            "kind": kind,
            "decision": "blocked_replay",
            "detail": {},
            "at": _now(),
        }
        log.append_event("side_effect_decision", **record)
        records.append(record)
    return records


def _skip_record(log: WorkflowRunLogWriter, node_id: str, kind: str, decision: str) -> dict[str, Any]:
    record = {"node_id": node_id, "kind": kind, "decision": decision, "detail": {}, "at": _now()}
    log.append_event("side_effect_decision", **record)
    return record


def _hydrate_outputs(source_log: dict[str, Any], source_run_dir: Path | None, node_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    if not source_log or source_run_dir is None:
        return {}, {}
    node_payload = (source_log.get("nodes") or {}).get(node_id) or {}
    refs = node_payload.get("outputs") or {}
    outputs: dict[str, Any] = {}
    for port, ref_payload in refs.items():
        if isinstance(ref_payload, dict) and ref_payload.get("artifact_ref"):
            artifact_path = source_run_dir / str(ref_payload["artifact_ref"])
            if artifact_path.exists():
                outputs[port] = json.loads(artifact_path.read_text(encoding="utf-8"))
    return outputs, refs


def _hydrate_node_ref_inputs(source_log: dict[str, Any], source_run_dir: Path, inputs: dict[str, Any]) -> dict[str, Any]:
    hydrated = dict(inputs)
    for input_name, raw in inputs.items():
        parsed = parse_node_output_ref(raw)
        if parsed is None:
            continue
        source_node, source_port = parsed
        value = _read_output_artifact(source_log, source_run_dir, source_node, source_port)
        if value is None:
            raise KeyError(f"missing source artifact for {raw}")
        hydrated[input_name] = value
    return hydrated


def _read_output_artifact(source_log: dict[str, Any], source_run_dir: Path, node_id: str, port: str) -> Any:
    node_payload = (source_log.get("nodes") or {}).get(node_id) or {}
    ref_payload = (node_payload.get("outputs") or {}).get(port)
    if not isinstance(ref_payload, dict) or not ref_payload.get("artifact_ref"):
        return None
    artifact_path = source_run_dir / str(ref_payload["artifact_ref"])
    if not artifact_path.exists():
        return None
    return json.loads(artifact_path.read_text(encoding="utf-8"))


def _read_source_log(source_run_dir: Path | None) -> dict[str, Any]:
    if source_run_dir is None:
        return {}
    path = source_run_dir / "run_log.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _digest_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    digest: dict[str, Any] = {}
    for key, value in inputs.items():
        if isinstance(value, list):
            digest[key] = {"type": "list", "len": len(value)}
        elif isinstance(value, dict):
            digest[key] = {"type": "dict", "keys": sorted(str(item) for item in value)[:20]}
        else:
            digest[key] = json_safe(value)
    return digest


def _edge_set(items: list[dict[str, Any]]) -> set[tuple[str, str, str, str]]:
    return {
        (str(item.get("from_node")), str(item.get("from_output")), str(item.get("to_node")), str(item.get("to_input")))
        for item in items
    }


def _issue(code: str, message: str, *, node_id: str = "", edge: str = "", severity: str = "error") -> ValidationIssue:
    return ValidationIssue(severity=severity, code=code, message=message, node_id=node_id, edge=edge)


def _new_run_id() -> str:
    return f"wf-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
