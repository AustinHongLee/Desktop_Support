from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from launcher.plugins.iso_tools.workflow.nodes.base import WorkflowNode
    from launcher.plugins.iso_tools.workflow.schema import NodeSpec


class NodeRegistry:
    def __init__(self) -> None:
        self._classes: dict[str, type[WorkflowNode]] = {}

    def register(self, node_cls: type[WorkflowNode]) -> None:
        node_type = node_cls.spec.node_type
        if node_type in self._classes and self._classes[node_type] is not node_cls:
            raise ValueError(f"duplicate workflow node type: {node_type}")
        self._classes[node_type] = node_cls

    def create(self, node_type: str) -> WorkflowNode:
        return self._classes[node_type]()

    def get_spec(self, node_type: str) -> NodeSpec:
        return self._classes[node_type].spec

    def list_specs(self) -> list[NodeSpec]:
        return [self._classes[key].spec for key in sorted(self._classes)]

    def has(self, node_type: str) -> bool:
        return node_type in self._classes

    def clear_for_tests(self) -> None:
        self._classes.clear()


_REGISTRY = NodeRegistry()
_NODES_IMPORTED = False


def register_node(cls: type[WorkflowNode]) -> type[WorkflowNode]:
    _REGISTRY.register(cls)
    return cls


def get_registry() -> NodeRegistry:
    global _NODES_IMPORTED
    if not _NODES_IMPORTED:
        import launcher.plugins.iso_tools.workflow.nodes  # noqa: F401

        _NODES_IMPORTED = True
    return _REGISTRY
