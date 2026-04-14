import contextlib
import importlib.metadata
import importlib.resources as resources
import logging
import os
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

MAXMEM = "40G"
LAUNCH_MODE = "fg"
DEBUG_ADDRESS = "127.0.0.1:13002"
VMARG_LIST = "-XX:ParallelGCThreads=4 -XX:CICompilerCount=4 "


def read_version():
    filepath = str(resources.files(__name__) / "VERSION")
    with open(filepath) as file:
        for line in file:
            line = line.strip()
            return line.strip(' "')
    return "unknown-dev"


version = read_version()
language = "PCODE"


def _find_ghidra_base() -> Path:
    ghidra_home = os.environ.get("GHIDRA_HOME")
    if ghidra_home:
        return Path(ghidra_home)

    ghidra_bin = shutil.which("ghidra")
    if ghidra_bin:
        return Path(ghidra_bin).resolve().parent

    raise FileNotFoundError(
        "Could not find ghidra in PATH. Add 'ghidra' to PATH or set GHIDRA_HOME."
    )


def _find_analyze_headless() -> Path:
    ghidra_base = _find_ghidra_base()
    candidates = [
        ghidra_base.parent / "lib" / "ghidra" / "support" / "analyzeHeadless",
        ghidra_base / "support" / "analyzeHeadless",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    raise FileNotFoundError(
        f"Could not find Ghidra analyzeHeadless from ghidra directory {ghidra_base}"
    )


def run(ctadl, args, artifact: str, out: str, **kwargs):
    ctadl.status(f"ctadl_ghidra_fact_generator_plugin {version}")
    logger.debug("artifact: %s", artifact)
    logger.debug("out: %s", out)

    pcode_files = resources.files(ctadl) / "souffle-logic/pcode"
    ctadl.status(f"exporting program with Ghidra to '{out}'")
    factsdir = str(Path(out) / "facts")
    os.makedirs(factsdir, exist_ok=True)
    with contextlib.ExitStack() as ctx:
        analyze_headless = _find_analyze_headless()
        script_dir = analyze_headless.parent
        launch_script = script_dir / "launch.sh"
        logger.debug("analyzeHeadless path: %s", analyze_headless)
        command = [
            str(launch_script),
            LAUNCH_MODE,
            "jdk",
            "Ghidra-Headless",
            MAXMEM,
            VMARG_LIST,
            "ghidra.app.util.headless.AnalyzeHeadless",
        ]
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
        env = os.environ.copy()
        env["DEBUG_ADDRESS"] = DEBUG_ADDRESS
        return subprocess.run(command, env=env)
