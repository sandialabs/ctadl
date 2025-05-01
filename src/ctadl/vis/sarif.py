"""
This module formats SARIF results from CTADL's taint database.
It formats the main data results, not the metadata.
The usage model is:

    run_info = format_run_info(cx)

which returns a dictionary with logicalLocations, addresses, graphs, and
results, which form the bulk of the data in a SARIF run.

This module and the formatters are interdependent. If the SARIF schema changes,
both need to change.

Match queries result in instructions, variables, and functions.

    match_info = format_match_info(cx)
"""

# ---------------------------------------------------------------------------
# Internal design notes

# There should be no dependencies between the format_* functions. They all
# depend on _load_taint_set, but not on each other.

import contextlib
import dataclasses
import logging
import textwrap
from collections import defaultdict
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from pprint import pformat
from sqlite3 import Connection
from typing import Iterable, Iterator, Literal, NamedTuple, Optional, Union

import ctadl
from ctadl.util.functions import CleanDict, Dict, OrderedSet, pairwise
from ctadl.vis.model import (
    ColumnSpec,
    TableSpec,
    TempTable,
    create_indexes,
    execute,
    executemany,
)
from ctadl.vis.taintgraph import TaintGraph, TaintGraphEdgeInput
from ctadl.vis.types import (
    FuncIdStr,
    InsnIdStr,
    InsnKind,
    LabelSet,
    SliceDirection,
    VarIdStr,
    VertexId,
    VertexTy,
)

# ---------------------------------------------------------------------------
# Types

ResultType = Literal[
    "instruction_result",
    "vertex_result",
    "path_result",
    "source_result",
    "sink_result",
    "graphs",
    "source_sink_function_result",
]

# To denote most types of SARIF objects, we just use dictionaries or arrays. We
# could use dataclasses or something more type-safe but most of the fields end
# up being optional, negating type safety; also there is an exhaustive spec and
# we would literally just be reproducing (an incomplete subset of) it...so it
# doesn't seem like we gain much. Instead, we use the names from the SARIF spec
# to indicate where such a thing should be used.

# We do risk mistyping fields with this design; but since we validate our SARIF
# against the spec, those bugs should be easy to find.


class Message(CleanDict):  # 3.11
    def __init__(self, text):
        self["text"] = text


ReportingDescriptor = CleanDict  # 3.49
ArtifactLocation = CleanDict  # 3.4
PhysicalLocation = CleanDict  # 3.29
LogicalLocation = CleanDict  # 3.33
Location = CleanDict  # 3.28
Address = CleanDict  # 3.32
Region = CleanDict  # 3.30
ThreadFlow = CleanDict  # 3.37
CodeFlow = CleanDict  # 3.36
Result = CleanDict  # 3.27
Graph = CleanDict  # 3.39
Node = CleanDict  # 3.40
Edge = CleanDict  # 3.41

# ---------------------------------------------------------------------------
# Globals

rules = [
    ReportingDescriptor(
        id="C0001",
        name="Tainted paths",
        shortDescription=Message("A path of tainted data flow"),
        messageStrings=dict(default=Message("This is a tainted source-sink path.")),
    ),
    ReportingDescriptor(
        id="C0002",
        name="Tainted instructions",
        shortDescription={"text": "An instruction with tainted data"},
        messageStrings={
            "default": {"text": """This instruction manipulates tainted data."""}
        },
    ),
    ReportingDescriptor(
        id="C0003",
        name="Tainted data sources",
        shortDescription={"text": "Tainted data source"},
        messageStrings={"default": {"text": """This is a source of tainted data."""}},
    ),
    ReportingDescriptor(
        id="C0004",
        name="Tainted data sink",
        shortDescription={"text": "Tainted data sinks"},
        messageStrings={
            "default": {"text": """This is an desired sink of tainted data."""}
        },
    ),
    ReportingDescriptor(
        id="C0005",
        name="Tainted data",
        shortDescription={"text": "Tainted variables and fields"},
        messageStrings={"default": {"text": """This vertex is tainted."""}},
    ),
    ReportingDescriptor(
        id="C0006",
        name="Almost-path function",
        shortDescription={
            "text": """A function which contains source-tainted and sink-tainted data, which means there's 'almost' a path between them."""
        },
        messageStrings={
            "default": {"text": "This function contains source and sink taint."}
        },
    ),
]

match_rules = [
    ReportingDescriptor(
        id="M0001",
        name="Instruction match result",
        shortDescription=Message("""Match query matched an instruction."""),
        messageStrings={"default": Message("Match query matched an instruction.")},
    ),
    ReportingDescriptor(
        id="M0002",
        name="Instruction match result",
        shortDescription=Message("""Match query matched an instruction."""),
        messageStrings={"default": Message("Match query matched an instruction.")},
    ),
    ReportingDescriptor(
        id="M0003",
        name="Instruction match result",
        shortDescription=Message("""Match query matched an instruction."""),
        messageStrings={"default": Message("Match query matched an instruction.")},
    ),
]


# ---------------------------------------------------------------------------
# Implementation

logger = logging.getLogger(__name__)


class Context:
    """Stores the database connection and configuration for format_run_info

    The configuration is denoted with ResultType. Each type of result can be
    chosen independently of others.

    - "path_result": C0001. Includes codeFlows members for every tainted path
    - "instruction_result": C0002. Includes results for every tainted
      instruction
    - "source_result": C0003. Includes results for every taint source
    - "sink_result": C0004. Includes results for every taint sink
    - "vertex_result": C0005. Includes results for every tainted vertex
    - "source_sink_function_result": C0006. Includes results for functions
      containing both forward and backward tainted data
    - "graphs": Includes graphs, the literal taint graphs. These are not
      strictly SARIF results. But filtering them is important because in the
      common case they are large and users really want paths (not graphs).

    """

    conn: Connection
    result_types: set[ResultType]
    strategy: str

    # Implementation vars
    _info: "TaintInfo"

    def __init__(self, conn: Connection, results: Iterable[ResultType], strat: str):
        self.conn = conn
        self.result_types = set(results)
        self.strategy = strat

        self.pycx = contextlib.ExitStack()
        self.pycx.__enter__()

        self._info = TaintInfo()


# The following types are used when storing and shuffling around some types of
# results.


class TaintGraphPath(NamedTuple):
    nodes: list[VertexId]
    dir: SliceDirection


class TaintGraphEdge(NamedTuple):
    direction: SliceDirection
    src: VertexId
    dst: VertexId


class TaintGraphEdgeInfo(NamedTuple):
    insn: InsnIdStr
    kind: InsnKind


class FormalParamInfo(NamedTuple):
    func: FuncIdStr
    idx: int


class ActualArgInfo(NamedTuple):
    vertex: VertexTy
    idx: int


class Parameter(NamedTuple):
    idx: int


class ReturnParameter(NamedTuple):
    idx: int


# This class houses all the indexed values we need to access when formatting
# SARIF. It's a laundry list of stuff. Loading it all in batch from the
# database is more efficient than piecemeal
@dataclass
class TaintInfo:
    # Maps a vertex id to a taint label
    id_to_label: dict[VertexId, str] = dataclasses.field(default_factory=dict)
    # Maps ids to vertices
    id_to_vertex: dict[VertexId, VertexTy] = dataclasses.field(default_factory=dict)
    # Maps a vertex to its ids. Note that for this to be safe the forward and
    # backward graph vertex IDs must not overlap. Otherwise taint data between
    # the graphs might get conflated.
    ids_by_vertex: dict[VertexTy, set[VertexId]] = dataclasses.field(
        default_factory=lambda: defaultdict(set)
    )
    # Aggregation of labels across every tainted vertex
    labels_by_vertex: dict[VertexTy, LabelSet] = dataclasses.field(
        default_factory=lambda: defaultdict(LabelSet)
    )
    # Aggregation of labels that cross the instruction
    labels_by_insn: dict[InsnIdStr, LabelSet] = dataclasses.field(
        default_factory=lambda: defaultdict(LabelSet)
    )
    insn_is_dataflow_only: set[InsnIdStr] = dataclasses.field(default_factory=set)
    # All instructions for the given graph edge
    insns_by_edge: dict[TaintGraphEdge, list[TaintGraphEdgeInfo]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    # All src/dst vertices for the instruction
    vertices_by_insn: dict[InsnIdStr, OrderedSet[VertexTy]] = dataclasses.field(
        default_factory=lambda: defaultdict(OrderedSet)
    )
    # All logical locations for each instruction and variable
    logical_locations_by_obj: dict[
        Union[InsnIdStr, VarIdStr], LogicalLocation
    ] = dataclasses.field(default_factory=Dict)
    # Logical locations in final array order for layout in the SARIF. It is
    # safe to index other locations (for example, with a parentIndex) into this
    # array.
    logical_locations_array: list[LogicalLocation] = dataclasses.field(
        default_factory=list
    )
    # Maps object to index into logical_locations_array
    logical_location_index_by_obj: dict[
        Union[InsnIdStr, VarIdStr, FuncIdStr], int
    ] = dataclasses.field(default_factory=Dict)
    # All physical locations for each instruction and variable
    physical_locations_by_obj: dict[
        Union[InsnIdStr, VarIdStr], list[PhysicalLocation]
    ] = dataclasses.field(default_factory=lambda: defaultdict(list))
    # Maps function to its name
    function_to_name: Dict[FuncIdStr, str] = dataclasses.field(default_factory=Dict)
    # Maps variable to an internal name chosen by CTADL
    var_to_name: Dict[VarIdStr, str] = dataclasses.field(default_factory=Dict)
    # Maps variable to a source name, if available
    var_to_source_names: dict[VarIdStr, list[str]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    # Maps variable to func, if available
    var_in_func: Dict[VarIdStr, FuncIdStr] = dataclasses.field(default_factory=Dict)
    # Maps instruction to func
    insn_in_func: Dict[InsnIdStr, FuncIdStr] = dataclasses.field(default_factory=Dict)
    # Maps a namespace to its parent
    parent_namespaces: dict[str, list[str]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    # Maps variable to its formal parameter entry. Curiously, sometimes the
    # same variable is reused for more than one formal parameter. Hence, the
    # range needs to be a list.
    formals_by_var: dict[VarIdStr, list[FormalParamInfo]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    # Maps instruction to its list of actuals, if any
    actuals_by_insn: dict[InsnIdStr, list[ActualArgInfo]] = dataclasses.field(
        default_factory=lambda: defaultdict(list)
    )
    # The graphs loaded from the database
    graphs: list[TaintGraph] = dataclasses.field(default_factory=list)
    # Paths in the taint graph
    paths: list[TaintGraphPath] = dataclasses.field(default_factory=list)
    # Formal parameter index of the return parameter
    return_parameter_index: int = -1


def format_run_info(cx: Context) -> dict:
    """Formats taint analysis results as SARIF using the configuration in the
    context. The configuration filters which results should be included in the
    SARIF file"""

    _load_taint_set(cx)

    info = cx._info
    cur = cx.conn.cursor()

    # Populated with the various SARIF result types we support
    sarif_results: list[Result] = []

    if "path_result" in cx.result_types:
        for path in cx._info.paths:
            nodes = path.nodes
            logger.debug("formatting result for path: %s", path)
            # XXX result.locations??
            start, end = (info.id_to_vertex[nodes[0]], info.id_to_vertex[nodes[-1]])
            start_func, end_func = (
                info.var_in_func.get(start[0], "global"),
                info.var_in_func.get(end[0], "global"),
            )
            start_label = info.id_to_label[nodes[0]]
            result = Result(
                ruleId="C0001",
                kind="review",
                level="warning",
                message=Message(
                    f"Path starts in function '{start_func}' label '{start_label}', ends at '{end_func}'"
                ),
                properties=make_labels_properties([start_label]),
            )
            result |= dict(codeFlows=_format_code_flows(cx, path))
            sarif_results.append(result)

    if "source_result" in cx.result_types:
        # XXX get all taint labels if the message matters that much
        for var, path, label in execute(
            cur, """ SELECT v, p, tag FROM TaintSourceVertex """
        ):
            loc = _format_locations(cx, var)
            field_info = f" in field {path}"
            msg = f"Source labeled '{label}'"
            if path:
                msg += field_info
            result = Result(
                ruleId="C0003",
                kind="informational",
                level="none",
                message=Message(f"{msg}."),
                properties=make_labels_properties([label]),
                locations=[loc],
            )
            sarif_results.append(result)

    if "sink_result" in cx.result_types:
        # XXX get all taint labels if the message matters that much
        for var, path, label in execute(
            cur, """ SELECT v, p, tag FROM LeakingSinkVertex """
        ):
            loc = _format_locations(cx, var)
            field_info = f" in field {path}"
            msg = f"Sink labeled '{label}'"
            if path:
                msg += field_info
            result = Result(
                ruleId="C0004",
                kind="informational",
                level="none",
                message=Message(f"{msg}."),
                properties=make_labels_properties([label]),
                locations=[loc],
            )
            sarif_results.append(result)

    if "vertex_result" in cx.result_types:
        for var, path in execute(
            cur,
            f"""
            SELECT v1, p1 FROM "forward_flow.ReachableVertex"
            UNION
            SELECT v1, p1 FROM "backward_flow.ReachableVertex"
            """,
        ):
            loc = _format_locations(cx, var)
            assert VertexTy(var, path) in info.labels_by_vertex
            labels = ", ".join(
                f"'{label}'" for label in info.labels_by_vertex[VertexTy(var, path)]
            )
            msg = f"Tainted data labeled {labels}"
            result = Result(
                ruleId="C0005",
                kind="informational",
                level="none",
                message=Message(f"{msg}."),
                properties=make_labels_properties(
                    info.labels_by_vertex[VertexTy(var, path)]
                ),
                locations=[loc],
            )
            sarif_results.append(result)

    if "instruction_result" in cx.result_types:
        for (insn,) in execute(
            cur,
            f"""
            SELECT insn FROM "natural_flow.ReachableEdge"
            """,
        ):
            loc = _format_locations(cx, insn)
            assert insn in info.labels_by_insn, f"{insn} not labeled"
            labels = ", ".join(f"'{label}'" for label in info.labels_by_insn[insn])
            msg = f"Tainted instruction labeled {labels}"
            result = Result(
                ruleId="C0002",
                kind="informational",
                level="none",
                message=Message(f"{msg}."),
                properties=make_labels_properties(info.labels_by_insn[insn]),
                locations=[loc],
            )
            sarif_results.append(result)

    if "source_sink_function_result" in cx.result_types:
        for fwd_insn, bwd_insn, func in execute(
            cur,
            f"""
            SELECT DISTINCT
                fwd.insn, bwd.insn, f2."function"
            FROM "forward_flow.ReachableEdge" fwd
            JOIN "IntCInsn_InFunction" f1 USING (insn)
            JOIN "IntCInsn_InFunction" f2 ON (f2."function" = f1."function")
            JOIN "backward_flow.ReachableEdge" bwd ON (bwd.insn = f2.insn)
            GROUP BY f2."function"
            """,
        ):
            fwd_loc = _format_locations(cx, fwd_insn)
            bwd_loc = _format_locations(cx, bwd_insn)
            assert fwd_insn in info.labels_by_insn, f"{fwd_insn} not labeled"
            assert bwd_insn in info.labels_by_insn, f"{bwd_insn} not labeled"
            labels = info.labels_by_insn[fwd_insn] + info.labels_by_insn[bwd_insn]
            msg = f"Source-sink function '{func}'"
            result = Result(
                ruleId="C0006",
                kind="informational",
                level="none",
                message=Message(f"{msg}."),
                locations=[fwd_loc, bwd_loc],
                properties=make_labels_properties(labels),
            )
            sarif_results.append(result)

    return dict(
        addresses=[],
        logicalLocations=cx._info.logical_locations_array,
        results=list(sorted(sarif_results, key=lambda r: r["ruleId"])),
        graphs=list(_format_graphs(cx)),
    )


def format_match_info(cx: Context) -> list[Result]:
    """Returns a list of SARIF results"""
    cur = cx.conn.cursor()
    info = cx._info
    _prepare(cx)
    execute(cur, """INSERT OR IGNORE INTO tainted_insn SELECT insn FROM Match_Insn""")
    execute(cur, """INSERT OR IGNORE INTO tainted_var SELECT var FROM Match_Var""")
    execute(
        cur,
        """
        INSERT OR IGNORE INTO tainted_func
        SELECT func AS function FROM Match_Func
        UNION
        SELECT function FROM Match_Insn mi
        JOIN IntCInsn_InFunction iif USING (insn)
        UNION
        SELECT function FROM Match_Var mi
        JOIN CVar_InFunction vif USING (var)
        """,
    )
    _load_physical_locations(cx)
    _make_logical_locations(cx)
    for child, parent in execute(
        cur,
        """
        SELECT child, parent FROM CNamespace_Parent
        JOIN tainted_func ON "child" = "func"
        """,
    ):
        info.parent_namespaces[child].append(parent)
    res = []
    for insn, label in execute(cur, """SELECT insn, label FROM Match_Insn"""):
        location = _format_locations(cx, insn)
        r = Result(
            ruleId="M0001",
            kind="informational",
            level="none",
            message=Message(f"Instruction matches label '{label}'"),
            locations=[location],
            properties=make_labels_properties([label]),
        )
        res.append(r)
    for var, label in execute(cur, """SELECT var, label FROM Match_Var"""):
        var_name = info.var_to_name[var]
        location = _format_locations(cx, var)
        r = Result(
            ruleId="M0002",
            kind="informational",
            level="none",
            message=Message(f"Var matches label '{label}': {var_name}"),
            locations=[location],
            properties=make_labels_properties([label]),
        )
        res.append(r)
    for function, label in execute(cur, """SELECT func, label FROM Match_Func"""):
        func_name = None if function is None else info.function_to_name[function]
        func_parent = "".join(
            [] if function is None else info.parent_namespaces[function][:1]
        )
        func_parent = (f" in '{func_parent}'") if func_parent else ""
        location = _format_locations(cx, function)
        r = Result(
            ruleId="M0003",
            kind="informational",
            level="none",
            message=Message(
                f"Function matches label '{label}': {func_name}{func_parent}"
            ),
            locations=[location],
            properties=make_labels_properties([label]),
        )
        res.append(r)
    return res


def _format_graphs(cx: Context) -> Iterator[Graph]:
    if "graphs" not in cx.result_types:
        return
    logger.info("collecting sarif graphs")
    info = cx._info
    for graph in info.graphs:
        nodes: list[Node] = []
        edges: list[Edge] = []
        for node in graph.get_nodes():
            nodes.append(_format_node(cx, node))
        for src, dst in graph.get_edges():
            edges.extend(
                _format_edge(
                    cx, TaintGraphEdge(direction=graph.direction, src=src, dst=dst)
                )
            )
        dir = "forward" if graph.direction.is_forward() else "backward"
        yield Graph(
            description=Message(
                f"Interprocedural {dir} graph of all tainted nodes and edges"
            ),
            nodes=nodes,
            edges=edges,
        )


def _format_node(cx: Context, node: VertexId) -> Node:
    info = cx._info
    node_loc = _format_locations(cx, info.id_to_vertex[node].var)
    return Node(id=f"{node}", label=Message(info.id_to_label[node]), location=node_loc)


def _format_edge(cx: Context, edge: TaintGraphEdge) -> Iterator[Edge]:
    """Returns the graph edges corresponding to a given taint graph edge.
    Returns one edge per instruction"""
    info = cx._info
    for insn_info in info.insns_by_edge[edge]:
        yield Edge(
            id=f"{edge.src}/{edge.dst}/{insn_info.insn}",
            sourceNodeId=f"{edge.src}",
            targetNodeId=f"{edge.dst}",
            label=Message(insn_info.insn),
        )


def _format_code_flows(cx: Context, path: TaintGraphPath) -> list[CodeFlow]:
    info = cx._info
    nodes = path.nodes
    start = info.id_to_vertex[nodes[0]]
    end = info.id_to_vertex[nodes[-1]]
    start_func, end_func = (
        info.var_in_func.get(start[0], "global"),
        info.var_in_func.get(end[0], "global"),
    )
    start_label = info.id_to_label[nodes[0]]
    start_var_name = info.var_to_name[start[0]]
    start_source_name = "".join(
        f"aka '{name}'" for name in info.var_to_source_names[start[0]]
    )

    thread_flows_locations = []
    msg = Message(
        f"Tainted data enters in '{start_var_name}' {start_source_name} in '{start_func}'"
    )

    def mk_annotations(entries) -> list[Region]:
        return [Region(message=Message(entry)) for entry in entries]

    thread_flows_locations.append(
        dict(
            location=(
                _format_locations(cx, start[0])
                | CleanDict(
                    message=msg,
                    annotations=mk_annotations(
                        [
                            f"Source vertex: '{start}'",
                            f"Source variable: '{start_var_name}'",
                        ]
                    ),
                )
            ),
            kinds=["taint", "acquire"],
            state={start_var_name: Message(f"label: {start_label}")},
            properties=Message("This is the source vertex"),
        )
    )
    for src, dst in pairwise(nodes):
        insn_info = info.insns_by_edge[
            TaintGraphEdge(direction=path.dir, src=src, dst=dst)
        ][0]
        insn_func = info.insn_in_func[insn_info.insn]
        location = _format_locations(cx, insn_info.insn)
        src_vertex, dst_vertex = info.id_to_vertex[src], info.id_to_vertex[dst]
        formatted_src_vertex, formatted_dst_vertex = (
            src_vertex.var + src_vertex.path,
            dst_vertex.var + dst_vertex.path,
        )
        formatted_assign = f"{formatted_dst_vertex} := {formatted_src_vertex}"
        src_var_name, dst_var_name = (
            info.var_to_name[src_vertex.var],
            info.var_to_name[dst_vertex.var],
        )
        src_local_name, dst_local_name = (
            src_var_name + src_vertex.path,
            dst_var_name + dst_vertex.path,
        )
        src_label, dst_label = info.id_to_label[src], info.id_to_label[dst]
        src_func, dst_func = info.var_in_func.get(src_vertex[0]), info.var_in_func.get(
            dst_vertex[0]
        )
        intraprocedural = src_func == dst_func
        step_kind = "intraprocedural" if intraprocedural else "interprocedural"
        # vloc = _format_locations(cx, dst_vertex[0])
        # XXX ?
        # location["logicalLocations"].append(vloc["logicalLocations"][0])
        from_source_name = " ".join(
            f" aka '{name}'" for name in info.var_to_source_names[src_vertex[0]]
        )
        to_source_name = " ".join(
            f" aka '{name}'" for name in info.var_to_source_names[dst_vertex[0]]
        )
        # step_copy = dc.replace(step, insns=step.insns[0:1])
        from_dec = _format_vertex_context(cx, src_vertex.var, insn_info)
        to_dec = _format_vertex_context(cx, dst_vertex.var, insn_info)
        from_func_name = None if src_func is None else info.function_to_name[src_func]
        from_func_parent = "".join(
            [] if src_func is None else info.parent_namespaces[src_func][:1]
        )
        from_func_parent = (f" in '{from_func_parent}'") if from_func_parent else ""
        to_func_parent = "".join(
            [] if dst_func is None else info.parent_namespaces[dst_func][:1]
        )
        to_func_parent = (f" in '{to_func_parent}'") if to_func_parent else ""
        to_func_name = None if dst_func is None else info.function_to_name[dst_func]
        from_star = "*" if src_func != insn_func else ""
        to_star = "*" if dst_func != insn_func else ""
        from_field = f" field '{src_vertex.path}'" if src_vertex.path else ""
        to_field = f" field '{dst_vertex.path}'" if dst_vertex.path else ""
        from_msg = Message(
            f"""[out of{from_star}] {from_dec} '{src_var_name}'{from_source_name}{from_field} in '{from_func_name}'{from_func_parent}"""
        )
        to_msg = f""" [into{to_star}] {to_dec} '{dst_var_name}'{to_source_name}{to_field} in '{to_func_name}'{to_func_parent}"""
        msg = textwrap.dedent(
            f"""
                [{step_kind}] {from_dec} '{src_local_name}' {from_source_name} in '{src_func}' flows to {to_dec} '{dst_local_name}' {to_source_name} in '{dst_func}'."""
        )
        if info.physical_locations_by_obj.get(insn_info.insn) is None:
            logging.debug("%s: no source code location insn: %s", src_func, insn_info)
        thread_flows_locations.append(
            dict(
                location=location
                | CleanDict(
                    message=from_msg,
                    annotations=mk_annotations(
                        [
                            f"Source vertex: '{formatted_src_vertex}' in '{src_func}'",
                            f"Source variable: '{src_local_name}'",
                            f"The tainted assignment text is '{formatted_assign}'",
                        ]
                    ),
                ),
                kinds=["taint", step_kind],
                state={src_local_name: {"text": f"labels: {src_label}"}},
                properties=dict(
                    # XXX pcode backend properties
                    additionalProperties=dict(insnDecoratedName=insn_info.insn),
                    # "insn": findings.insn_backend_properties(step_insn),
                ),
                # "nestingLevel": step.nesting_level,
            )
        )
        thread_flows_locations.append(
            dict(
                location=location
                | CleanDict(
                    message=Message(to_msg),
                    annotations=mk_annotations(
                        [
                            f"Destination vertex: '{formatted_dst_vertex}' in '{dst_func}'",
                            f"Destination variable: '{dst_local_name}'",
                            f"The tainted assignment text is '{formatted_assign}'",
                        ]
                    ),
                ),
                kinds=["taint", step_kind],
                state={dst_local_name: Message(f"labels: {dst_label}")},
                # "nestingLevel": step.nesting_level,
            )
        )
    path_length = len(nodes) - 1
    message = Message(
        f"Path from source to sink with {path_length} intermediate instructions"
    )
    return [
        CodeFlow(
            message=message,
            threadFlows=[ThreadFlow(message=message, locations=thread_flows_locations)],
        )
    ]


def _format_locations(
    cx: Context, obj: Union[VarIdStr, InsnIdStr, FuncIdStr]
) -> Location:
    # XXX could put other locations with "relationships"
    info = cx._info
    result = Location()

    try:
        # SARIF only specifies space for one physical location, even though our
        # schema supports multiple; just use the first one for now.
        phyloc = info.physical_locations_by_obj.get(obj, [])[0]
        result |= CleanDict(physicalLocation=phyloc)
    except IndexError:
        pass

    try:
        result |= CleanDict(
            logicalLocations=[
                LogicalLocation(index=info.logical_location_index_by_obj[obj])
            ]
        )
    except KeyError:
        pass

    return result


def _format_vertex_context(cx: Context, var: VarIdStr, edge: TaintGraphEdgeInfo) -> str:
    """Returns a string descriptor of the vertex's context"""
    var_cx = _var_context(cx, var, edge)
    if var_cx is None:
        return ""
    if isinstance(var_cx, Parameter):
        return f"parameter({var_cx.idx})"
    if isinstance(var_cx, ReturnParameter):
        return f"return value"
    raise ValueError("unknown vertex decoration")


def _var_context(
    cx: Context, var: VarIdStr, edge: TaintGraphEdgeInfo
) -> Optional[Union[Parameter, ReturnParameter]]:
    """Determines some context information for a variable, specifically whether
    it's used in a non-return parameter or a return parameter"""
    insn, insn_kind = edge.insn, edge.kind
    if insn_kind == "move":
        return None
    if not insn_kind in ("formal-to-actual", "actual-to-formal"):
        raise ValueError
    for formal in cx._info.formals_by_var.get(var, []):
        if formal.idx == cx._info.return_parameter_index:
            return ReturnParameter(idx=formal.idx)
        else:
            # XXX technically could be multiple, we would need to store
            # actual/formal index information on interprocedural flows to be
            # accurate.
            return Parameter(idx=formal.idx)
    for actual in cx._info.actuals_by_insn.get(insn, []):
        if actual.vertex[0] != var:
            continue
        if actual.idx == cx._info.return_parameter_index:
            return ReturnParameter(idx=actual.idx)
        else:
            return Parameter(idx=actual.idx)


def _load_taint_set(cx: Context):
    _prepare(cx)
    cur = cx.conn.cursor()
    info = cx._info

    for (index,) in execute(cur, """SELECT "index" FROM CReturnParameter"""):
        info.return_parameter_index = index

    fw_endpoints = set()
    if any(e in cx.result_types for e in ["graphs", "path_result"]):
        # Loads graphs and paths
        with ctadl.progressbar() as progress:
            taskid = progress.add_task("processing forward slice", total=None)
            fw_graph = _load_taint_graph(cx, SliceDirection.forward)
            if "path_result" in cx.result_types:
                info.insn_is_dataflow_only.update(
                    insn
                    for (insn,) in execute(cur, "SELECT insn FROM CInsn_isDataflowOnly")
                )
                ctadl.status("finding paths from sources to sinks", verb=1)
                for p in fw_graph.iter_paths(
                    progress=progress, taskid=taskid, strategy=cx.strategy
                ):
                    info.paths.append(TaintGraphPath(p, SliceDirection.forward))
                    fw_endpoints.add((p[0], p[-1]))
            if "graphs" not in cx.result_types:
                fw_graph = None  # free memory
            else:
                info.graphs.append(fw_graph)

            taskid = progress.add_task("processing backward slice", total=None)
            bw_graph = _load_taint_graph(cx, SliceDirection.backward)
            if "path_result" in cx.result_types:
                ctadl.status(f"finding paths from sinks to sources", verb=1)
                for p in bw_graph.iter_paths(
                    progress=progress, taskid=taskid, strategy=cx.strategy
                ):
                    # Filters out duplicates already in source-sink paths
                    if (p[0], p[-1]) not in fw_endpoints:
                        info.paths.append(TaintGraphPath(p, SliceDirection.backward))
            if "graphs" not in cx.result_types:
                bw_graph = None  # free memory
            else:
                info.graphs.append(bw_graph)
    logger.debug("paths: %s", info.paths)

    # Loads metadata in several chunks. All the queries are restricted to the
    # tainted set that we loaded above.
    with ctadl.progressbar() as progress:
        taskid = progress.add_task("loading slice metadata", total=4)
        _populate_taintset(cx)
        use_paths = set(["path_result"]) == cx.result_types
        for id, label, v, p in execute(
            cur,
            """ SELECT id, label, v1, p1 from "forward_flow.ReachableVertex" """
            + (f""" JOIN pathresult_id USING (id) """ if use_paths else "")
            + """
            UNION ALL
            SELECT id, label, v1, p1 from "backward_flow.ReachableVertex"
            """
            + (f""" JOIN pathresult_id USING (id) """ if use_paths else ""),
        ):
            vertex = VertexTy(v, p)
            info.labels_by_vertex[vertex].add(label)
            info.ids_by_vertex[vertex].add(id)
            assert id not in info.id_to_label or info.id_to_label[id] == label
            info.id_to_label[id] = label
            assert id not in info.id_to_vertex or info.id_to_vertex[id] == vertex
            info.id_to_vertex[id] = vertex
        progress.update(taskid, advance=1)
        if "source_result" in cx.result_types:
            for v, p, label in execute(
                cur, """ SELECT v, p, tag from "TaintSourceVertex" """
            ):
                vertex = VertexTy(v, p)
                info.ids_by_vertex[vertex]
                info.labels_by_vertex[vertex].add(label)
        if "sink_result" in cx.result_types:
            for v, p, label in execute(
                cur, """ SELECT v, p, tag from "LeakingSinkVertex" """
            ):
                vertex = VertexTy(v, p)
                info.ids_by_vertex[vertex]
                info.labels_by_vertex[vertex].add(label)
        for db_dir, src, dst, insn, kind in execute(
            cur,
            f"""
            SELECT 'forward' as dir, vertex_from, vertex_to, insn, kind
            FROM "forward_flow.ReachableEdge" """
            + (
                """
                JOIN taintpath_edge pet USING (vertex_from, vertex_to)
                WHERE pet.direction = 'forward'"""
                if use_paths
                else ""
            )
            + """
            UNION
            SELECT 'backward' as dir, vertex_to, vertex_from, insn, kind
            FROM "backward_flow.ReachableEdge" """
            + (
                """
                JOIN taintpath_edge AS pet USING (vertex_from, vertex_to)
                WHERE pet.direction = 'backward'"""
                if use_paths
                else ""
            ),
        ):
            dir = SliceDirection.from_str(db_dir)
            info.insns_by_edge[TaintGraphEdge(dir, src, dst)].append(
                TaintGraphEdgeInfo(insn, kind)
            )
            src_labels = cx._info.labels_by_vertex[cx._info.id_to_vertex[src]]
            dst_labels = cx._info.labels_by_vertex[cx._info.id_to_vertex[dst]]
            labels_by_insn = set(src_labels) & set(dst_labels)
            info.labels_by_insn[insn].update(labels_by_insn)
            info.vertices_by_insn[insn].update(
                chain.from_iterable(info.id_to_vertex[v] for v in (src, dst))
            )
        progress.update(taskid, advance=1)
        _load_physical_locations(cx)
        _make_logical_locations(cx)
        progress.update(taskid, advance=1)
        for child, parent in execute(
            cur,
            """
            SELECT child, parent FROM CNamespace_Parent
            JOIN tainted_func ON "child" = "func"
            """,
        ):
            info.parent_namespaces[child].append(parent)

        for func, index, var in execute(
            cur,
            """
            SELECT function, "index", param FROM CFunction_FormalParam
            JOIN tainted_var ON "name" = "var"
            """,
        ):
            info.formals_by_var[var].append(FormalParamInfo(func, index))

        for insn, index, var, path in execute(
            cur,
            """
            SELECT insn, "index", param, ap FROM CCall_ActualParam
            JOIN tainted_insn USING (insn)
            """,
        ):
            info.actuals_by_insn[insn].append(ActualArgInfo(VertexTy(var, path), index))
        progress.update(taskid, advance=1)


def _load_taint_graph(cx: Context, dir: SliceDirection):
    """Loads either the forward or backward graph"""
    cur = cx.conn.cursor()
    flow = "forward_flow" if dir.is_forward() else "backward_flow"
    edge_iter = (
        TaintGraphEdgeInput(src=row["src"], dst=row["dst"])
        for row in execute(
            cur,
            (
                f"""
                SELECT vertex_from AS src, vertex_to AS dst
                FROM "forward_flow.ReachableEdge"
                """
                if dir.is_forward()
                # Reverses the edge direction when selecting from backward_flow
                # so that all edges end up in the "natural", code-execution
                # direction
                else f"""
                SELECT vertex_to AS src, vertex_from AS dst
                FROM "backward_flow.ReachableEdge"
                """
            ),
        )
    )
    g = TaintGraph(direction=dir, edges=edge_iter)
    source_vertices = set(
        id
        for (id,) in execute(
            cur,
            f"""
            SELECT DISTINCT id FROM "{flow}.ReachableVertex"
            JOIN "TaintSourceVertex" ON "v1" = "v"
            """,
        )
    )
    sink_vertices = set(
        id
        for (id,) in execute(
            cur,
            f"""
            SELECT DISTINCT id FROM "{flow}.ReachableVertex"
            JOIN "LeakingSinkVertex" ON "v1" = "v"
            """,
        )
    )
    if logger.isEnabledFor(logging.INFO):
        logger.info(
            "%s leak graph: found %d source vertices, %d sink vertices",
            dir,
            len(source_vertices),
            len(sink_vertices),
        )
    # Removes sources that are sinks so that we don't get length-1 paths
    source_vertices.difference_update(sink_vertices)
    g.set_root_vertices(list(source_vertices))
    g.set_goal_vertices(list(sink_vertices))
    return g


def _make_logical_locations(cx: Context):
    cur = cx.conn.cursor()
    for var, name in execute(
        cur,
        """
        SELECT var, value FROM CVar_SourceInfo
        JOIN tainted_var USING ("var")
        WHERE key = 'name'
        """,
    ):
        cx._info.var_to_source_names[var].append(name)

    cx._info.function_to_name = Dict(
        (func, name)
        for func, name in execute(
            cur,
            """
            SELECT "function", name FROM CFunction_Name
            JOIN tainted_func ON ("func" = "function")
            """,
        )
    )
    # create logical locs for each function
    for func, name in cx._info.function_to_name.items():
        cx._info.logical_locations_by_obj[func] = LogicalLocation(
            name=name,
            kind="function",
            fullyQualifiedName=func,
            decoratedName=func,
        )

    cx._info.var_to_name = Dict(
        (var, name)
        for var, name in execute(
            cur,
            """
            SELECT var, name FROM CVar_Name
            JOIN tainted_var USING ("var")
            """,
        )
    )
    cx._info.var_in_func = Dict(
        (var, name)
        for var, name in execute(
            cur,
            """
            SELECT var, function FROM CVar_InFunction
            JOIN tainted_var USING ("var")
            """,
        )
    )

    def varFQN(var, name):
        try:
            return cx._info.var_in_func[var] + "::" + name
        except KeyError:
            return var

    # create logical locs for each var
    for var, name in cx._info.var_to_name.items():
        try:
            source_name = cx._info.var_to_source_names.get(var, [])[0]
        except IndexError:
            source_name = None
        cx._info.logical_locations_by_obj[var] = LogicalLocation(
            name=source_name or name,
            kind="variable",
            fullyQualifiedName=varFQN(var, source_name or name),
            decoratedName=var,
        )

    cx._info.insn_in_func = Dict(
        (insn, func)
        for insn, func in execute(
            cur,
            """
            SELECT insn, function FROM IntCInsn_InFunction
            JOIN tainted_insn USING ("insn")
            """,
        )
    )
    # create logical locs for each insn
    for insn, func in cx._info.insn_in_func.items():
        cx._info.logical_locations_by_obj[insn] = LogicalLocation(
            name=insn,  # could strip func prefix
            kind="member",
            fullyQualifiedName=insn,
            decoratedName=insn,
        )

    # Associates variables and instructions with the containing functions.
    for obj, loc in cx._info.logical_locations_by_obj.items():
        cx._info.logical_location_index_by_obj[obj] = len(
            cx._info.logical_locations_array
        )
        cx._info.logical_locations_array.append(loc)

    for var, func in cx._info.var_in_func.items():
        var_loc = cx._info.logical_locations_by_obj[var]
        var_loc["parentIndex"] = cx._info.logical_location_index_by_obj[func]
    for insn, func in cx._info.insn_in_func.items():
        insn_loc = cx._info.logical_locations_by_obj[insn]
        insn_loc["parentIndex"] = cx._info.logical_location_index_by_obj[func]


def _load_physical_locations(cx: Context):
    insn_regions: dict[str, list[PhysicalLocation]] = defaultdict(list)
    var_regions: dict[str, list[PhysicalLocation]] = defaultdict(list)
    for regions, element, tbl in [
        (insn_regions, "insn", "tainted_insn"),
        (var_regions, "var", "tainted_var"),
    ]:
        _load_addresses(cx, regions, element, tbl)
        _load_byte_regions(cx, regions, element, tbl)
        _load_char_regions(cx, regions, element, tbl)
        _load_line_regions(cx, regions, element, tbl)
    logger.debug(
        "found %s insn_regions", sum(len(locs) for locs in insn_regions.values())
    )
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug("insn_regions: %s", pformat(insn_regions))

    for insn, locs in insn_regions.items():
        cx._info.physical_locations_by_obj[insn].extend(locs)
    logger.debug("var_regions: %s", pformat(var_regions))
    for var, locs in var_regions.items():
        cx._info.physical_locations_by_obj[var].extend(locs)


def _load_addresses(cx, regions: dict[str, list[PhysicalLocation]], col: str, tbl: str):
    cur = cx.conn.cursor()
    for row in execute(
        cur,
        f"""
        SELECT DISTINCT
            file_id,
            region_id,
            uri,
            uriBaseId,
            {col},
            CAddress_AbsoluteAddress."addr" AS absoluteAddress,
            CAddress_RelativeAddress."addr" AS relativeAddress,
            length,
            name,
            kind,
            "fullyQualifiedName",
            offset AS offsetFromParent
        FROM CSourceInfo_Location
        JOIN "{tbl}" ON "element" = "{col}"
        JOIN CSourceInfo_File ON CSourceInfo_File."id" = "file_id"
        -- left outer join in case of optional fields
        LEFT OUTER JOIN CFile_UriBaseId  ON CFile_UriBaseId."id" = "file_id"
        JOIN CSourceInfo_Address ON CSourceInfo_Address."id" = "region_id"
        LEFT OUTER JOIN CAddress_AbsoluteAddress ON CAddress_AbsoluteAddress."id" = "region_id"
        LEFT OUTER JOIN CAddress_RelativeAddress ON CAddress_RelativeAddress."id" = "region_id"
        LEFT OUTER JOIN CAddress_Length ON CAddress_Length."id" = "region_id"
        LEFT OUTER JOIN CAddress_Kind ON CAddress_Kind."id" = "region_id"
        LEFT OUTER JOIN CAddress_Name ON CAddress_Name."id" = "region_id"
        LEFT OUTER JOIN CAddress_OffsetFromParent ON CAddress_OffsetFromParent."id" = "region_id"
        LEFT OUTER JOIN CAddress_FullyQualifiedName ON CAddress_FullyQualifiedName."id" = "region_id"
        """,
    ):
        key = row[col]
        id = str(row["file_id"]) + "/" + str(row["region_id"])
        root = None if Path(row["uri"]).is_absolute() else row["uriBaseId"]
        aloc = ArtifactLocation(uri=row["uri"], uriBaseId=root)
        addr_dict = Address()  # id=row["region_id"])
        for k in [
            "absoluteAddress",
            "relativeAddress",
            "length",
            "name",
            "kind",
            "fullyQualifiedName",
            "offsetFromParent",
        ]:
            if k in row.keys() and row[k] is not None:
                addr_dict |= {k: row[k]}
        addr = Address(addr_dict)
        loc = PhysicalLocation(artifactLocation=aloc, address=addr)
        regions[key].append(loc)


def _load_char_regions(
    cx, regions: dict[str, list[PhysicalLocation]], col: str, tbl: str
):
    cur = cx.conn.cursor()
    insn_ctr = defaultdict(int)
    for row in execute(
        cur,
        f"""
        SELECT DISTINCT
            file_id, region_id, uri, uriBaseId, {col}, charOffset, charLength FROM CSourceInfo_Location
        JOIN "{tbl}" ON "element" = "{col}"
        JOIN CSourceInfo_File ON CSourceInfo_File."id" = "file_id"
        LEFT OUTER JOIN CFile_UriBaseId  ON CFile_UriBaseId."id" = "file_id"
        JOIN CSourceInfo_CharRegion ON CSourceInfo_CharRegion."id" = "region_id"
        LEFT OUTER JOIN CCharRegion_Length  ON CCharRegion_Length.id = "region_id"
        """,
    ):
        key = row[col]
        id = str(row["file_id"]) + "/" + str(row["region_id"])
        root = None if Path(row["uri"]).is_absolute() else row["uriBaseId"]
        aloc = ArtifactLocation(uri=row["uri"], uriBaseId=root)
        region = Region(charOffset=row["charOffset"], charLength=row["charLength"])
        loc = PhysicalLocation(artifactLocation=aloc, region=region)
        regions[key].append(loc)


def _load_byte_regions(
    cx, regions: dict[str, list[PhysicalLocation]], col: str, tbl: str
):
    cur = cx.conn.cursor()
    for row in execute(
        cur,
        f"""
        SELECT DISTINCT
            file_id, region_id, uri, uriBaseId, {col}, byteOffset, byteLength FROM CSourceInfo_Location
        JOIN "{tbl}" ON "element" = "{col}"
        JOIN CSourceInfo_File ON CSourceInfo_File."id" = "file_id"
        LEFT OUTER JOIN CFile_UriBaseId  ON CFile_UriBaseId."id" = "file_id"
        JOIN CSourceInfo_ByteRegion ON CSourceInfo_ByteRegion."id" = "region_id"
        LEFT OUTER JOIN CByteRegion_Length ON CByteRegion_Length.id = "region_id"
        """,
    ):
        key = row[col]
        id = str(row["file_id"]) + "/" + str(row["region_id"])
        root = None if Path(row["uri"]).is_absolute() else row["uriBaseId"]
        aloc = ArtifactLocation(uri=row["uri"], uriBaseId=root)
        region = Region(byteOffset=row["byteOffset"], byteLength=row["byteLength"])
        loc = PhysicalLocation(artifactLocation=aloc, region=region)
        regions[key].append(loc)


def _load_line_regions(
    cx, regions: dict[str, list[PhysicalLocation]], col: str, tbl: str
):
    cur = cx.conn.cursor()
    # , startColumn, endLine, endColumn
    for row in execute(
        cur,
        f"""
        SELECT DISTINCT
            file_id, region_id, uri, uriBaseId, {col},
            startLine, startColumn, endLine, endColumn FROM CSourceInfo_Location
        JOIN "{tbl}" ON "element" = "{col}"
        JOIN CSourceInfo_File ON CSourceInfo_File."id" = "file_id"
        LEFT OUTER JOIN CFile_UriBaseId  ON CFile_UriBaseId."id" = "file_id"
        JOIN CSourceInfo_LineRegion ON CSourceInfo_LineRegion."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_StartColumn ON CLineRegion_StartColumn."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_EndLine ON CLineRegion_EndLine."id" = "region_id"
        LEFT OUTER JOIN CLineRegion_EndColumn ON CLineRegion_EndColumn."id" = "region_id"
        """,
    ):
        key = row[col]
        id = str(row["file_id"]) + "/" + str(row["region_id"])
        root = None if Path(row["uri"]).is_absolute() else row["uriBaseId"]
        aloc = ArtifactLocation(uri=row["uri"], uriBaseId=root)
        region = Region(
            startLine=row["startLine"],
            startColumn=row["startColumn"],
            endLine=row["endLine"],
            endColumn=row["endColumn"],
        )
        loc = PhysicalLocation(artifactLocation=aloc, region=region)
        regions[key].append(loc)


def _populate_taintset(cx: Context):
    """Populates our main tables -- tainted_insn, tainted_var, tainted_func, as
    well as pathresult_id and taintpath_edge, if applicable"""
    # Restricts populating temporary tables, either by the common case -- which
    # is just returning path results -- or generally by the total reachable
    # set
    cur = cx.conn.cursor()
    paths = cx._info.paths
    logger.debug("result_types: %s", cx.result_types)
    if set(["path_result"]) == cx.result_types:
        logger.debug(
            "populating pathidtbl, pathedgetbl, vartbl, insntbl, functiontbl from paths"
        )
        for dir, path in chain(
            (("forward", p.nodes) for p in paths if p.dir.is_forward()),
            (("backward", p.nodes) for p in paths if not p.dir.is_forward()),
        ):
            executemany(
                cur,
                """ INSERT OR IGNORE INTO pathresult_id (id) VALUES (?) """,
                [(id,) for id in path],
            )
            executemany(
                cur,
                """
                INSERT OR IGNORE INTO taintpath_edge (direction, vertex_from, vertex_to)
                VALUES (?, ?, ?)
                """,
                [(dir, src, dst) for src, dst in pairwise(path)],
            )
        cx.conn.commit()
        execute(
            cur,
            """
            INSERT OR IGNORE INTO "tainted_var"
            SELECT DISTINCT v1 AS var FROM pathresult_id
                JOIN "forward_flow.ReachableVertex" USING (id)
            UNION ALL
            SELECT DISTINCT v1 AS var FROM pathresult_id
                JOIN "backward_flow.ReachableVertex" USING (id)
            """,
        )
        execute(
            cur,
            """
            INSERT OR IGNORE INTO "tainted_insn"
            SELECT DISTINCT insn FROM taintpath_edge
            JOIN "forward_flow.ReachableEdge" USING (vertex_from, vertex_to)
            UNION ALL
            """
            # The backward case must be a bug.... Since taintpath edges is in
            # VirtualAssign order we have to re-reverse on this query
            """
            SELECT DISTINCT insn FROM taintpath_edge
            JOIN "backward_flow.ReachableEdge" USING (vertex_from, vertex_to)
            """,
        )
    else:
        logger.debug("populating vartbl, insntbl, functiontbl from reachable set")
        execute(
            cur,
            """
            INSERT OR IGNORE INTO "tainted_var"
            SELECT v1 FROM "forward_flow.ReachableVertex"
            UNION
            SELECT v1 FROM "backward_flow.ReachableVertex"
            UNION
            SELECT v FROM "TaintSourceVertex"
            UNION
            SELECT v FROM "LeakingSinkVertex"
            """,
        )
        execute(
            cur,
            """
            INSERT OR IGNORE INTO "tainted_insn"
            SELECT insn FROM "forward_flow.ReachableEdge"
            UNION
            SELECT insn FROM "backward_flow.ReachableEdge"
            """,
        )
    cx.conn.commit()
    execute(
        cur,
        f"""
        INSERT OR IGNORE INTO "tainted_func"
        SELECT DISTINCT function FROM "CVar_InFunction"
        JOIN "tainted_var" USING ("var")
        """,
    )
    execute(
        cur,
        f"""
        INSERT OR IGNORE INTO "tainted_func"
        SELECT DISTINCT function FROM "IntCInsn_InFunction"
        JOIN "tainted_insn" USING ("insn")
        """,
    )
    cx.conn.commit()
    if logger.isEnabledFor(logging.INFO):
        counts = [
            execute(cur, f"SELECT count(*) from {tbl}").fetchall()[0][0]
            for tbl in ["tainted_func", "tainted_var", "tainted_insn"]
        ]
        logger.info(
            "taint set contains %d functions, %d vars, %d instructions",
            counts[0],
            counts[1],
            counts[2],
        )


def _prepare(cx: Context) -> None:
    """Prepares the database for formatting. Must be called before
    format_run_info or format_match_info"""
    # If the context wants paths and not graphs, then we can use the paths to
    # heavily restrict the results we fetch from the database.
    # If they want graphs then we need to make sure to fetch addresses,
    # variables, and so on for the entire tire graph.
    # In both cases we don't fetch stuff that doesn't touch the taint graph.

    # Creates temp tables for instructions, variables, functions, paths
    conn = cx.conn
    cx.pycx.enter_context(
        TempTable(
            conn,
            "tainted_func",
            TableSpec([ColumnSpec("func", "TEXT NOT NULL")]),
            indexes=[["function"]],
        )
    )
    cx.pycx.enter_context(
        TempTable(
            conn,
            "tainted_var",
            TableSpec([ColumnSpec("var", "TEXT NOT NULL")]),
            indexes=[["var"]],
        )
    )
    cx.pycx.enter_context(
        TempTable(
            conn,
            "tainted_insn",
            TableSpec([ColumnSpec("insn", "TEXT NOT NULL")]),
            indexes=[["insn"]],
        )
    )
    cx.pycx.enter_context(
        TempTable(
            conn,
            "pathresult_id",
            TableSpec([ColumnSpec("id", "INTEGER NOT NULL")]),
            indexes=[["id"]],
        )
    )
    # Edges from each path stored in same, natural order as VirtualAssign.
    cx.pycx.enter_context(
        TempTable(
            conn,
            "taintpath_edge",
            TableSpec(
                [
                    ColumnSpec("direction", "TEXT NOT NULL"),
                    ColumnSpec("vertex_from", "INTEGER NOT NULL"),
                    ColumnSpec("vertex_to", "INTEGER NOT NULL"),
                ],
                constraint="UNIQUE(vertex_from, vertex_to)",
                is_set=False,
            ),
            indexes=[["vertex_from", "vertex_to"]],
        )
    )


# Makes a property bag with taintLabels but also an additionalProperties
# with taintLabels. The latter is because contrastsecurity only parses the
# additionalProperties.
def make_labels_properties(labels):
    return dict(
        taintLabels=list(labels),
        additionalProperties=dict(taintLabels=list(labels)),
    )
