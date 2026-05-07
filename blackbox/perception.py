from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha1
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

Point = Tuple[float, float]
BBox = Tuple[int, int, int, int]


@dataclass(frozen=True)
class Component:
    value: int
    size: int
    bbox: BBox
    centroid: Point

    @property
    def area(self) -> int:
        y0, x0, y1, x1 = self.bbox
        return (y1 - y0 + 1) * (x1 - x0 + 1)

    @property
    def compactness(self) -> float:
        return self.size / max(1, self.area)


@dataclass(frozen=True)
class FrameObservation:
    frame_hash: str
    shape: Tuple[int, int]
    background_value: int
    palette_counts: Dict[int, int]
    components: List[Component]

    def rare_components(
        self,
        *,
        min_size: int = 1,
        max_size: int = 256,
        max_count: int = 24,
        exclude_values: Iterable[int] = (),
    ) -> List[Component]:
        excluded = {self.background_value, *set(exclude_values)}
        candidates = [
            c
            for c in self.components
            if c.value not in excluded and min_size <= c.size <= max_size
        ]

        def score(component: Component) -> Tuple[float, float, int]:
            color_count = max(1, self.palette_counts.get(component.value, component.size))
            rarity = 1.0 / color_count
            return (-rarity, -component.compactness, component.size)

        return sorted(candidates, key=score)[:max_count]


@dataclass(frozen=True)
class DiffComponent:
    size: int
    bbox: BBox
    centroid: Point


@dataclass(frozen=True)
class FrameDelta:
    changed_count: int
    bbox: Optional[BBox]
    centroid: Optional[Point]
    components: List[DiffComponent]
    transitions: Dict[str, int]
    added_centroid: Optional[Point]
    erased_centroid: Optional[Point]
    motion_delta: Optional[Point]
    impact: str


class Perception:
    """Frame and delta analysis with no game-source access."""

    def __init__(self, ignore_bottom_rows: int = 4) -> None:
        self.ignore_bottom_rows = ignore_bottom_rows

    def observe(self, frame: np.ndarray) -> FrameObservation:
        arr = self._playfield(frame)
        values, counts = np.unique(arr, return_counts=True)
        palette_counts = {int(v): int(c) for v, c in zip(values, counts)}
        background_value = int(values[int(np.argmax(counts))])
        components: List[Component] = []
        for value in values:
            value_int = int(value)
            if value_int == background_value:
                continue
            for pts in self._connected_points(arr == value_int):
                components.append(self._component_from_points(value_int, pts))
        return FrameObservation(
            frame_hash=self.hash_frame(arr),
            shape=tuple(int(v) for v in arr.shape),
            background_value=background_value,
            palette_counts=palette_counts,
            components=components,
        )

    def diff(self, before: np.ndarray, after: np.ndarray) -> FrameDelta:
        b = self._playfield(before)
        a = self._playfield(after)
        if b.shape != a.shape:
            raise ValueError(f"frame shapes differ: {b.shape} != {a.shape}")

        mask = b != a
        changed_count = int(mask.sum())
        if changed_count == 0:
            return FrameDelta(
                changed_count=0,
                bbox=None,
                centroid=None,
                components=[],
                transitions={},
                added_centroid=None,
                erased_centroid=None,
                motion_delta=None,
                impact="no_change",
            )

        ys, xs = np.nonzero(mask)
        bbox = (int(ys.min()), int(xs.min()), int(ys.max()), int(xs.max()))
        centroid = (float(ys.mean()), float(xs.mean()))
        components = [
            DiffComponent(
                size=len(pts),
                bbox=self._bbox(pts),
                centroid=self._centroid(pts),
            )
            for pts in self._connected_points(mask)
        ]

        pairs = np.stack([b[mask], a[mask]], axis=1)
        transitions: Dict[str, int] = {}
        for old, new in pairs:
            key = f"{int(old)}->{int(new)}"
            transitions[key] = transitions.get(key, 0) + 1

        before_bg = self.observe(before).background_value
        after_bg = self.observe(after).background_value
        added_mask = (b == before_bg) & (a != after_bg)
        erased_mask = (b != before_bg) & (a == after_bg)
        added_centroid = self._mask_centroid(added_mask)
        erased_centroid = self._mask_centroid(erased_mask)
        motion_delta = None
        if added_centroid is not None and erased_centroid is not None:
            motion_delta = (
                added_centroid[0] - erased_centroid[0],
                added_centroid[1] - erased_centroid[1],
            )

        playfield_area = int(mask.size)
        if changed_count <= 2:
            impact = "tiny"
        elif changed_count / max(1, playfield_area) > 0.05:
            impact = "broad"
        elif len(components) <= 4:
            impact = "local"
        else:
            impact = "distributed"

        return FrameDelta(
            changed_count=changed_count,
            bbox=bbox,
            centroid=centroid,
            components=components,
            transitions=transitions,
            added_centroid=added_centroid,
            erased_centroid=erased_centroid,
            motion_delta=motion_delta,
            impact=impact,
        )

    def hash_frame(self, frame: np.ndarray) -> str:
        arr = np.asarray(frame, dtype=np.int16)
        return sha1(arr.tobytes()).hexdigest()[:16]

    def _playfield(self, frame: np.ndarray) -> np.ndarray:
        arr = np.asarray(frame)
        if arr.ndim != 2:
            raise ValueError(f"expected 2D frame, got shape {arr.shape}")
        if self.ignore_bottom_rows <= 0:
            return arr
        cutoff = max(1, arr.shape[0] - self.ignore_bottom_rows)
        return arr[:cutoff, :]

    def _connected_points(self, mask: np.ndarray) -> List[List[Tuple[int, int]]]:
        height, width = mask.shape
        visited = np.zeros_like(mask, dtype=bool)
        components: List[List[Tuple[int, int]]] = []
        for y in range(height):
            for x in range(width):
                if not mask[y, x] or visited[y, x]:
                    continue
                stack = [(y, x)]
                visited[y, x] = True
                pts: List[Tuple[int, int]] = []
                while stack:
                    cy, cx = stack.pop()
                    pts.append((cy, cx))
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if (
                            0 <= ny < height
                            and 0 <= nx < width
                            and mask[ny, nx]
                            and not visited[ny, nx]
                        ):
                            visited[ny, nx] = True
                            stack.append((ny, nx))
                components.append(pts)
        return components

    def _component_from_points(self, value: int, pts: Sequence[Tuple[int, int]]) -> Component:
        return Component(
            value=value,
            size=len(pts),
            bbox=self._bbox(pts),
            centroid=self._centroid(pts),
        )

    def _bbox(self, pts: Sequence[Tuple[int, int]]) -> BBox:
        ys = [p[0] for p in pts]
        xs = [p[1] for p in pts]
        return (min(ys), min(xs), max(ys), max(xs))

    def _centroid(self, pts: Sequence[Tuple[int, int]]) -> Point:
        ys = np.array([p[0] for p in pts], dtype=np.float64)
        xs = np.array([p[1] for p in pts], dtype=np.float64)
        return (float(ys.mean()), float(xs.mean()))

    def _mask_centroid(self, mask: np.ndarray) -> Optional[Point]:
        if not bool(mask.any()):
            return None
        ys, xs = np.nonzero(mask)
        return (float(ys.mean()), float(xs.mean()))
