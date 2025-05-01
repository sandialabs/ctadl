import contextlib
import importlib.metadata
import importlib.resources as resources
import subprocess
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def read_version():
    filepath = str(resources.files(__name__) / "VERSION")
    with open(filepath) as file:
        for line in file:
            line = line.strip()
            return line.strip(' "')
    return "unknown-dev"


version = read_version()
language = "TAINT-FRONT"


def run(ctadl, args, artifact: str, out: str, **kwargs):
    ctadl.status(f"ctadl_taint_front_fact_generator_plugin {version}")
    logger.debug("artifact: %s", artifact)
    logger.debug("out: %s", out)
    ctadl.status(f"exporting program with taintfront to '{out}'")

    command = ["taintfront"]
    opts = [["-o", out], [artifact]]
    for opt_list in opts:
        command.extend(opt_list)
    command.extend(kwargs.get("argument_passthrough", []))
    logger.debug("taintfront command: %s", " ".join(command))
    return subprocess.run(command)
