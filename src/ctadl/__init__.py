import contextlib
import csv
import importlib.metadata
import importlib.resources as resources
import io
import logging
import os
import shutil
import sys
import typing
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def read_version():
    filepath = str(resources.files(__name__) / "VERSION")
    with open(filepath) as file:
        for line in file:
            line = line.strip()
            return line.strip(' "')
    return "unknown-dev"


__version__ = read_version()

quiet = False

# Log levels from logger are messages intended for debugging and development.
# Verbosity levels are intended for users and go up to -vvv.
verbosity = 0


configdir = (
    Path(
        os.environ.get("APPDATA")
        or os.environ.get("XDG_CONFIG_HOME")
        or (Path(os.environ["HOME"]) / ".config")
    )
    / f"ctadl"
)

datadir = (
    Path(
        os.environ.get("APPDATA")
        or os.environ.get("XDG_DATA_HOME")
        or (Path(os.environ["HOME"]) / ".local" / "share")
    )
    / f"ctadl"
)

statedir = (
    Path(
        os.environ.get("APPDATA")
        or os.environ.get("XDG_STATE_HOME")
        or (Path(os.environ["HOME"]) / ".local" / "state")
    )
    / f"ctadl"
)

analysisdir = datadir / "analysis" / __version__


def is_verbosity_enabled_for(verb: int):
    """Returns true if messages are enabled for given verbosity level"""
    global quiet, verbosity
    return not quiet and verb <= verbosity


def status(msg: str, prefix: str = "", verb=0, **kwargs) -> int:
    """Outputs a ctadl status message. Returns number of characters printed.

    Arguments:
    - verb: Sets verbosity level"""
    if is_verbosity_enabled_for(verb):
        # First, we'll format everything to a string so we know exactly how
        # many characters are printed.
        output = io.StringIO()
        kwargs.update(dict(file=output))
        print(f"{prefix}{msg}", **kwargs)

        # Outputs that string as is
        contents = output.getvalue()
        n = len(contents)
        sys.stderr.write(contents)
        return n
    return 0


def advise(msg):
    global quiet
    if not quiet:
        print(">> hint:", msg, file=sys.stderr)


def warn(msg):
    global quiet
    if not quiet:
        print("^^ warning:", msg, file=sys.stderr)


def error(msg, *, remediations: typing.Union[str, list[str]] = ""):
    """Prints an error message and possible remediations"""
    print("**", msg, file=sys.stderr)
    if remediations:
        if isinstance(remediations, str):
            print("   >", remediations, file=sys.stderr)
        else:
            print("   possible solutions:", file=sys.stderr)
            for r in remediations:
                print("   >", r, file=sys.stderr)


def banner():
    global quiet
    if not quiet:
        print(f"CTADL {__version__}", file=sys.stderr)


def status_isatty():
    return sys.stderr.isatty()


class SouffleDialect(csv.Dialect):
    delimiter = "\t"
    quotechar = '"'
    escapechar = None


def modified_after(ref=None, test=None):
    if ref is None:
        raise RuntimeError("ref not given")
    if test is None:
        raise RuntimeError("test not given")
    tref = Path(ref).stat()
    ttest = Path(test).stat()
    return tref.st_mtime > ttest.st_mtime


def ensure_dir_exists(path: str, clear=False):
    if clear and os.path.exists(path):
        logging.debug("deleting %s", path)
        shutil.rmtree(path)
    if not os.path.exists(path):
        logging.debug("creating %s", path)
        os.makedirs(path)


def check_env_exists(var):
    print(os.environ.get(var, ""))


# https://stackoverflow.com/questions/3173320/text-progress-bar-in-terminal-with-block-characters
# Print iterations progress
def print_progress_bar(
    iteration,
    total,
    prefix="",
    suffix="",
    decimals=1,
    length=100,
    fill="█",
    printEnd="\r",
    file=sys.stderr,
):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)

        import time

        # A List of Items
        items = list(range(0, 57))
        l = len(items)

        # Initial call to print 0% progress
        printProgressBar(0, l, prefix = 'Progress:', suffix = 'Complete', length = 50)
        for i, item in enumerate(items):
            # Do stuff...
            time.sleep(0.1)
            # Update Progress Bar
            printProgressBar(i + 1, l, prefix = 'Progress:', suffix = 'Complete', length
    """
    if total < 0:
        return
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + "-" * (length - filledLength)
    print(f"\r{prefix} |{bar}| {percent}% {suffix}", end=printEnd, file=file)
    # Print New Line on Complete
    if iteration == total:
        print(file=file)


def progress_bar(
    iterable,
    description="",
    total=-1,
    prefix="",
    suffix="",
    decimals=0,
    length=-1,
    fill="█",
    printEnd="\r",
    file=sys.stderr,
):
    """
    Call in a loop to create terminal progress bar
    @params:
        iterable    - Required  : iterable object (Iterable)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)

        import time

        # A List of Items
        items = list(range(0, 57))

        # A Nicer, Single-Call Usage
        for item in progress_bar(items, prefix = 'Progress:', suffix = 'Complete', length = 50):
            # Do stuff...
            time.sleep(0.1)
    """
    if length < 0:
        displaycols, displayrows = shutil.get_terminal_size()
        if displaycols > 0:
            length = displaycols - len(prefix)
        else:
            length = 100
    print("hi my length is", length, file=sys.stderr)
    total = len(iterable)
    if total == 0:
        return

    # Progress Bar Printing Function
    def printProgressBar(iteration):
        percent = ("{0:." + str(decimals) + "f}").format(
            100 * (iteration / float(total))
        )
        filledLength = int(length * iteration // total)
        bar = fill * filledLength + "-" * (length - filledLength)
        print(f"\r{prefix} |{bar}| {percent}% {suffix}", end=printEnd, file=file)

    if os.isatty(file.fileno()):
        # Initial Call
        printProgressBar(0)
    # Update Progress Bar
    for i, item in enumerate(iterable):
        yield item
        if os.isatty(file.fileno()):
            printProgressBar(i + 1)
    if os.isatty(file.fileno()):
        # Print New Line on Complete
        print(file=file)


class ProgressBar(contextlib.AbstractContextManager):
    def __init__(*args, **kwargs):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        pass

    def add_task(self, description, **kwargs):
        return None

    def update(self, task, **kwargs):
        pass


def _empty_progressbar(*args, **kwargs):
    return ProgressBar(*args, **kwargs)


def _rich_progressbar(**kwargs):
    from rich.console import Console
    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    return Progress(
        TextColumn("{task.description}"),
        TextColumn("[green]{task.percentage:>3.1f}%"),
        MofNCompleteColumn(),
        BarColumn(bar_width=None, style="dark_violet"),
        "Elapsed:",
        TimeElapsedColumn(),
        "Remaining:",
        TimeRemainingColumn(),
        console=Console(file=sys.stderr),
    )


try:
    import rich.progress
except ImportError:
    rich = None


def progressbar(fake=False):
    """Creates a progress bar context

    Arguments:
    - fake: Set fake to true if you don't want a progress bar"""
    return (
        _empty_progressbar()
        if fake or rich is None or quiet or not status_isatty()
        else _rich_progressbar()
    )


def track_progress(iterable, **kwargs):
    if rich:
        return rich.progress.track(iterable, **kwargs)
    else:
        return progress_bar(iterable, **kwargs)


class DatalogSource:
    """Represents a datalog source and its corresponding binary of an analysis
    for language"""

    lang: str

    def __init__(
        self, lang, ctx=None, bin: Optional[str] = None, src: Optional[str] = None
    ):
        self.lang = lang
        self._bin = bin
        self._src = src
        if bin is None and src is None:
            assert ctx is not None
            self._bin = str(analysisdir / f"index_{lang}")
            self._src = str(
                resources.files(sys.modules[__name__])
                / "souffle-logic"
                / f"{lang}"
                / "index.dl"
            )

    @property
    def bin(self) -> str:
        assert self._bin is not None
        return self._bin

    @property
    def src(self) -> str:
        assert self._src is not None
        return self._src
