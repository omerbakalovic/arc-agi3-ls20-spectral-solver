from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

GridPos = Tuple[int, int]


@dataclass
class PartialGraph:
    visited: Set[GridPos] = field(default_factory=lambda: {(0, 0)})
    edges: Dict[Tuple[GridPos, int], GridPos] = field(default_factory=dict)
    walls: Set[Tuple[GridPos, int]] = field(default_factory=set)
    forbidden: Set[Tuple[GridPos, int]] = field(default_factory=set)
    attempts: Dict[Tuple[GridPos, int], int] = field(default_factory=dict)

    def record_attempt(self, pos: GridPos, action_id: int) -> None:
        key = (pos, action_id)
        self.attempts[key] = self.attempts.get(key, 0) + 1

    def record_move(self, pos: GridPos, action_id: int, next_pos: GridPos) -> None:
        self.record_attempt(pos, action_id)
        if (pos, action_id) in self.forbidden:
            return
        self.edges[(pos, action_id)] = next_pos
        self.visited.add(pos)
        self.visited.add(next_pos)

    def record_inferred_move(self, pos: GridPos, action_id: int, next_pos: GridPos) -> None:
        if (pos, action_id) in self.forbidden:
            return
        if (pos, action_id) not in self.walls:
            self.edges.setdefault((pos, action_id), next_pos)
        self.visited.add(pos)
        self.visited.add(next_pos)

    def record_wall(self, pos: GridPos, action_id: int) -> None:
        self.record_attempt(pos, action_id)
        if (pos, action_id) in self.forbidden:
            return
        self.walls.add((pos, action_id))
        self.visited.add(pos)

    def record_forbidden(self, pos: GridPos, action_id: int) -> None:
        key = (pos, action_id)
        self.forbidden.add(key)
        self.edges.pop(key, None)
        self.walls.add(key)
        self.visited.add(pos)

    def load_forbidden(self, edges: Iterable[Tuple[GridPos, int]]) -> None:
        for pos, action_id in edges:
            self.record_forbidden(pos, action_id)

    def record_ambiguous(self, pos: GridPos, action_id: int) -> None:
        self.record_attempt(pos, action_id)
        self.visited.add(pos)

    def tried(self, pos: GridPos, action_id: int) -> bool:
        return (pos, action_id) in self.attempts

    def candidate_actions(self, pos: GridPos, action_ids: Iterable[int], retry_limit: int = 1) -> List[int]:
        candidates: List[int] = []
        for action_id in action_ids:
            if (pos, action_id) in self.forbidden:
                continue
            if (pos, action_id) in self.walls or (pos, action_id) in self.edges:
                continue
            if self.attempts.get((pos, action_id), 0) < retry_limit:
                candidates.append(action_id)
        return candidates

    def untried_actions(self, pos: GridPos, action_ids: Iterable[int]) -> List[int]:
        return self.candidate_actions(pos, action_ids, retry_limit=1)

    def neighbors(self, pos: GridPos) -> List[Tuple[GridPos, int]]:
        return [
            (next_pos, action_id)
            for (edge_pos, action_id), next_pos in self.edges.items()
            if edge_pos == pos and (edge_pos, action_id) not in self.forbidden
        ]

    def stats(self) -> Dict[str, int]:
        return {
            "visited": len(self.visited),
            "edges": len(self.edges),
            "walls": len(self.walls),
            "forbidden": len(self.forbidden),
            "attempts": len(self.attempts),
        }


class BFSPlanner:
    """BFS over the learned graph, with frontier exploration when no target is known."""

    def __init__(self, action_ids: Iterable[int], ambiguous_retry_limit: int = 3) -> None:
        self.action_ids = list(action_ids)
        self.ambiguous_retry_limit = ambiguous_retry_limit
        self.pending_path: deque[int] = deque()
        self.target_positions: Set[GridPos] = set()

    def set_action_ids(self, action_ids: Iterable[int]) -> None:
        self.action_ids = list(action_ids)

    def set_targets(self, targets: Iterable[GridPos]) -> None:
        self.target_positions = set(targets)

    def next_action(self, graph: PartialGraph, current_pos: GridPos) -> Tuple[Optional[int], str]:
        if self.pending_path:
            return self.pending_path.popleft(), "follow_pending_bfs_path"

        for action_id in graph.candidate_actions(current_pos, self.action_ids, self.ambiguous_retry_limit):
            return action_id, "probe_untried_local_action"

        target_path = self._path_to_any_target(graph, current_pos)
        if target_path:
            self.pending_path = deque(target_path[1:])
            return target_path[0], "bfs_to_visible_target"

        frontier_path = self._path_to_nearest_frontier(graph, current_pos)
        if frontier_path:
            self.pending_path = deque(frontier_path[1:])
            return frontier_path[0], "bfs_to_frontier"

        return None, "no_frontier_left"

    def _path_to_any_target(self, graph: PartialGraph, start: GridPos) -> Optional[List[int]]:
        if not self.target_positions:
            return None
        queue: deque[Tuple[GridPos, List[int]]] = deque([(start, [])])
        seen = {start}
        while queue:
            pos, path = queue.popleft()
            if pos in self.target_positions and path:
                return path
            for next_pos, action_id in graph.neighbors(pos):
                if next_pos in seen:
                    continue
                seen.add(next_pos)
                queue.append((next_pos, path + [action_id]))
        return None

    def _path_to_nearest_frontier(self, graph: PartialGraph, start: GridPos) -> Optional[List[int]]:
        queue: deque[Tuple[GridPos, List[int]]] = deque([(start, [])])
        seen = {start}
        while queue:
            pos, path = queue.popleft()
            if path and graph.candidate_actions(pos, self.action_ids, self.ambiguous_retry_limit):
                return path
            for next_pos, action_id in graph.neighbors(pos):
                if next_pos in seen:
                    continue
                seen.add(next_pos)
                queue.append((next_pos, path + [action_id]))
        return None
