from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

GridPos = Tuple[int, int]


@dataclass(frozen=True)
class HazardEdge:
    level_index: int
    pos: GridPos
    action_id: int
    state: str
    step: int


class HazardModel:
    """Terminal-edge memory learned from failed black-box attempts."""

    def __init__(self) -> None:
        self.terminal_edges: List[HazardEdge] = []

    def record_terminal_edge(
        self,
        *,
        level_index: int,
        pos: GridPos,
        action_id: int,
        state: str,
        step: int,
    ) -> HazardEdge:
        edge = HazardEdge(
            level_index=int(level_index),
            pos=pos,
            action_id=int(action_id),
            state=str(state),
            step=int(step),
        )
        if edge not in self.terminal_edges:
            self.terminal_edges.append(edge)
        return edge

    def forbidden_edges(self, level_index: int) -> Set[Tuple[GridPos, int]]:
        return {
            (edge.pos, edge.action_id)
            for edge in self.terminal_edges
            if edge.level_index == int(level_index)
        }

    def stats(self) -> Dict[str, int]:
        by_level: Dict[int, int] = {}
        for edge in self.terminal_edges:
            by_level[edge.level_index] = by_level.get(edge.level_index, 0) + 1
        return {
            "terminal_edges": len(self.terminal_edges),
            **{f"level_{level}_terminal_edges": count for level, count in sorted(by_level.items())},
        }

    def to_dict(self) -> Dict[str, object]:
        return {
            "terminal_edges": [
                {
                    "level_index": edge.level_index,
                    "pos": edge.pos,
                    "action_id": edge.action_id,
                    "state": edge.state,
                    "step": edge.step,
                }
                for edge in self.terminal_edges
            ],
            "stats": self.stats(),
        }
