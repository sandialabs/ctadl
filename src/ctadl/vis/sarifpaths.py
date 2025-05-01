"""
Given a set of vertices, return paths to and from sources and sinks

- We allow a set of vertices because we are really going to start from an
  instruction and we want to consider all the adjacent vertices, which is
  usually at least two.

Ideally we would use iterative deepening and be able to return paths at level 1, 2, 3...

Ensure that multiple requests of this type don't cause a lock on the database
"""

import logging
import sqlite3
from pprint import pformat
from typing import Collection, Iterable, Iterator, NamedTuple, Optional, Union

from ctadl.vis.model import ColumnSpec, TableSpec, TempTable, execute, executemany
from ctadl.vis.taintgraph import (
    Path,
    SemiNaiveMinPathLength,
    PathAvoidStrategy,
)
from ctadl.vis.types import SliceDirection, VertexId, VertexTy

logger = logging.getLogger(__name__)


def find_paths(
    conn: sqlite3.Connection, vertices: Collection[VertexTy]
) -> Iterator[Path]:
    """
    Finds paths in the taint graph that connect to the given vertices.

    Both the forward and backward taint graphs are searched.
    """

    sources: list[VertexId] = [
        id
        for (id,) in execute(
            conn,
            """
            SELECT id from "flow.ReachableVertex" v
            JOIN TaintSourceVertex source ON (v.v1 = source.v AND v.p1 = source.p)
            """,
        )
    ]
    sinks: list[VertexId] = [
        id
        for (id,) in execute(
            conn,
            """
            SELECT id from "flow.ReachableVertex" v
            JOIN LeakingSinkVertex sink ON (v.v1 = sink.v AND v.p1 = sink.p)
            """,
        )
    ]
    with TempTable(
        conn,
        "vertex_input",
        TableSpec(
            [ColumnSpec("v1", "TEXT NOT NULL"), ColumnSpec("p1", "TEXT NOT NULL")]
        ),
    ):
        for dir in [SliceDirection.forward, SliceDirection.backward]:
            logger.debug("find_paths starting search %s", dir)
            execute(conn, 'DELETE FROM "vertex_input"')
            executemany(
                conn,
                """INSERT OR IGNORE INTO "vertex_input" (v1, p1) VALUES (?, ?)""",
                vertices,
            )
            vertices_ids = [
                id
                for (id,) in execute(
                    conn,
                    f"""
                    SELECT id FROM "vertex_input"
                    JOIN "flow.ReachableVertex" rv USING (v1, p1)
                    WHERE direction = ?
                    """,
                    (dir.value,),
                )
            ]
            s = SemiNaiveMinPathLength(conn, dir)
            t = s.run(starts=vertices_ids)
            logger.debug("%s graph: %s", dir, pformat(list(t.get_edges())))
            # If we're looking at the forward graph, we do a search from
            # sources to the selected vertices. If we're looking at the
            # backward graph, we do a search from selected vertices to sinks.
            starts = sources if dir.is_forward() else vertices_ids
            goals = sinks if not dir.is_forward() else vertices_ids
            for i in starts:
                for path in t.startpaths(
                    start=i, goals=goals, strategy=PathAvoidStrategy.Both
                ):
                    # Projects the path back onto its vertices
                    logger.debug("%s path: %s", dir, path)
                    # We inline the order of the vertex ids in the path using
                    # sub-selects so that we can find the corresponding
                    # vertices without creating a new temporary table.
                    id_list = " UNION ".join(
                        f"SELECT {i} AS idx, {id} AS id" for i, id in enumerate(path)
                    )
                    path_on_vertices = []
                    for v, p in execute(
                        conn,
                        f"""
                        SELECT v1, p1 FROM "flow.ReachableVertex"
                        JOIN (
                            {id_list}
                        )
                        USING (id)
                        WHERE direction = ?
                        ORDER BY idx
                        """,
                        tuple(dir.value),
                    ):
                        path_on_vertices.append(VertexTy(v, p))
                    logger.debug("path: %s", path_on_vertices)
                    yield path_on_vertices
