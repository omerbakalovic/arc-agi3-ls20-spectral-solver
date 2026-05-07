from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import median
from typing import Dict, Iterable, Optional, Sequence, Tuple

from .perception import FrameDelta

GridPos = Tuple[int, int]
Vector = Tuple[int, int]
Point = Tuple[float, float]


@dataclass(frozen=True)
class MovementOutcome:
    action_id: int
    moved: bool
    blocked: bool
    current_pos: GridPos
    next_pos: GridPos
    vector: Optional[Vector]
    pixel_delta: Optional[Point]
    actor_before: Optional[Point]
    actor_after: Optional[Point]
    confidence: float
    reason: str


class MovementModel:
    """Infer actor movement and collisions from frame deltas."""

    def __init__(
        self,
        *,
        min_motion_px: float = 2.0,
        max_motion_px: float = 12.0,
        broad_change_limit: int = 260,
    ) -> None:
        self.min_motion_px = min_motion_px
        self.max_motion_px = max_motion_px
        self.broad_change_limit = broad_change_limit
        self.action_vectors: Dict[int, Vector] = {}
        self.action_pixel_deltas: Dict[int, Point] = {}
        self.pixel_step_estimate: Optional[float] = None
        self.actor_center: Optional[Point] = None
        self._motion_magnitudes: list[float] = []

    def classify(
        self,
        action_id: int,
        delta: FrameDelta,
        current_pos: GridPos,
    ) -> MovementOutcome:
        actor_before = delta.erased_centroid
        actor_after = delta.added_centroid
        pixel_delta = delta.motion_delta

        if delta.changed_count == 0:
            return self._blocked(action_id, current_pos, "no_frame_delta")

        if delta.changed_count > self.broad_change_limit or delta.impact == "broad":
            return MovementOutcome(
                action_id=action_id,
                moved=False,
                blocked=False,
                current_pos=current_pos,
                next_pos=current_pos,
                vector=None,
                pixel_delta=pixel_delta,
                actor_before=actor_before,
                actor_after=actor_after,
                confidence=0.15,
                reason=f"broad_change({delta.changed_count})",
            )

        if pixel_delta is None:
            centroid_outcome = self._classify_from_delta_centroid(action_id, delta, current_pos)
            if centroid_outcome is not None:
                return centroid_outcome
            if action_id in self.action_vectors and delta.changed_count <= 3:
                return self._blocked(action_id, current_pos, "tiny_without_motion")
            return MovementOutcome(
                action_id=action_id,
                moved=False,
                blocked=False,
                current_pos=current_pos,
                next_pos=current_pos,
                vector=None,
                pixel_delta=None,
                actor_before=actor_before,
                actor_after=actor_after,
                confidence=0.2,
                reason="no_added_erased_pair",
            )

        magnitude = math.hypot(pixel_delta[0], pixel_delta[1])
        if magnitude < self.min_motion_px:
            return self._blocked(action_id, current_pos, f"motion_too_small({magnitude:.2f})")
        if magnitude > self.max_motion_px:
            return MovementOutcome(
                action_id=action_id,
                moved=False,
                blocked=False,
                current_pos=current_pos,
                next_pos=current_pos,
                vector=None,
                pixel_delta=pixel_delta,
                actor_before=actor_before,
                actor_after=actor_after,
                confidence=0.25,
                reason=f"motion_too_large({magnitude:.2f})",
            )

        vector = self._normalize_vector(pixel_delta)
        known = self.action_vectors.get(action_id)
        if known is not None and known != vector:
            confidence = 0.45
            reason = f"movement_vector_changed({known}->{vector})"
        else:
            confidence = 0.8
            reason = "movement"

        self.action_vectors[action_id] = vector
        self.action_pixel_deltas[action_id] = pixel_delta
        self._motion_magnitudes.append(magnitude)
        self.pixel_step_estimate = float(median(self._motion_magnitudes))
        if actor_after is not None:
            self.actor_center = actor_after

        next_pos = (current_pos[0] + vector[0], current_pos[1] + vector[1])
        return MovementOutcome(
            action_id=action_id,
            moved=True,
            blocked=False,
            current_pos=current_pos,
            next_pos=next_pos,
            vector=vector,
            pixel_delta=pixel_delta,
            actor_before=actor_before,
            actor_after=actor_after,
            confidence=confidence,
            reason=reason,
        )

    def seed_from_outcomes(self, outcomes: Iterable[MovementOutcome]) -> None:
        for outcome in outcomes:
            if outcome.moved and outcome.vector is not None:
                self.action_vectors[outcome.action_id] = outcome.vector
                if outcome.pixel_delta is not None:
                    self.action_pixel_deltas[outcome.action_id] = outcome.pixel_delta
                    self._motion_magnitudes.append(math.hypot(*outcome.pixel_delta))
                if outcome.actor_after is not None:
                    self.actor_center = outcome.actor_after
        if self._motion_magnitudes:
            self.pixel_step_estimate = float(median(self._motion_magnitudes))

    def fit_action_from_centroid_sequence(
        self,
        action_id: int,
        deltas: Sequence[FrameDelta],
    ) -> Optional[MovementOutcome]:
        centers = [
            delta.centroid
            for delta in deltas
            if delta.centroid is not None and delta.changed_count > 0 and delta.impact in {"local", "distributed"}
        ]
        shifts: list[Point] = []
        for before, after in zip(centers, centers[1:]):
            dy = after[0] - before[0]
            dx = after[1] - before[1]
            magnitude = math.hypot(dy, dx)
            if self.min_motion_px <= magnitude <= self.max_motion_px:
                shifts.append((dy, dx))
        if not shifts:
            return None

        dy = float(median([s[0] for s in shifts]))
        dx = float(median([s[1] for s in shifts]))
        vector = self._normalize_vector((dy, dx))
        self.action_vectors[action_id] = vector
        self.action_pixel_deltas[action_id] = (dy, dx)
        self._motion_magnitudes.append(math.hypot(dy, dx))
        self.pixel_step_estimate = float(median(self._motion_magnitudes))
        if centers:
            self.actor_center = centers[-1]
        return MovementOutcome(
            action_id=action_id,
            moved=True,
            blocked=False,
            current_pos=(0, 0),
            next_pos=vector,
            vector=vector,
            pixel_delta=(dy, dx),
            actor_before=centers[0],
            actor_after=centers[-1],
            confidence=0.75,
            reason="centroid_sequence_fit",
        )

    def set_reversal(self, action_id: int, source_action_id: int) -> Optional[MovementOutcome]:
        source_vector = self.action_vectors.get(source_action_id)
        source_delta = self.action_pixel_deltas.get(source_action_id)
        if source_vector is None:
            return None
        vector = (-source_vector[0], -source_vector[1])
        self.action_vectors[action_id] = vector
        pixel_delta = None
        if source_delta is not None:
            pixel_delta = (-source_delta[0], -source_delta[1])
            self.action_pixel_deltas[action_id] = pixel_delta
        return MovementOutcome(
            action_id=action_id,
            moved=True,
            blocked=False,
            current_pos=(0, 0),
            next_pos=vector,
            vector=vector,
            pixel_delta=pixel_delta,
            actor_before=None,
            actor_after=None,
            confidence=0.7,
            reason=f"hash_reversal_of_action_{source_action_id}",
        )

    def target_grid_estimate(self, current_pos: GridPos, target_center: Point) -> Optional[GridPos]:
        if self.actor_center is None or not self.pixel_step_estimate:
            return None
        dy = int(round((target_center[0] - self.actor_center[0]) / self.pixel_step_estimate))
        dx = int(round((target_center[1] - self.actor_center[1]) / self.pixel_step_estimate))
        return (current_pos[0] + dy, current_pos[1] + dx)

    def opposite_action(self, action_id: int) -> Optional[int]:
        vector = self.action_vectors.get(action_id)
        if vector is None:
            return None
        opposite = (-vector[0], -vector[1])
        for candidate_action_id, candidate_vector in self.action_vectors.items():
            if candidate_action_id != action_id and candidate_vector == opposite:
                return candidate_action_id
        return None

    def _normalize_vector(self, pixel_delta: Point) -> Vector:
        dy, dx = pixel_delta
        if abs(dy) >= abs(dx):
            return (1 if dy > 0 else -1, 0)
        return (0, 1 if dx > 0 else -1)

    def _classify_from_delta_centroid(
        self,
        action_id: int,
        delta: FrameDelta,
        current_pos: GridPos,
    ) -> Optional[MovementOutcome]:
        if delta.centroid is None or delta.changed_count == 0:
            return None
        known_vector = self.action_vectors.get(action_id)
        center_delta: Optional[Point] = None
        magnitude = 0.0
        if self.actor_center is not None:
            center_delta = (
                delta.centroid[0] - self.actor_center[0],
                delta.centroid[1] - self.actor_center[1],
            )
            magnitude = math.hypot(center_delta[0], center_delta[1])

        if known_vector is not None and delta.impact in {"local", "distributed"}:
            self.actor_center = delta.centroid
            next_pos = (current_pos[0] + known_vector[0], current_pos[1] + known_vector[1])
            pixel_delta = self.action_pixel_deltas.get(action_id) or center_delta
            return MovementOutcome(
                action_id=action_id,
                moved=True,
                blocked=False,
                current_pos=current_pos,
                next_pos=next_pos,
                vector=known_vector,
                pixel_delta=pixel_delta,
                actor_before=None,
                actor_after=delta.centroid,
                confidence=0.62,
                reason="known_vector_local_delta",
            )

        if center_delta is None:
            self.actor_center = delta.centroid
            return MovementOutcome(
                action_id=action_id,
                moved=False,
                blocked=False,
                current_pos=current_pos,
                next_pos=current_pos,
                vector=None,
                pixel_delta=None,
                actor_before=None,
                actor_after=delta.centroid,
                confidence=0.35,
                reason="init_actor_from_delta_centroid",
            )

        if self.min_motion_px <= magnitude <= self.max_motion_px:
            vector = self._normalize_vector(center_delta)
            self.action_vectors[action_id] = vector
            self.action_pixel_deltas[action_id] = center_delta
            self._motion_magnitudes.append(magnitude)
            self.pixel_step_estimate = float(median(self._motion_magnitudes))
            self.actor_center = delta.centroid
            next_pos = (current_pos[0] + vector[0], current_pos[1] + vector[1])
            return MovementOutcome(
                action_id=action_id,
                moved=True,
                blocked=False,
                current_pos=current_pos,
                next_pos=next_pos,
                vector=vector,
                pixel_delta=center_delta,
                actor_before=None,
                actor_after=delta.centroid,
                confidence=0.58,
                reason="delta_centroid_shift",
            )

        if delta.impact in {"local", "distributed"} and magnitude > self.max_motion_px:
            self.actor_center = delta.centroid
            return MovementOutcome(
                action_id=action_id,
                moved=False,
                blocked=False,
                current_pos=current_pos,
                next_pos=current_pos,
                vector=None,
                pixel_delta=center_delta,
                actor_before=None,
                actor_after=delta.centroid,
                confidence=0.25,
                reason=f"delta_centroid_jump({magnitude:.2f})",
            )

        return None

    def _blocked(self, action_id: int, current_pos: GridPos, reason: str) -> MovementOutcome:
        return MovementOutcome(
            action_id=action_id,
            moved=False,
            blocked=True,
            current_pos=current_pos,
            next_pos=current_pos,
            vector=self.action_vectors.get(action_id),
            pixel_delta=None,
            actor_before=None,
            actor_after=self.actor_center,
            confidence=0.65 if action_id in self.action_vectors else 0.35,
            reason=reason,
        )
