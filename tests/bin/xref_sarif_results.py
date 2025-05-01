#!/usr/bin/env python3

import json
from collections import defaultdict
from typing import Generic, TypeVar, Iterator

"""Finds instruction results C0002 that aren't in any graph"""

NodeTy = TypeVar("NodeTy")


class AdjacencyGraph1(Generic[NodeTy]):
    """
    Graph with an adjacency list representation. Keeps successors only
    """

    def __init__(self):
        self._successors: defaultdict[NodeTy, set[NodeTy]] = defaultdict(set)

    def add_node(self, node: NodeTy) -> NodeTy:
        self._successors[node]
        return node

    def add_edge(self, *, src: NodeTy, dst: NodeTy) -> None:
        """
        Adds an edge from src to dst to the graph.
        """

        self._successors[src].add(dst)
        self._successors[dst]

    def remove_edge(self, *, src: NodeTy, dst: NodeTy) -> None:
        self._successors[src].remove(dst)
        if not self._successors[src]:
            del self._successors[src]

    def get_nodes(self) -> Iterator[NodeTy]:
        return iter(self._successors)

    def get_edges(self) -> Iterator[tuple[NodeTy, NodeTy]]:
        for node, succs in self._successors.items():
            for succ in succs:
                yield (node, succ)

    def num_nodes(self):
        return len(self._successors)

    def num_edges(self):
        return sum(len(succs) for succs in self._successors.values())

    def freeze(self) -> None:
        self._successors.default_factory = None  # freeze

    def successors(self, node: NodeTy) -> set[NodeTy]:
        return self._successors.get(node, set())


class LogicalLocations:
    def __init__(self, loglocs):
        self.loglocs = loglocs

    def lookup(self, logloc_ref):
        try:
            i = logloc_ref["index"]
            assert i < len(self.loglocs)
            ll = self.loglocs[i]
        except IndexError:
            ll = logloc_ref
        return ll


class SarifGraph(AdjacencyGraph1[int]):
    def __init__(self, json):
        super().__init__()
        for node in json.get("nodes", []):
            self.add_node(int(node["id"]))
        self.edge_labels = set()
        for edge in json.get("edges", []):
            self.add_edge(src=int(edge["sourceNodeId"]), dst=int(edge["targetNodeId"]))
            try:
                label = edge["label"]["text"]
                self.edge_labels.add(label)
            except IndexError:
                pass

    def contains_edge_label(self, label):
        return label in self.edge_labels


def ensure_taint_results_in_graph(run) -> bool:
    res = False  # no errors
    loglocs = LogicalLocations(run.get("logicalLocations", []))
    insn_results = [
        result for result in run.get("results", []) if result.get("ruleId") == "C0002"
    ]
    graphs = [SarifGraph(g) for g in run.get("graphs", [])]

    for result in insn_results:
        for location in result.get("locations", []):
            for logloc_ref in location.get("logicalLocations", []):
                logloc = loglocs.lookup(logloc_ref)
                try:
                    insn_name = logloc["fullyQualifiedName"]
                    if not any(
                        graph.contains_edge_label(insn_name) for graph in graphs
                    ):
                        res = True
                        print(insn_name)
                except IndexError:
                    pass
    return res


def main(argv):
    res = False  # no errors
    filepath = argv[1]

    with open(filepath, "r") as file:
        log = json.loads(file.read())

    for run in log.get("runs", []):
        res |= ensure_taint_results_in_graph(run)
    exit(int(res))


if __name__ == "__main__":
    import sys

    main(sys.argv)
