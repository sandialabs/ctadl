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
language = "PCODE"


def run(ctadl, args, artifact: str, out: str, **kwargs):
    ctadl.status(f"ctadl_ghidra_fact_generator_plugin {version}")
    logger.debug("artifact: %s", artifact)
    logger.debug("out: %s", out)

    pcode_files = resources.files(ctadl) / "souffle-logic/pcode"
    ctadl.status(f"exporting program with Ghidra to '{out}'")
    factsdir = str(Path(out) / "facts")
    os.makedirs(factsdir, exist_ok=True)
    with contextlib.ExitStack() as ctx:
        analyzer = str(
            ctx.enter_context(
                resources.as_file(pcode_files / "analyzeHeadlessBigMem")
            ).resolve()
        )
        command = [analyzer]
        project_path = args.tmpdir + "/ghidra_headless"
        os.makedirs(project_path)
        project = "headless"
        opts = [
            [project_path],
            [project],
            ["-import", artifact, "-deleteProject"],
            ["-postScript", "ExportPCodeForCTADL.java", factsdir],
            [
                "-scriptPath",
                str(ctx.enter_context(resources.as_file(pcode_files)).resolve()),
            ],
        ]
        for opt_list in opts:
            command.extend(opt_list)
        command.extend(kwargs.get("argument_passthrough", []))
        logger.debug("analyzeHeadless command: %s", " ".join(command))
        return subprocess.run(command)
