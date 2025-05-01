import networkx as nx
import importlib.metadata
import importlib.resources as resources
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
export_formats: list[str] = ["gml"]


def run(ctadl, args, format: str, index: Path, out: str, **kwargs) -> int:
    import ctadl.vis.model as model
    from ctadl.util.functions import writer

    ctadl.status(f"ctadl_networkx_export_plugin {version}")
    logger.debug("format is '%s'", format)
    logger.debug("index is '%s'", index)
    logger.debug("out is '%s'", out)

    g = nx.DiGraph()
    counter = 0
    ids = dict()

    def get_id(t):
        nonlocal counter
        if t not in ids:
            id = counter
            ids[t] = id
            counter += 1
        return ids[t]

    with model.DB(index) as con:
        cur = model.execute(
            con,
            """
            SELECT * from CVar_Type
            """,
        )
        for row in cur:
            u = get_id((row["var"], row["path"]))
            g.add_node(u, variable=row["var"], access=row["path"], type=row["type"])
        cur = model.execute(
            con,
            """
            SELECT * FROM VirtualAssign
            """,
        )
        for row in cur:
            u = get_id((row["v2"], row["p2"]))
            v = get_id((row["v1"], row["p1"]))
            g.add_edge(u, v, ctx=row["ctx"])
    if format == "gml":
        nx.write_gml(g, out)
        return 0
    return 1
