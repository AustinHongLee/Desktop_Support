from __future__ import annotations

from dataclasses import dataclass

from launcher.core.action_model import ActionDefinition


@dataclass(frozen=True)
class PaletteMatch:
    action: ActionDefinition
    score: float


def rank_actions(
    actions: list[ActionDefinition],
    query: str,
    *,
    recent_action_ids: list[str] | None = None,
) -> list[PaletteMatch]:
    recent_weights = {
        action_id: max(1, len(recent_action_ids or []) - index)
        for index, action_id in enumerate(recent_action_ids or [])
    }
    tokens = [token for token in _normalize(query).split() if token]
    matches: list[PaletteMatch] = []
    for action in actions:
        score = _recent_score(action.id, recent_weights)
        if tokens:
            query_score = _query_score(action, tokens)
            if query_score is None:
                continue
            score += query_score
        matches.append(PaletteMatch(action=action, score=score))
    return sorted(matches, key=lambda match: (-match.score, match.action.category, match.action.title))


def _query_score(action: ActionDefinition, tokens: list[str]) -> float | None:
    searchable = _searchable_text(action)
    title = _normalize(action.title)
    category = _normalize(action.category)
    score = 0.0
    for token in tokens:
        token_score = _token_score(token, searchable)
        if token_score is None:
            return None
        if token in title:
            token_score += 35
        if token in category:
            token_score += 18
        score += token_score
    return score


def _token_score(token: str, searchable: str) -> float | None:
    if token in searchable:
        return 120 + min(40, len(token) * 3)
    subsequence = _subsequence_score(token, searchable)
    if subsequence is None:
        return None
    return subsequence


def _subsequence_score(needle: str, haystack: str) -> float | None:
    positions: list[int] = []
    start = 0
    for char in needle:
        index = haystack.find(char, start)
        if index < 0:
            return None
        positions.append(index)
        start = index + 1
    span = positions[-1] - positions[0] + 1 if positions else 0
    compactness = len(needle) / max(1, span)
    start_bonus = max(0, 18 - positions[0] * 0.25) if positions else 0
    return 45 + compactness * 40 + start_bonus


def _recent_score(action_id: str, recent_weights: dict[str, int]) -> float:
    return recent_weights.get(action_id, 0) * 12


def _searchable_text(action: ActionDefinition) -> str:
    return _normalize(" ".join([action.id, action.title, action.category, action.description, action.plugin_id]))


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").replace("-", " ").split())
