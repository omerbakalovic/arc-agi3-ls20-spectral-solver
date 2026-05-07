"""Black-box ARC-AGI-3 agent components.

Milestone 1 is intentionally narrow: infer movement and collisions from
frames/deltas, build a partial graph, and log the evidence.  Higher-level
operators live behind stubs until we have enough traces to justify them.
"""

from .agent import BlackBoxAgent
from .hazard import HazardModel
from .movement import MovementModel
from .perception import Perception
from .planner import BFSPlanner, PartialGraph
from .probe import ClickKernelModel, ProbeRunner
from .trace import TraceLogger

__all__ = [
    "BFSPlanner",
    "BlackBoxAgent",
    "ClickKernelModel",
    "HazardModel",
    "MovementModel",
    "PartialGraph",
    "Perception",
    "ProbeRunner",
    "TraceLogger",
]
