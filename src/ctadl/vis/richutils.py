# Extracted and modified from https://github.com/tiangolo/typer
# Extracted and modified from https://github.com/ewels/rich-click

import contextlib
import sys
import textwrap
from functools import singledispatchmethod, wraps
from os import getenv
from typing import Optional, Protocol, Union

from rich import box, print
from rich.align import Align
from rich.columns import Columns
from rich.console import Console, Group, NewLine, RenderableType, group
from rich.emoji import Emoji
from rich.highlighter import RegexHighlighter
from rich.markdown import Markdown
from rich.padding import Padding
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.style import Style
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich.tree import Tree

from ctadl.vis.types import *

if sys.version_info >= (3, 8):
    from typing import Literal
else:
    from typing_extensions import Literal

from . import model

# Default styles
STYLE_VAR = "yellow"
STYLE_FIELD = "blue"
STYLE_TAINT_LABEL = "red"
STYLE_INT_ID = "light_slate_blue"

_TERMINAL_WIDTH = getenv("TERMINAL_WIDTH")
MAX_WIDTH = int(_TERMINAL_WIDTH) if _TERMINAL_WIDTH else None
COLOR_SYSTEM: Optional[
    Literal["auto", "standard", "256", "truecolor", "windows"]
] = "truecolor"  # Set to None to disable colors
FORCE_TERMINAL = (
    True
    if getenv("GITHUB_ACTIONS") or getenv("FORCE_COLOR") or getenv("PY_COLORS")
    else None
)


def _get_rich_console(stderr: bool = False) -> Console:
    return Console(
        theme=Theme(
            {
                "taint_label": STYLE_TAINT_LABEL,
                "var": STYLE_VAR,
                "field": STYLE_FIELD,
                "leak_graph_id": STYLE_INT_ID,
            },
        ),
        highlight=True,
        color_system=COLOR_SYSTEM,
        force_terminal=FORCE_TERMINAL,
        width=MAX_WIDTH,
        stderr=stderr,
    )
