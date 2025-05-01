"""
Ensures that all the tuples from a given json file are present in an IR database

Example testcase file:

{
  "VirtualAssign": {
    "includes": [{
      "insn": "service/call/2",
      "v1": "service/second",
      "v2": "service/first"
    }],
    "excludes": [{
      "insn": "service/call/3",
      "v1": "service/third",
      "v2": "service/first"
    }]
  }
}
"""

import sys
import json
import sqlite3
import os


def testcase_matches_row(testcase: dict, row):
    all_true = True
    for col, val in testcase.items():
        all_true &= row[col] == val
    return all_true


class TestDatabase:
    def __init__(self, tests):
        self.tests = tests

    def process_row(self, table, row):
        testcases = self.tests[table].get("includes", [])
        if testcases:
            upd = [
                testcase
                for testcase in testcases
                if not testcase_matches_row(testcase, row)
            ]
            self.tests[table]["includes"] = upd

        testcases = self.tests[table].get("excludes", [])
        for testcase in testcases:
            if testcase_matches_row(testcase, row):
                print(f"error: excludes violated on table {table}")
                print(f"exclude entry: {testcase}")
                row_fmt = "\n".join(f"{k}: '{row[k]}'" for k in row.keys())
                print(f"violating row:\n{row_fmt}")
                exit(1)
        self.tests[table]["excludes"] = []

    def check_errors(self) -> bool:
        ok = True
        for table, testcases in self.tests.items():
            if testcases["includes"]:
                print(table, testcases)
                ok = False
        return ok


def main(tests, db):
    tables = tests.keys()
    test_db = TestDatabase(tests)
    # We go through the tables in the database and all the rows and remove
    # matches from the test databes. If at the end the database is empty,
    # success.
    for table in tables:
        rows = db.execute(f"""select * from "{table}" """).fetchall()
        for row in rows:
            test_db.process_row(table, row)

    exit(1 if not test_db.check_errors() else 0)


if __name__ == "__main__":
    json_file = sys.argv[1]
    db_file = "ctadlir.db"
    if len(sys.argv) > 2:
        db_file = sys.argv[2]
    tests = None
    with open(json_file, "r") as fp:
        tests = json.load(fp)
    with sqlite3.connect(db_file) as db:
        db.row_factory = sqlite3.Row
        print(f"testing '{db_file}'")
        main(tests, db)
