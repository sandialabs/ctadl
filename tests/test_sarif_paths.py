import logging
import os
import subprocess
import unittest
from pathlib import Path

from ctadl.vis.model import DB
from ctadl.vis.sarifpaths import find_paths
from ctadl.vis.types import VertexTy

test_path = Path(__file__).parent
import_path = test_path / "import" / "compositional-ctx2"
db_path = import_path / "ctadlir.db"
taintfront_path = Path(__file__).parent.parent / "taint-front"


class TestPaths(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generates test input database
        cmd = [
            "ctadl",
            "import",
            "taint-front",
            str(taintfront_path / "compositional-ctx2.tnt"),
            "-o",
            str(import_path),
            "-f",
        ]
        subprocess.check_call(cmd)
        try:
            os.environ["CTADL_DEFAULT_DIRECTORY"] = str(import_path)

            cmd = ["ctadl", "index", "-f"]
            subprocess.check_call(cmd)
            cmd = [
                "ctadl",
                "query",
                # str(test_path / "test-query.json"),
                "--compute-slices",
                "all",
            ]
            subprocess.check_call(cmd)
        finally:
            del os.environ["CTADL_DEFAULT_DIRECTORY"]

    def test_simple_case(self):
        # First is the source and, due to summaries, connects to the sink in
        # one edge
        with DB(db_path) as conn:
            vertices = [VertexTy("Main/first", "")]
            paths = find_paths(conn, vertices)
            self.assertTrue(
                any(
                    [VertexTy("Main/first", ""), VertexTy("Main/second", "")] == elt
                    for elt in paths
                )
            )

    def test_forward_path(self):
        with DB(db_path) as conn:
            vertices = [VertexTy("Leaf/tmp2", "")]
            paths = find_paths(conn, vertices)
            target = [
                VertexTy("Main/first", ""),
                VertexTy("bar/x", ""),
                VertexTy("bar1/x", ""),
                VertexTy("Leaf/x", ""),
                VertexTy("Leaf/tmp1", ""),
                VertexTy("Leaf/tmp2", ""),
            ]
            self.assertTrue(any(target == path for path in paths))

    def test_backward_path(self):
        with DB(db_path) as conn:
            vertices = [VertexTy("bar1/tmp", "")]
            paths = find_paths(conn, vertices)
            target = [
                VertexTy("bar1/tmp", ""),
                VertexTy("bar1/<ret>", ""),
                VertexTy("bar/tmp", ""),
                VertexTy("bar/<ret>", ""),
                VertexTy("Main/second", ""),
            ]
            self.assertTrue(any(target == path for path in paths))


if __name__ == "__main__":
    logging.basicConfig(filename="tests.log", filemode="a", level=logging.DEBUG)
    unittest.main()
