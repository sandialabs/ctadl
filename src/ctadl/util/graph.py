import logging
from collections import defaultdict, deque
from enum import Enum
from typing import Generic, Iterator, Optional, TypeVar

from .functions import Dict

logger = logging.getLogger(__name__)


class Counter:
    def __init__(self, i=0):
        self.reset(i)

    def increment(self) -> int:
        self.value += 1
        return self.value

    def reset(self, i=0):
        self.value = i


NodeTy = TypeVar("NodeTy")


class DfsStack:
    def __init__(self, elts=[]):
        self._stack = [e for e in elts]

    def __bool__(self):
        return bool(self._stack)

    def clear(self):
        self._stack.clear()

    def push(self, elt):
        self._stack.append(elt)

    def pop(self):
        return self._stack.pop()


class BfsQueue:
    def __init__(self, elts=[]):
        self._queue = deque(elts)

    def __bool__(self):
        return bool(self._queue)

    def __len__(self):
        return len(self._queue)

    def clear(self):
        self._queue.clear()

    def push(self, elt):
        self._queue.appendleft(elt)

    def pop(self):
        return self._queue.pop()


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
        logger.debug(f"remove_edge {src} -> {dst}")
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


class VertexState(Enum):
    """Traversal state of a vertex"""

    undiscovered = 1
    discovered = 2
    processed = 3


class EdgeClass(Enum):
    """Classification of edges in a DFS traversal"""

    tree = 1
    back = 2
    forward = 3
    cross = 4


class Search(Generic[NodeTy]):
    @staticmethod
    def make_path(node: Optional[NodeTy], parent: dict[NodeTy, Optional[NodeTy]]):
        """
        Makes a path from an end node and a parent map
        """

        # Reads path out of parent map
        path = []
        while node is not None:
            path.append(node)
            node = parent.get(node)
        return list(reversed(path))

    def process_edge(self, src: NodeTy, dst: NodeTy) -> bool:
        """Returns False if search should not continue"""
        return True

    def process_preorder(self, node: NodeTy) -> bool:
        """Returns False if search should not continue"""
        return True

    def process_postorder(self, node: NodeTy) -> bool:
        """Returns False if search should not continue"""
        return True


class BFS(Search[NodeTy], Generic[NodeTy]):
    """Breadth-first search

    Subclasses should override any of the `process_*` methods
    """

    def __init__(self):
        self.worklist = BfsQueue()
        self.state = defaultdict(lambda: VertexState.undiscovered)
        self.parent: dict[NodeTy, Optional[NodeTy]] = defaultdict(lambda: None)

    def reset(self) -> None:
        self.worklist.clear()
        self.state.clear()
        self.parent.clear()

    def perform(
        self,
        graph: AdjacencyGraph1[NodeTy],
        starts: list[NodeTy],
        avoids: list[NodeTy] = [],
    ) -> None:
        """Performs a BFS from `starts` avoiding `avoids`"""

        for s in starts:
            if s not in avoids:
                self.state[s] = VertexState.discovered
                self.worklist.push(s)
        for a in avoids:
            self.state[a] = VertexState.processed

        while self.worklist:
            u = self.worklist.pop()
            assert self.state[u] == VertexState.discovered
            if not self.process_preorder(u):
                break

            for v in graph.successors(u):
                # We assume the graph is directed which means wy always call
                # process_edge
                if not self.process_edge(u, v):
                    break
                if self.state[v] == VertexState.undiscovered:
                    self.worklist.push(v)
                    self.state[v] = VertexState.discovered
                    self.parent[v] = u

            if not self.process_postorder(u):
                break
            self.state[u] = VertexState.processed


class DFS(Search[NodeTy], Generic[NodeTy]):
    """Depth-first search

    Subclasses should override any of the `process_*` methods
    """

    def __init__(self):
        self.worklist = DfsStack()
        self.state = defaultdict(lambda: VertexState.undiscovered)
        self.parent: dict[NodeTy, Optional[NodeTy]] = defaultdict(lambda: None)
        self.time = Counter()
        self.entry_time = Dict()
        self.exit_time = Dict()

    def classify_edge(self, *, src: NodeTy, dst: NodeTy) -> EdgeClass:
        """Returns the class of an edge

        This method is a function of the search state, so it's only reliable if
        you call it from inside `process_edge`
        """
        if self.parent[dst] == src:
            return EdgeClass.tree
        # Discovered but not processed
        if self.state[dst] == VertexState.discovered:
            return EdgeClass.back
        if (
            self.state[dst] == VertexState.processed
            and self.entry_time[dst] > self.entry_time[src]
        ):
            return EdgeClass.forward
        if (
            self.state[dst] == VertexState.processed
            and self.entry_time[dst] < self.entry_time[src]
        ):
            return EdgeClass.cross
        raise ValueError

    def reset(self):
        self.worklist.clear()
        self.state.clear()
        self.parent.clear()
        self.time.reset()
        self.entry_time.clear()
        self.exit_time.clear()

    def perform(
        self,
        graph: AdjacencyGraph1[NodeTy],
        starts: list[NodeTy],
        avoids: list[NodeTy] = [],
    ):
        """Performs a DFS from `starts` avoiding `avoids`"""

        for s in starts:
            if s not in avoids:
                self.state[s] = VertexState.discovered
                self.worklist.push(s)
        for a in avoids:
            self.state[a] = VertexState.processed

        while self.worklist:
            u = self.worklist.pop()
            assert self.state[u] == VertexState.discovered
            if u not in self.entry_time:
                # Seeing u for the first time
                self.entry_time[u] = self.time.increment()
                if not self.process_preorder(u):
                    break

            u_processed = True
            for v in graph.successors(u):
                # We assume the graph is directed which means wy always call
                # process_edge
                if self.state[v] == VertexState.undiscovered:
                    # u is not fully processed since we found an undiscovered
                    # successor, so push u back onto the queue.
                    self.worklist.push(u)
                    self.worklist.push(v)
                    self.state[v] = VertexState.discovered
                    self.parent[v] = u
                    u_processed = False
                    self.process_edge(u, v)
                    break
                else:
                    self.process_edge(u, v)
            if not u_processed:
                continue

            if not self.process_postorder(u):
                break
            self.exit_time[u] = self.time.increment()
            self.state[u] = VertexState.processed
