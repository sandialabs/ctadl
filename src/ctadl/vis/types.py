import logging
from enum import Enum
from typing import Literal, NamedTuple

from ctadl.util import OrderedSet

logger = logging.getLogger(__name__)


class VertexTy(NamedTuple):
    var: str
    path: str  # Access path


VertexId = int
InsnIdStr = str
VarIdStr = str
FuncIdStr = str
LabelSet = OrderedSet
InsnKind = Literal["move", "actual-to-formal", "formal-to-actual"]


class IllegalStackStateTransition(Exception):
    def __init__(self, reason):
        self.reason = reason

    def __str__(self):
        return "IllegalStackStateTransition: " + self.reason


class CtadlModelError(Exception):
    def __init__(self, reason):
        self.reason = reason

    def __str__(self):
        return "CtadlModelError: " + self.reason


class StackState(Enum):
    """State of the stack in the taint traversal"""

    free = 1
    restricted = 2

    def do_call(self):
        if self == StackState.free:
            return StackState.restricted
        elif self == StackState.restricted:
            return StackState.restricted

    def do_return(self):
        if self == StackState.free:
            return StackState.free
        elif self == StackState.restricted:
            raise IllegalStackStateTransition("return in restricted state")


class SliceDirection(Enum):
    forward = "f"
    backward = "b"

    def is_forward(self):
        return self is SliceDirection.forward

    @staticmethod
    def from_str(s: str) -> "SliceDirection":
        if s not in ["forward", "backward", "fwd", "bwd", "f", "b"]:
            raise ValueError(f"SliceDirection from invalid string: '{s}'")
        if s.startswith("f"):
            return SliceDirection.forward
        if s.startswith("b"):
            return SliceDirection.backward
        raise ValueError("Should be impossible")
