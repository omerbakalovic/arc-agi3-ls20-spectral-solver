from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, "model_dump"):
        return _jsonable(value.model_dump())
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _jsonable(vars(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, set):
        return sorted(_jsonable(v) for v in value)
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


class TraceLogger:
    """Append-only trace logger for black-box runs.

    The JSONL file is the durable source of truth.  Optional frame arrays are
    saved as .npy files so the visual evidence can be replayed without relying
    on environment internals.
    """

    def __init__(self, output_dir: Path | str, save_frames: bool = True) -> None:
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.frames_dir = self.output_dir / "frames"
        self.save_frames = save_frames
        if save_frames:
            self.frames_dir.mkdir(parents=True, exist_ok=True)
        self.jsonl_path = self.output_dir / "trace.jsonl"
        self.text_path = self.output_dir / "trace.txt"
        self.summary_path = self.output_dir / "summary.json"
        self._jsonl = self.jsonl_path.open("w", encoding="utf-8")
        self._text = self.text_path.open("w", encoding="utf-8")
        self._event_index = 0
        self._frame_index = 0
        self.summary: Dict[str, Any] = {}

    def event(self, kind: str, **payload: Any) -> Dict[str, Any]:
        record = {
            "event_index": self._event_index,
            "kind": kind,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        }
        self._event_index += 1
        serializable = _jsonable(record)
        self._jsonl.write(json.dumps(serializable, ensure_ascii=True, sort_keys=True) + "\n")
        self._jsonl.flush()
        self._text.write(self._format_text(serializable) + "\n")
        self._text.flush()
        return serializable

    def frame(self, label: str, frame: np.ndarray, **payload: Any) -> Optional[Path]:
        path: Optional[Path] = None
        if self.save_frames:
            safe_label = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in label)
            path = self.frames_dir / f"{self._frame_index:05d}_{safe_label}.npy"
            np.save(path, np.asarray(frame, dtype=np.int16))
        self.event(
            "frame",
            frame_index=self._frame_index,
            label=label,
            path=path,
            shape=list(np.asarray(frame).shape),
            **payload,
        )
        self._frame_index += 1
        return path

    def set_summary(self, **payload: Any) -> None:
        self.summary.update(payload)
        self.summary_path.write_text(
            json.dumps(_jsonable(self.summary), indent=2, ensure_ascii=True, sort_keys=True),
            encoding="utf-8",
        )

    def close(self) -> None:
        self.set_summary(events=self._event_index, frames=self._frame_index)
        self._jsonl.close()
        self._text.close()

    def _format_text(self, record: Dict[str, Any]) -> str:
        kind = record.get("kind", "event")
        idx = record.get("event_index", "?")
        fields = []
        for key, value in record.items():
            if key in {"event_index", "kind", "timestamp"}:
                continue
            if isinstance(value, (dict, list)):
                value_text = json.dumps(value, ensure_ascii=True, sort_keys=True)
            else:
                value_text = str(value)
            fields.append(f"{key}={value_text}")
        return f"[{idx:04d}] {kind}: " + " ".join(fields)
