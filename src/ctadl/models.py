import dataclasses
import importlib.resources as resources
import json
import logging
import re
import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import chain, groupby
from typing import Literal, Union

try:
    import pyjson5 as json5
except ImportError:
    import json5

import ctadl
from ctadl import progressbar, status, warn
from ctadl.util.functions import CleanDict
from ctadl.util.graph import Counter
from ctadl.vis.model import ColumnSpec, Facts, TableSpec, TempTable, execute
from ctadl.vis.types import SliceDirection

logger = logging.getLogger(__name__)


def match_pattern(input_string, pattern) -> re.Match:
    compiled_pattern = re.compile(pattern)
    return compiled_pattern.match(input_string)


@dataclass(frozen=True)
class JSONModelNode:
    """A JSONModelNode is part of a tree that represents evaluation criteria
    for creating models of methods at analysis time"""

    id: str


@dataclass(frozen=True)
class OpNode(JSONModelNode):
    op: Literal["union", "intersection"]
    left: JSONModelNode
    right: JSONModelNode

    @staticmethod
    def mk(
        id: str,
        op: Literal["union", "intersection"],
        left: JSONModelNode,
        right: JSONModelNode,
    ) -> JSONModelNode:
        if isinstance(left, NothingNode):
            return right
        if isinstance(right, NothingNode):
            return left
        if op not in ["union", "intersection"]:
            raise ValueError("op must be union or intersection")
        return OpNode(id=id, op=op, left=left, right=right)

    @staticmethod
    def mk_union(id: str, left: JSONModelNode, right: JSONModelNode) -> JSONModelNode:
        return OpNode.mk(id=id, op="union", left=left, right=right)

    @staticmethod
    def mk_intersection(
        id: str, left: JSONModelNode, right: JSONModelNode
    ) -> JSONModelNode:
        return OpNode.mk(id=id, op="intersection", left=left, right=right)


@dataclass(frozen=True)
class Atom(JSONModelNode):
    relation: str
    args: tuple[Union[str, int], ...] = dataclasses.field(default_factory=tuple)
    inners: tuple[str, ...] = dataclasses.field(default_factory=tuple)


@dataclass(frozen=True)
class NothingNode(JSONModelNode):
    """This magically stands for the identity element of union and
    intersection"""

    pass


class JSONTranslator:
    filename: str
    counter: Counter
    nothing_id: int
    nodes: set[JSONModelNode]
    nodes_output: set[JSONModelNode]

    def __init__(self, facts: Facts):
        self.facts = facts
        self.counter = Counter(i=1)
        self.nothing_id = 0
        self.nodes = set()
        self.nodes_output = set()
        self.initialize_relations()

    @staticmethod
    def as_port(index: int, field: str) -> str:
        field = field.replace("..*", ".*")
        return f"Argument({index}){field}"

    @staticmethod
    def get_endpoint_models(conn: sqlite3.Connection):
        name_by_var = {}
        func_by_var = {}
        source_models_by_var = defaultdict(list)
        sink_models_by_var = defaultdict(list)
        for endpoint, var, path, label, name, func in execute(
            conn,
            """
            SELECT endpoint, v, p, tag, vn.name, vf.function FROM (
                SELECT 'source' AS endpoint, v, p, tag FROM TaintSourceVertex
                UNION
                SELECT 'sink' AS endpoint, v, p, tag FROM LeakingSinkVertex
            )
            JOIN CVar_Name vn ON (v = vn.var)
            LEFT OUTER JOIN CVar_InFunction vf ON (v = vf.var)
            """,
        ):
            name_by_var[var] = name
            if func:
                func_by_var[var] = func
            models_by_var = (
                source_models_by_var if endpoint == "source" else sink_models_by_var
            )
            models_by_var[var].append(CleanDict(kind=label, field=path or None))
        generators = []
        for var in name_by_var:
            generators.append(
                dict(
                    find="variables",
                    where=[
                        CleanDict(
                            constraint="signature_match",
                            name=name_by_var[var],
                            parent=func_by_var.get(var),
                        )
                        | {"unqualified-id": var}
                    ],
                    model=CleanDict(
                        sources=source_models_by_var.get(var),
                        sinks=sink_models_by_var.get(var),
                    ),
                )
            )
        return dict(model_generators=generators)

    @staticmethod
    def get_unmodeled_ports(conn: sqlite3.Connection):
        func_input_ports = defaultdict(set)
        func_output_ports = defaultdict(set)
        func_labels = defaultdict(set)
        for label, function, index, ap, direction in execute(
            conn,
            """ SELECT tag, function, "index", ap, direction from isTaintedArgUnmodeled """,
        ):
            dir = SliceDirection.from_str(direction)
            if dir == SliceDirection.forward:
                func_input_ports[function].add(JSONTranslator.as_port(index, ap))
            if dir == SliceDirection.backward:
                func_output_ports[function].add(JSONTranslator.as_port(index, ap))
            func_labels[function].add(label)
        finds = []
        for f in sorted(chain(func_input_ports, func_output_ports)):
            d = dict(
                find="methods",
                where=[{"constraint": "signature_match", "unqualified-id": f}],
                model=dict(
                    propagation=[
                        [{"input": i} for i in func_input_ports[f]]
                        + [{"output": i} for i in func_output_ports[f]]
                    ]
                ),
            )
            finds.append(d)
        res = {"model_generators": finds}
        return res

    @staticmethod
    def get_propagation_models(
        conn: sqlite3.Connection,
    ):
        """Turns all summaries from index into model generators"""

        def handle_arg(index: int):
            if index == -1:
                return "Return"
            return f"Argument({index})"

        with TempTable(
            conn,
            "mg_function",
            TableSpec(cols=[ColumnSpec("function", "TEXT NOT NULL, UNIQUE(function)")]),
        ):
            cur = conn.cursor()
            execute(
                cur,
                f"""
                INSERT OR IGNORE INTO "mg_function" (function)
                SELECT m1 FROM "SummaryFlow"
                UNION ALL SELECT m2 FROM "SummaryFlow"
                WHERE m1 = m2 and ctx = ''
                """,
            )
            conn.commit()
            names = dict()
            signatures = dict()
            parents = dict()
            for function, name, signature, parent in execute(
                conn,
                """
                SELECT mg."function", name, signature, parent FROM mg_function mg
                JOIN CFunction_Name name ON (mg.function = name.function)
                JOIN CFunction_Signature sig ON (mg.function = sig.function)
                LEFT OUTER JOIN CNamespace_Parent ns ON (mg.function = ns.child)
                """,
            ):
                names[function] = name
                signatures[function] = signature
                if parent:
                    parents[function] = parent

            # Loads summaries and groups them by function
            models_by_func = defaultdict(list)
            for f, dst_n, dst_ap, src_n, src_ap in execute(
                conn,
                """
                SELECT m1, n1, p1, n2, p2  FROM SummaryFlow
                WHERE m1 = m2 AND ctx = ''
                ORDER BY m1
                """,
            ):
                inbase = handle_arg(src_n)
                outbase = handle_arg(dst_n)
                inap, outap = src_ap, dst_ap
                models_by_func[f].append(
                    dict(input=f"{inbase}{inap}", output=f"{outbase}{outap}")
                )

            return dict(
                model_generators=[
                    CleanDict(
                        find="methods",
                        where=[
                            CleanDict(
                                constraint="signature_match",
                                name=names[func],
                                parent=parents.get(func),
                            )
                            | {"unqualified-id": func},
                            dict(
                                constraint="signature_match", pattern=signatures[func]
                            ),
                        ],
                        models=models,
                    )
                    for func, models in models_by_func.items()
                ]
            )

    def initialize_relations(self):
        self.op_rel = self.facts.add_input_relation(
            "MG_OpNode",
            [ColumnSpec("nodeid", "TEXT NOT NULL"), ColumnSpec("op", "TEXT NOT NULL")],
        )
        self.edge_rel = self.facts.add_input_relation(
            "MG_Edge2",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("child1", "TEXT NOT NULL"),
                ColumnSpec("child2", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_Edge1",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("child1", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_AllOf",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_AnyOf",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_Not",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_SigMatchParent",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("parent", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_SigMatchPattern",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("pattern", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_SigMatchName",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("name", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_SigMatchUnqualifiedId",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("function", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_Parent", [ColumnSpec("nodeid", "TEXT NOT NULL")]
        )
        self.facts.add_input_relation(
            "MG_Extends", [ColumnSpec("nodeid", "TEXT NOT NULL")]
        )
        self.facts.add_input_relation(
            "MG_Parameter",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("index", "INTEGER NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_AnyParameter",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("start_idx", "INTEGER NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_NumberParameters",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_IntCompare",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("rel", "TEXT NOT NULL"),
                ColumnSpec("value", "INTEGER NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_Name",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("pattern", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_HasCode",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("value", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_ForwardSelf",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("whereid", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_ForwardCall",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("targetid", "TEXT NOT NULL"),
                ColumnSpec("forwardid", "TEXT NOT NULL"),
                ColumnSpec("isdirect", "INTEGER NOT NULL"),
                ColumnSpec("param", "INTEGER NOT NULL"),
                ColumnSpec("ap", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_UsesFieldName",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("name", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_UsesFieldUnqualifiedId",
            [ColumnSpec("nodeid", "TEXT NOT NULL"), ColumnSpec("id", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_Propagation",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("propid", "TEXT NOT NULL"),
                ColumnSpec("direction", "TEXT NOT NULL"),
                ColumnSpec("param", "INTEGER NOT NULL"),
                ColumnSpec("is_star", "INTEGER NOT NULL"),
                ColumnSpec("ap", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_Endpoint",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("source_or_sink", "TEXT NOT NULL"),
                ColumnSpec("label", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_EndpointVertex",
            [
                ColumnSpec("nodeid", "TEXT NOT NULL"),
                ColumnSpec("param", "INTEGER NOT NULL"),
                ColumnSpec("is_star", "INTEGER NOT NULL"),
                ColumnSpec("ap", "TEXT NOT NULL"),
                ColumnSpec("all_fields", "TEXT NOT NULL"),
            ],
        )
        self.facts.add_input_relation(
            "MG_EndpointField",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )
        self.facts.add_input_relation(
            "MG_EndpointInsn",
            [ColumnSpec("nodeid", "TEXT NOT NULL")],
        )

    def atom(self, *args, **kwargs) -> Atom:
        """Creates an atom with automatic id and adds it to internal list of
        nodes"""
        if "id" not in kwargs:
            kwargs.update(dict(id=str(self.counter.increment())))
        a = Atom(*args, **kwargs)
        self.nodes.add(a)
        return a

    def op(self, *args, **kwargs) -> JSONModelNode:
        assert "id" not in kwargs
        kwargs.update(dict(id=str(self.counter.increment())))
        o = OpNode.mk(*args, **kwargs)
        self.nodes.add(o)
        return o

    def nothing(self) -> NothingNode:
        return NothingNode(id=str(self.nothing_id))

    def reduce_op(
        self, op: Literal["union", "intersection"], nodes: Iterable[JSONModelNode]
    ) -> JSONModelNode:
        """Performs associative op on the iterable of nodes and returns root
        node"""
        # We put a "nothing" on front...
        node_iter = chain([self.nothing()], nodes)
        # ... which ensures this next() call works
        m = next(node_iter)
        for n in node_iter:
            m = self.op(op=op, left=n, right=m)
        return m

    def output_datalog_constraint(self, writer, n: JSONModelNode) -> bool:
        """Outputs a node constraint

        If the constraint was already output, returns False. Otherwise returns
        True"""
        if n in self.nodes_output or isinstance(n, NothingNode):
            return False
        self.nodes_output.add(n)
        if isinstance(n, Atom):
            # XXX could add types from atom here, if Atom had types
            args = [("nodeid", "TEXT_NOT_NULL")] + list(
                (
                    f"{i}",
                    ("TEXT NOT NULL" if isinstance(arg, str) else "INTEGER NOT NULL"),
                )
                for i, arg in enumerate(n.args)
            )
            self.facts.write(writer, n.relation, n.id, *n.args)
            for inner_id in n.inners:
                self.facts.write(writer, "MG_Edge1", n.id, inner_id)
        elif isinstance(n, OpNode):
            self.facts.write(writer, self.op_rel, n.id, n.op)
            self.facts.write(writer, self.edge_rel, n.id, n.left.id, n.right.id)
        return True

    def con_port(self, port_desc: str) -> tuple[str, str]:
        buf = port_desc

        def parse_var():
            nonlocal buf
            if m := match_pattern(buf, "Return"):
                buf = buf[m.end() :]
                return "-1"
            if m := match_pattern(buf, "Argument\\((-?[0-9]+)\\)"):
                buf = buf[m.end() :]
                return m.group(1)
            if m := match_pattern(buf, "Argument\\((\\*)\\)"):
                buf = buf[m.end() :]
                return m.group(1)
            raise ValueError

        port = parse_var()
        buf = buf.replace(".*", "..*")
        return (port, buf)

    def mod_propagation(self, root: JSONModelNode, props):
        for propid, prop in enumerate(props):
            outvar, outfield = self.con_port(prop.get("output"))
            invar, infield = self.con_port(prop.get("input"))
            self.atom(
                relation="MG_Propagation",
                id=root.id,
                args=(
                    str(propid),
                    "input",
                    -100 if invar == "*" else int(invar),
                    int(invar == "*"),
                    infield,
                ),
            )
            self.atom(
                relation="MG_Propagation",
                id=root.id,
                args=(
                    str(propid),
                    "output",
                    -100 if outvar == "*" else int(outvar),
                    int(outvar == "*"),
                    outfield,
                ),
            )

    def mod_endpoints_on_methods(self, root: JSONModelNode, sources, sinks):
        for endtype, endp in chain(
            (("sink", s) for s in sinks), (("source", s) for s in sources)
        ):
            label = endp["kind"]
            pairs = []
            all_fields_default = True
            if "port" in endp:
                all_fields_default = False
                pairs.append(self.con_port(endp["port"]))
            else:
                # Includes all params and return value if no port given
                pairs.extend([("*", ""), ("-1", "")])
            all_fields = endp.get("all_fields", all_fields_default)
            for var, field in pairs:
                self.atom(
                    relation="MG_Endpoint",
                    id=root.id,
                    args=(
                        endtype,
                        label,
                    ),
                )
                self.atom(
                    relation="MG_EndpointVertex",
                    id=root.id,
                    args=(
                        -100 if var == "*" else int(var),
                        int(var == "*"),
                        field,
                        "true" if all_fields else "false",
                    ),
                )

    def mod_endpoints_on_variables(self, root: JSONModelNode, sources, sinks):
        for endtype, endp in chain(
            (("sink", s) for s in sinks), (("source", s) for s in sources)
        ):
            label = endp["kind"]
            fields = []
            if "field" in endp:
                fields.append(endp["field"])
            fields.extend(endp.get("fields", []))
            all_fields = endp.get("all_fields", False)
            for field in fields:
                field = field.replace(".*", "..*")
                self.atom(
                    relation="MG_Endpoint",
                    id=root.id,
                    args=(
                        endtype,
                        label,
                    ),
                )
                self.atom(
                    relation="MG_EndpointVertex",
                    id=root.id,
                    args=(
                        -100,
                        0,
                        field,
                        "true" if all_fields else "false",
                    ),
                )

    def mod_endpoints_on_fields(self, root: JSONModelNode, sources, sinks):
        for endtype, endp in chain(
            (("sink", s) for s in sinks), (("source", s) for s in sources)
        ):
            label = endp["kind"]
            # var, field = self.con_port(endp["port"])
            all_fields = endp.get("all_fields", False)
            self.atom(
                relation="MG_Endpoint",
                id=root.id,
                args=(
                    endtype,
                    label,
                ),
            )
            self.atom(
                relation="MG_EndpointField",
                id=root.id,
                args=(),
            )

    def mod_endpoints_on_instructions(
        self, root: JSONModelNode, sources, sinks, taints
    ):
        for endtype, endp in chain(
            (("sink", s) for s in sinks),
            (("source", s) for s in sources),
            (("taint", s) for s in taints),
        ):
            label = endp["kind"]
            # var, field = self.con_port(endp["port"])
            all_fields = endp.get("all_fields", False)
            self.atom(
                relation="MG_Endpoint",
                id=root.id,
                args=(
                    endtype,
                    label,
                ),
            )
            self.atom(
                relation="MG_EndpointInsn",
                id=root.id,
                args=(),
            )

    def mod_forward_call(self, find_root: JSONModelNode, call):
        if not call:
            return
        forward_where = self.reduce_op(
            "intersection",
            [self.handle_constraint(con) for con in call.get("where", [])],
        )
        is_direct = True
        var, fld = "", ""
        if "receiver" in call:
            is_direct = False
            var, _ = self.con_port(call["receiver"])
        assert var != "*"
        self.atom(
            relation="MG_ForwardCall",
            args=(
                find_root.id,
                forward_where.id,
                1 if is_direct else 0,
                var,
                "",  # field ignored
            ),
        )

    def mod_forward_self(self, root: JSONModelNode, forward_self):
        if not forward_self:
            return
        forward_where = self.reduce_op(
            "intersection",
            [self.handle_constraint(con) for con in forward_self.get("where", [])],
        )
        self.atom(
            relation="MG_ForwardSelf",
            id=root.id,
            args=(forward_where.id,),
        )

    def handle_models(self, root: JSONModelNode, model, *, find: str):
        sources, sinks = model.get("sources", []), model.get("sinks", [])
        taints = model.get("taint", [])
        if find == "methods":
            self.mod_propagation(root, model.get("propagation", []))
            self.mod_endpoints_on_methods(root, sources, sinks)
            self.mod_forward_self(root, model.get("forward_self", {}))
            self.mod_forward_call(root, model.get("forward_call", {}))
        elif find == "variables":
            self.mod_endpoints_on_variables(root, sources, sinks)
        elif find == "fields":
            self.mod_endpoints_on_fields(root, sources, sinks)
        elif find == "instructions":
            self.mod_endpoints_on_instructions(root, sources, sinks, taints)
        else:
            raise ValueError(f"unknown find method: '{find}'")

    def con_signature(self, con) -> JSONModelNode:
        assert con["constraint"] in ["signature", "signature_pattern"]
        return self.atom(
            relation="MG_SigMatchPattern",
            args=(con["pattern"],),
        )

    def con_signature_match(self, con) -> JSONModelNode:
        assert con["constraint"] == "signature_match"
        # Nodes that match on each name
        nodes: list[JSONModelNode] = [
            self.atom(
                relation="MG_SigMatchName",
                args=(name,),
            )
            for name in con.get("names", [])
        ]
        c1 = self.reduce_op("union", nodes)
        c2 = self.nothing()
        if "name" in con:
            c2 = self.atom(
                relation="MG_SigMatchName",
                args=(con["name"],),
            )
        nodes = [
            self.atom(
                relation="MG_SigMatchParent",
                args=(name,),
            )
            for name in con.get("parents", [])
        ]
        c3 = self.reduce_op("union", nodes)
        c4 = self.nothing()
        if "parent" in con:
            c4 = self.atom(
                relation="MG_SigMatchParent",
                args=(con["parent"],),
            )
        c5 = self.nothing()
        if "unqualified-id" in con:
            c5 = self.atom(
                relation="MG_SigMatchUnqualifiedId", args=(con["unqualified-id"],)
            )
        return self.reduce_op("intersection", [c1, c2, c3, c4, c5])

    def con_parent(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(relation="MG_Parent", inners=(inner.id,))

    def con_extends(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(relation="MG_Extends", inners=(inner.id,))

    def con_name(self, con) -> JSONModelNode:
        return self.atom(
            relation="MG_Name",
            args=(con["pattern"],),
        )

    def con_parameter(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(
            relation="MG_Parameter",
            args=(con["idx"],),
            inners=(inner.id,),
        )

    def con_any_parameter(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(
            relation="MG_AnyParameter", args=(con["start_idx"],), inners=(inner.id,)
        )

    def con_number_parameters(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(
            relation="MG_NumberParameters",
            inners=(inner.id,),
        )

    def con_uses_field(self, con) -> JSONModelNode:
        nodes: list[JSONModelNode] = [
            self.atom(
                relation="MG_UsesFieldName",
                args=(name,),
            )
            for name in con.get("names", [])
        ]
        c1 = self.reduce_op("union", nodes)
        c2 = self.nothing()
        if "name" in con:
            c2 = self.atom(relation="MG_UsesFieldName", args=(con["name"],))
        c3 = self.nothing()
        if "unqualified-id" in con:
            c3 = self.atom(
                relation="MG_UsesFieldUnqualifiedId", args=(con["unqualified-id"],)
            )
        return self.reduce_op("intersection", [c1, c2, c3])

    def con_int_compare(self, con) -> JSONModelNode:
        return self.atom(
            relation="MG_IntCompare",
            args=(con["constraint"], con["value"]),
        )

    def con_has_code(self, con) -> JSONModelNode:
        return self.atom(
            relation="MG_HasCode",
            args=(str(con["value"]).lower(),),
        )

    def con_any_of(self, con) -> JSONModelNode:
        inners = [self.handle_constraint(inner) for inner in con["inners"]]
        return self.reduce_op("union", inners)

    def con_all_of(self, con) -> JSONModelNode:
        inners = [self.handle_constraint(inner) for inner in con["inners"]]
        return self.reduce_op("intersection", inners)

    def con_not(self, con) -> JSONModelNode:
        inner = self.handle_constraint(con["inner"])
        return self.atom(relation="MG_Not", inners=(inner.id,))

    def handle_constraint(self, desc) -> JSONModelNode:
        """Translates a "constraint" from the model json"""
        if "constraint" not in desc:
            return self.nothing()
        constraint = desc["constraint"]
        if constraint == "name":
            return self.con_name(desc)
        elif constraint == "signature_match":
            return self.con_signature_match(desc)
        elif constraint in ["signature", "signature_pattern"]:
            return self.con_signature(desc)
        elif constraint == "parent":
            return self.con_parent(desc)
        elif constraint == "extends":
            return self.con_extends(desc)
        elif constraint == "parameter":
            return self.con_parameter(desc)
        elif constraint == "any_parameter":
            return self.con_any_parameter(desc)
        elif constraint == "number_parameters":
            return self.con_number_parameters(desc)
        elif constraint == "uses_field":
            return self.con_uses_field(desc)
        elif constraint in ["<", "<=", ">", ">=", "!=", "=="]:
            return self.con_int_compare(desc)
        elif constraint == "has_code":
            return self.con_has_code(desc)
        elif constraint == "any_of":
            return self.con_any_of(desc)
        elif constraint == "all_of":
            return self.con_all_of(desc)
        elif constraint == "not":
            return self.con_not(desc)
        else:
            raise ValueError(f"Unrecognized constraint: '{constraint}'")

    def handle_find(self, generator, *, find: str) -> JSONModelNode:
        logger.debug("start: %s", generator)
        root = self.reduce_op(
            "intersection",
            [self.handle_constraint(con) for con in generator.get("where", [])],
        )
        self.handle_models(root, generator.get("model", {}), find=find)
        return root

    def handle_model_generator(self, generator) -> JSONModelNode:
        find = generator.get("find")
        if find in ["methods", "variables", "fields", "instructions"]:
            return self.handle_find(generator, find=find)
        else:
            raise ValueError(f"unknown find type: {find}")

    def validate_models(self, instance, *, filename):
        with resources.as_file(
            resources.files(ctadl) / "models" / "ctadl-model-generator.schema.json"
        ) as schema:
            with open(schema, "rb") as fp:
                schema = json.loads(fp.read())
        # import fastjsonschema
        # v = fastjsonschema.compile(schema)
        # print(v(instance))

        try:
            from jsonschema import validate
        except ImportError:
            warn(f"omitting model validation, jsonschema not found")
            return instance

        status(f"validating models in '{filename}'", verb=1)
        validate(instance=instance, schema=schema)
        return instance

    def translate(self, filename, validate: bool = True, progress=True):
        """Translates a list of model_generators (in json format) and adds them
        to the analyzer inputs"""

        status(f"importing models in '{filename}'", verb=1)
        with open(filename, "rb") as fp:
            parser = json
            contents = fp.read()
            if str(filename).endswith(".json5"):
                parser = json5
                contents = contents.decode()
            models = parser.loads(contents)
        if not isinstance(models, dict):
            return
        if validate:
            self.validate_models(models, filename=filename)
        with progressbar(fake=not progress) as pbar:
            model_generators = models.get("model_generators", [])
            roots = []
            task = pbar.add_task(
                description="processing model_generators", total=len(model_generators)
            )
            # how many elements before updating progress bar
            period, i = 5101, 0
            for i, gen in enumerate(model_generators, start=1):
                roots.append(self.handle_model_generator(gen))
                if i % period == 0:
                    pbar.update(task, advance=period)
            pbar.update(task, advance=(i % period))
        with progressbar(fake=not progress) as pbar:
            task = pbar.add_task(description="writing models", total=len(self.nodes))
            period, i = 21001, 0
            with self.facts.writer() as writer:
                for i, n in enumerate(self.nodes, start=1):
                    self.output_datalog_constraint(writer, n)
                    if i % period == 0:
                        pbar.update(task, advance=period)
                pbar.update(task, advance=(i % period))
