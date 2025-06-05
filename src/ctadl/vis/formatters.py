import json
import logging
import sqlite3
import sys
from datetime import date
from typing import IO, Any

import ctadl
import ctadl.vis.sarif as sarif
from ctadl.vis.model import execute

ResultType = sarif.ResultType

logger = logging.getLogger(__name__)

# "Each run represents a single invocation of a single analysis tool, and the
# run has to describe the tool that produced it."


class BaseFormatter:
    def print_taint_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        """Formats taint results to file"""
        pass

    def print_match_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        """Formats match results to file"""
        pass


class Formatter(BaseFormatter):
    pass


class SummaryFormatter(BaseFormatter):
    def print_taint_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        """Formats taint results to file"""
        num_source_labels = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT tag FROM TaintSourceVertex)
             """,
        ).fetchall()[0][0]
        num_sink_labels = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT tag FROM LeakingSinkVertex)
             """,
        ).fetchall()[0][0]
        num_sources = execute(
            conn,
            """SELECT COUNT(*) FROM (SELECT DISTINCT v, p FROM TaintSourceVertex)""",
        ).fetchall()[0][0]
        num_sinks = execute(
            conn,
            """SELECT COUNT(*) FROM (SELECT DISTINCT v, p FROM LeakingSinkVertex)""",
        ).fetchall()[0][0]
        num_sink_leaks = execute(
            conn,
            """
            SELECT COUNT(*) FROM
                (SELECT DISTINCT
                    rv.v1 AS var, rv.p1 as path, label AS src_tag, ls.tag AS sink_tag
                FROM "forward_flow.ReachableVertex" rv
                JOIN LeakingSinkVertex ls ON ls.v = rv.v1 AND ls.p = rv.p1)
            """,
        ).fetchall()[0][0]
        num_source_leaks = execute(
            conn,
            """
            SELECT COUNT(*) FROM
                (SELECT DISTINCT
                    rv.v1 AS var, rv.p1 as path, label AS src_tag, ls.tag AS sink_tag
                FROM "backward_flow.ReachableVertex" rv
                JOIN TaintSourceVertex ls ON ls.v = rv.v1 AND ls.p = rv.p1)
            """,
        ).fetchall()[0][0]
        num_forward_tainted_edges = execute(
            conn, """ SELECT COUNT(DISTINCT insn) FROM "forward_flow.ReachableEdge" """
        ).fetchall()[0][0]
        num_backward_tainted_edges = execute(
            conn, """ SELECT COUNT(DISTINCT insn) FROM "backward_flow.ReachableEdge" """
        ).fetchall()[0][0]
        num_forward_tainted_funcs = execute(
            conn,
            """ SELECT COUNT(DISTINCT function) FROM "forward_flow.ReachableEdge" re
            JOIN CInsn_InFunction iif ON (re.insn = iif.insn) """,
        ).fetchall()[0][0]
        num_backward_tainted_funcs = execute(
            conn,
            """ SELECT COUNT(DISTINCT function) FROM "backward_flow.ReachableEdge" re
            JOIN CInsn_InFunction iif ON (re.insn = iif.insn) """,
        ).fetchall()[0][0]

        lines = []
        lines.append("summary of query results:")
        lines.append(f"{num_sink_leaks} sink vertexes reached by sources")
        lines.append(f"{num_source_leaks} source vertexes reached by sinks")
        lines.append(
            f"{num_source_labels} source taint labels across {num_sources} taint sources"
        )
        lines.append(
            f"{num_sink_labels} sink taint labels across {num_sinks} taint sinks"
        )
        lines.append(
            f"{num_forward_tainted_edges} instructions in forward source-slice"
        )
        lines.append(
            f"{num_backward_tainted_edges} instructions in backward sink-slice"
        )
        lines.append(f"{num_forward_tainted_funcs} functions in forward sink-slice")
        lines.append(f"{num_backward_tainted_funcs} functions in backward sink-slice")
        print("\n".join(lines), file=file)

    def print_match_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        num_insns = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT insn FROM Match_Insn)
             """,
        ).fetchall()[0][0]
        num_funcs = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT func FROM Match_Func)
             """,
        ).fetchall()[0][0]
        num_vars = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT var FROM Match_Var)
             """,
        ).fetchall()[0][0]
        num_fields = execute(
            conn,
            """
            SELECT COUNT(*) FROM
            (SELECT DISTINCT field FROM Match_Field)
             """,
        ).fetchall()[0][0]
        lines = []
        lines.append(f"{num_insns} instructions")
        lines.append(f"{num_funcs} functions")
        lines.append(f"{num_vars} variables")
        lines.append(f"{num_fields} fields")
        print("\n".join(lines), file=file)


JSONDict = dict[str, Any]


class SARIFFormatter(BaseFormatter):
    """
    Formats query results in SARIF format

    - code flows for each source-sink path
    """

    schema = "https://docs.oasis-open.org/sarif/sarif/v2.1.0/cos02/schemas/sarif-schema-2.1.0.json"
    version = "2.1.0"

    emit_results: list[ResultType]
    strategy: str

    def __init__(self, results: list[ResultType] = [], strat: str = "front"):
        self.emit_results = results
        self.strategy = strat

    def print_taint_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        con = conn
        meta = {
            "$schema": self.schema,
            "version": self.version,
            "properties": {
                "comment": "CTADL taint findings",
                "day": str(date.today()),
            },
        }
        logger.info("formatting sarif results")
        rules = [
            sarif.ReportingDescriptor(
                id="C0001",
                name="Tainted paths",
                shortDescription=sarif.Message("A path of tainted data flow"),
                messageStrings=dict(
                    default=sarif.Message("This is a tainted source-sink path.")
                ),
            ),
            sarif.ReportingDescriptor(
                id="C0002",
                name="Tainted instructions",
                shortDescription={"text": "An instruction with tainted data"},
                messageStrings={
                    "default": {
                        "text": """This instruction manipulates tainted data."""
                    }
                },
            ),
            sarif.ReportingDescriptor(
                id="C0003",
                name="Tainted data sources",
                shortDescription={"text": "Tainted data source"},
                messageStrings={
                    "default": {"text": """This is a source of tainted data."""}
                },
            ),
            sarif.ReportingDescriptor(
                id="C0004",
                name="Tainted data sink",
                shortDescription={"text": "Tainted data sinks"},
                messageStrings={
                    "default": {"text": """This is an desired sink of tainted data."""}
                },
            ),
            sarif.ReportingDescriptor(
                id="C0005",
                name="Tainted data",
                shortDescription={"text": "Tainted variables and fields"},
                messageStrings={"default": {"text": """This vertex is tainted."""}},
            ),
            sarif.ReportingDescriptor(
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
        cx = sarif.Context(con, self.emit_results, self.strategy)
        config = {
            key: val
            for key, val in execute(
                cx.conn, """ SELECT feature, value FROM CTADLConfig """
            )
        }
        stats = {
            key: val
            for key, val in execute(
                cx.conn, """ SELECT stat_name, n FROM CTADLStats """
            )
        }
        run = {
            "tool": {
                "driver": {
                    "name": "ctadl",
                    "version": ctadl.__version__,
                    "informationUri": "https://github.com/sandialabs/ctadl",
                    "fullDescription": {
                        "text": "CTADL (Compositional Taint Analysis in Datalog)."
                    },
                    "rules": rules,
                    "properties": {
                        "short_description": "Compositional Taint Analysis in Datalog",
                        "config": config,
                        "stats": stats,
                    },
                },
            },
        } | sarif.format_run_info(cx)
        runs = {"runs": [run]}

        log = meta | runs

        print(json.dumps(log, indent=2), file=file)

    def print_match_results(
        self, conn: sqlite3.Connection, file: IO[Any] = sys.stdout, **kwargs
    ) -> None:
        cx = sarif.Context(conn, self.emit_results, self.strategy)
        print(json.dumps(sarif.format_match_info(cx), indent=2), file=file)
