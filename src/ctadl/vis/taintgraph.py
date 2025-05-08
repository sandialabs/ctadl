"""
Data structures and algorithms for efficiently exploring the underlying taint graphs
"""

import logging
import sqlite3

try:
    from collections import Sized
except ImportError:
    from collections.abc import Sized

from collections.abc import Collection, Iterable, Iterator
from copy import copy
from enum import Enum
from itertools import chain
from time import time
from typing import NamedTuple, Optional, Union

import ctadl
from ctadl.util.graph import BFS, AdjacencyGraph1, Search

from .model import execute
from .types import SliceDirection, VertexId

logger = logging.getLogger(__name__)


class TaintGraphEdgeInput(NamedTuple):
    src: VertexId
    dst: VertexId


Path = list[VertexId]


class PathAvoidStrategy(Enum):
    Front = 1
    Back = 2
    Both = 3


class TaintGraph(AdjacencyGraph1[VertexId]):
    """Taint graph with no metadata"""

    sources: list[VertexId]
    sinks: list[VertexId]

    def __init__(
        self,
        *,
        direction: SliceDirection,
        edges: Optional[Iterable[TaintGraphEdgeInput]] = None,
    ):
        """Edges are (src, dst)"""
        super().__init__()
        self.direction = direction
        for src, dst in edges or []:
            self.add_edge(src=src, dst=dst)

    def set_root_vertices(self, vs: list[VertexId]):
        self.sources = vs

    def set_goal_vertices(self, vs: list[VertexId]):
        self.sinks = vs

    def startpaths(
        self,
        *,
        start: VertexId,
        goals: list[VertexId],
        strategy: PathAvoidStrategy,
    ) -> list[list[VertexId]]:
        """Returns a list of paths from start to any goal

        Enumerating paths takes some care. For efficiency, we allow users to
        state a strategy for identifying "unique" paths. When a new path is
        found, the algorithm decides on a node that will never be included in
        new paths: either the second node in the path, the second-to-last node,
        or either. The either option starts independent searches, one that
        avoids the second node and another that avoids the second-to-last.
        """

        paths = []
        # Maintains a list of searches and works on them till they're exhausted
        searches = [TaintGraphBFS(self, goals)]
        while searches:
            search = searches.pop()
            search.reset()
            logger.debug(
                "startpaths search for %d goals start: %d avoids: %s goals: %s",
                len(goals),
                start,
                search.avoids,
                goals,
            )
            search.perform_avoidant_search([start])
            if not search.paths:
                logger.debug("search.paths false")
                continue
            logger.debug("search.paths true")
            paths.extend(search.paths)
            if any(len(path) < 2 for path in search.paths):
                continue
            # We want to find new paths besides the ones found in the first pass,
            # and they way we do that is by running the search again, avoiding
            # some nodes from previous paths. We could do this by rerunning the search
            # and avoiding each node in the path one-at-a-time, but for efficiency,
            # we instead only do nodes at the start and end (which usually represent
            # the callsites of sources and sinks respectively) and run those searches
            # separately, to capture paths where only one is different
            if strategy in [PathAvoidStrategy.Front, PathAvoidStrategy.Both]:
                search2 = search.clone()
                search2.add_avoids(path[1] for path in search.paths)
                searches.append(search2)
            if strategy in [PathAvoidStrategy.Back, PathAvoidStrategy.Both]:
                search2 = search.clone()
                search2.add_avoids(path[-2] for path in search.paths)
                searches.append(search2)
        return paths

    def iter_paths_generic_single_source(
        self, source: VertexId, sinks: list[VertexId], strat: PathAvoidStrategy
    ) -> Iterator[list[VertexId]]:
        start = source
        logger.debug("start = %s", start)
        goal_nodes = copy(sinks)
        while goal_nodes:
            paths = self.startpaths(start=start, goals=goal_nodes, strategy=strat)
            if not paths:
                break
            for path in paths:
                logger.debug(
                    "path len %d %s -> %s: %s", len(path), path[0], path[-1], path
                )
                yield path
                found = path[-1]
                if found in goal_nodes:
                    goal_nodes.remove(found)

    def iter_paths(
        self, *, progress=None, taskid, strategy
    ) -> Iterator[list[VertexId]]:
        if progress is None:
            progress = ctadl._empty_progressbar()
        # Attempts to find a path from each start node to each goal node
        progress.update(taskid, total=len(self.sources))
        logger.debug("update task total = %d", len(self.sources))
        if strategy == "both":
            strat_enum = PathAvoidStrategy.Both
        elif strategy == "front":
            strat_enum = PathAvoidStrategy.Front
        else:
            strat_enum = PathAvoidStrategy.Back
        for start in self.sources:
            logger.debug("start = %d", start)
            yield from self.iter_paths_generic_single_source(
                start, self.sinks, strat_enum
            )
            progress.update(taskid, advance=1)


class TaintGraphBFS(BFS[int]):
    """Breadth-first search that stores a static list of goals and mutable list
    of nodes to avoid. Produces a list of paths

    Usage:

        search = TaintGraphBFS(g, goals)
        search.add_avoids([1, 2])
        search.perform_avoidant_search([start1, start2])
        for path in search.paths:
            process_path(path)
    """

    paths: list[list[int]]
    avoids: list[int]

    def __init__(
        self, graph: TaintGraph, goals: list[int], avoids: Optional[list[int]] = None
    ):
        super().__init__()
        self.graph = graph
        self.goals = goals
        self.paths = []
        self.avoids = avoids or []

    def clone(self) -> "TaintGraphBFS":
        """Close this object, copying paths and avoids. Graph and goals are not
        copied, they are referenced"""
        t = TaintGraphBFS(self.graph, self.goals, list(self.avoids))
        t.paths = list(self.paths)
        return t

    def reset(self) -> None:
        """Resets paths and search state"""
        super().reset()
        self.paths.clear()

    def process_preorder(self, node: int) -> bool:
        """Finds goals"""
        if node in self.goals:
            path = Search.make_path(node, self.parent)
            logger.debug("path length %d", len(path))
            self.paths.append(path)
        return True

    def add_avoids(self, elts: Iterable[int]):
        self.avoids.extend(elts)

    # This method should have an obvious name that isn't "perform," so I went
    # with this one.
    def perform_avoidant_search(
        self,
        starts: list[int],
    ) -> None:
        """Performs search with stored list of nodes to avoid"""
        self.perform(self.graph, starts, self.avoids)


def sql_q_list(elts: Union[Sized, int]) -> str:
    """Returns a sequence of question marks, one per element"""
    return ", ".join(["?"] * (elts if isinstance(elts, int) else len(elts)))


class SemiNaiveMinPathLength:
    """
    Loads partial taint graph using a set of start nodes

    Usage:

        s = SemiNaiveMinPathLength(conn, dir)
        t = s.run(starts=vertex_ids)

    To load the edges, we use semi-naive evaluation in a loop managed by the
    host language over a temporary table that holds the results. This tends to
    use less memory than loading the entire graph before doing the search.

    Edges in the graph are in natural (execution) order.
    """

    def __init__(self, conn: sqlite3.Connection, dir: SliceDirection):
        self.con = conn
        self.dir = dir
        self.debug = True

    def _print_table(self):
        cur = self.con.cursor()
        logger.debug(
            "-------------------------------------------------------------------------------------"
        )
        logger.debug(
            "{: >20} {: >20} {: >20} {: >20}".format(
                "node", "next_node", "path_length", "iteration_count"
            )
        )
        for row in execute(
            cur,
            """
            SELECT * from fp
            """,
        ):
            logger.debug(
                "{: >20} {: >20} {: >20} {: >20}".format(row[0], row[1], row[2], row[3])
            )

    def _print_row(self, row):
        print(f"Edge: {row[0]} <- {row[1]}, Minimum Path Length: {row[2]}")

    def _init(self, starts: Collection[VertexId]):
        """Initializes the fixpoint table

        Computes the transitive closure on the graph starting from the given vertices"""
        cur = self.con.cursor()
        execute(
            cur,
            """
            CREATE TEMP TABLE IF NOT EXISTS
                fp (
                    node INTEGER NOT NULL,
                    next_node INTEGER NOT NULL,
                    path_length INTEGER NOT NULL,
                    iteration_count INTEGER NOT NULL,
                    UNIQUE (node, next_node, path_length, iteration_count)
                )
            """,
        )
        execute(
            cur,
            """
            CREATE INDEX IF NOT EXISTS
                temp.idx_fp_node_next_node_length ON fp (node, next_node, path_length)
            """,
        )
        execute(
            cur,
            """
            CREATE INDEX IF NOT EXISTS
                temp.idx_fp_next_node ON fp (next_node)
            """,
        )
        execute(
            cur,
            """
            CREATE INDEX IF NOT EXISTS
                temp.idx_fp_iteration_count ON fp (iteration_count)
            """,
        )
        execute(
            cur,
            """
            CREATE INDEX IF NOT EXISTS
                temp.idx_fp_next_node_iteration_count ON fp (next_node, iteration_count)
            """,
        )
        execute(
            cur,
            """
            CREATE INDEX IF NOT EXISTS
                temp.idx_fp_path_length ON fp (path_length)
            """,
        )
        execute(
            cur,
            """
            DELETE FROM temp.fp;
            """,
        )
        start_list = sql_q_list(starts)
        execute(
            cur,
            f"""
            INSERT OR IGNORE INTO fp (
                node,
                next_node,
                path_length,
                iteration_count
            )
            SELECT e."vertex_from" AS node, e."vertex_to" AS next_node, 1 AS path_length, 0 AS iteration_count
            FROM "reverse_flow.ReachableEdge" e
            WHERE e."vertex_from" IN ({start_list}) AND e.direction = ?
            """,
            tuple(chain(starts, [self.dir.value])),
        )
        self.con.commit()
        if self._count(0) == False:
            logger.debug("seminaive has work to do")

    def _augment(self, n: int):
        # Updates table by finding all edges one step away from those in
        # iteration 'n' which don't have a larger path length that one we've
        # discovered
        q_list = ""  # sql_q_list(self.avoids)
        cur = self.con.cursor()
        execute(
            cur,
            f"""
            INSERT OR IGNORE INTO fp
            SELECT 
                fp.next_node AS node,
                e."vertex_to" AS next_node,
                fp.path_length + 1 AS path_length,
                fp.iteration_count + 1 AS iteration_count
            FROM 
                fp
            JOIN 
                -- picks an edge we should expand
                "reverse_flow.ReachableEdge" e ON fp.next_node = e."vertex_from"
            WHERE
                fp.iteration_count = ?
            AND
                e."vertex_from" NOT IN ({q_list})
            AND
                e.direction = ?
            AND
                NOT EXISTS (
                    -- excludes edges if we know a shorter path
                    SELECT 1
                    FROM fp ifp
                    WHERE
                        e."vertex_from" = ifp.node
                    AND e."vertex_to" = ifp.next_node
                    AND ifp.path_length <= fp.path_length + 1
                )
            """,
            tuple(chain([n], [], [self.dir.value])),
        )
        execute(cur, """PRAGMA optimize""")
        self.con.commit()

    def _count(self, n: int):
        # Returns True of there are no entries at iteration count 'n'
        cur = self.con.cursor()
        for row in execute(
            cur,
            """
            SELECT count(*) FROM fp
            WHERE iteration_count = :count
            """,
            {"count": n},
        ):
            logger.debug("table count: %d", row[0])
            if row[0] == 0:
                return True
        return False

    def run(self, *, starts: Collection[VertexId]) -> TaintGraph:
        """Returns cursor over (src, dst, min_path_length)"""

        # Implementation notes
        # The algorithm is:
        #   init()
        #   while True:
        #    augment()
        #    if no new entries produced by augment:
        #      break
        # select min-length edges

        # init includes any edges from the start set
        # augment adds new edges that represent shorter paths than existing edges

        # To make the code work on forward and backward graphs we need to
        # follow edges in reverse for forward graphs and in natural (execution)
        # order for backward graphs. To accomplish this we use a "reversed"
        # view over both graphs that (1) creates the edge order we need and (2)
        # tags edges with the graph they came from. Then we can use parameter
        # binding for the query and we don't need to interpolate anything.
        # We also could:
        # - Interpolate strings for the table and the src/dst columns, which
        # makes it possible to swap them into the queries. Annoying
        # interpolation
        # - Write different queries for the two cases. The queries are long
        # - Create a "forward" view of the backward graph. Can't believe a
        # never thought of that before. Then we just interpolate the table
        # name.

        start_time = time()
        self._init(starts)
        if self.debug:
            self._print_table()
        n = 0
        total_time = 0.0
        while True:
            new_total_time = time() - start_time
            delta_time = new_total_time - total_time
            total_time = new_total_time
            logger.debug(
                f"total: {total_time:.2f} delta: {delta_time:.2f} iteration {n}"
            )
            self._augment(n)
            if self.debug:
                self._print_table()
            n += 1
            if self._count(n):
                break
        cur = self.con.cursor()
        for row in execute(cur, """SELECT count(*) FROM fp"""):
            logger.debug("SemiNaive table has %d rows", row[0])
            break
        # As we said in impl notes above, we have to traverse the forward
        # graph backward. In that case, to make sure edges are returned in
        # natural order, we flip them before returning.
        edge_iter = (
            TaintGraphEdgeInput(
                **(
                    dict(src=dst, dst=src)
                    if self.dir.is_forward()
                    else dict(src=src, dst=dst)
                )
            )
            for src, dst, _ in execute(
                cur,
                """
            SELECT 
                node AS src,
                next_node AS dst,
                MIN(path_length) AS min_path_length
            FROM 
                fp
            GROUP BY 
                next_node;
            """,
            )
        )
        return TaintGraph(
            direction=self.dir,
            edges=edge_iter,
        )
