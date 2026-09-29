"""Fuzzy string matching utilities for Karina."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Generic, List, Optional, Tuple, TypeVar

T = TypeVar("T")

DEFAULT_THRESHOLD = 0.65
AMBIGUITY_GAP = 0.08


def active_threshold(override: Optional[float] = None) -> float:
    if override is not None:
        return override
    try:
        from config import get_settings

        return get_settings().fuzzy_threshold
    except Exception:
        return DEFAULT_THRESHOLD


@dataclass
class FuzzyMatch(Generic[T]):
    item: T
    index: int
    score: float
    label: str


def _normalize(text: str) -> str:
    return text.strip().lower()


def match_score(query: str, candidate: str) -> float:
    """Score how well query matches candidate using sequence, token, and substring signals."""
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0.0

    sequence = SequenceMatcher(None, q, c).ratio()

    q_tokens = q.split()
    c_tokens = c.split()
    if q_tokens:
        token_scores = [
            max(1.0 if token in c_token else SequenceMatcher(None, token, c_token).ratio() for c_token in c_tokens)
            for token in q_tokens
        ]
        token = sum(token_scores) / len(token_scores)
    else:
        token = 0.0

    if q in c:
        substring = 1.0
    elif any(token in c for token in q_tokens if len(token) >= 2):
        substring = 0.85
    else:
        substring = 0.0

    return max(sequence, token, substring)


def _default_label(item: T, index: int) -> str:
    return str(item)


def find_fuzzy_matches(
    query: str,
    candidates: List[T],
    threshold: Optional[float] = None,
    label_fn: Optional[Callable[[T, int], str]] = None,
) -> List[FuzzyMatch[T]]:
    """Return candidates scoring at or above threshold, sorted best-first."""
    threshold = active_threshold(threshold)
    label_fn = label_fn or _default_label
    matches: List[FuzzyMatch[T]] = []

    for index, item in enumerate(candidates):
        label = label_fn(item, index)
        score = match_score(query, label)
        if score >= threshold:
            matches.append(FuzzyMatch(item=item, index=index, score=score, label=label))

    matches.sort(key=lambda match: (-match.score, match.index))
    return matches


def resolve_fuzzy_match(
    query: str,
    candidates: List[T],
    threshold: Optional[float] = None,
    ambiguity_gap: float = AMBIGUITY_GAP,
    label_fn: Optional[Callable[[T, int], str]] = None,
) -> Tuple[Optional[FuzzyMatch[T]], Optional[str]]:
    """Resolve a single match, supporting numeric indices, ambiguity checks, and suggestions."""
    threshold = active_threshold(threshold)
    if not candidates:
        return None, "No candidates available."

    label_fn = label_fn or _default_label
    stripped = query.strip()

    if stripped.isdigit():
        index = int(stripped)
        if 0 <= index < len(candidates):
            label = label_fn(candidates[index], index)
            return FuzzyMatch(item=candidates[index], index=index, score=1.0, label=label), None
        return None, f"No candidate at index {index}. Valid indices: 0-{len(candidates) - 1}."

    matches = find_fuzzy_matches(query, candidates, threshold, label_fn)
    if not matches:
        near_misses = find_fuzzy_matches(query, candidates, threshold=0.0, label_fn=label_fn)[:3]
        if near_misses:
            suggestions = ", ".join(f"'{match.label}' ({match.score:.0%})" for match in near_misses)
            return None, f"No match for '{query}'. Did you mean: {suggestions}?"
        return None, f"No match for '{query}'."

    if len(matches) >= 2 and matches[0].score - matches[1].score < ambiguity_gap:
        options = ", ".join(f"'{match.label}'" for match in matches[:3])
        return None, f"Ambiguous match for '{query}'. Multiple options: {options}."

    return matches[0], None
