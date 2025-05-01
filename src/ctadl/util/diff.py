import difflib
import sqlite3
import sys
from pathlib import Path
from typing import Optional

from ctadl import status, warn

bad_tables = ["CTADLConfig", "CTADLStats"]


def print_difference(
    *,
    ca: int,
    cb: int,
    aconn: sqlite3.Connection,
    bconn: sqlite3.Connection,
    table: str,
    diff_table: Optional[str],
    diff_cols,
):
    rel = "<" if ca < cb else (">" if ca > cb else "=")
    print(table, ":", ca, rel, cb)

    def row_to_str(row):
        return "|".join(map(str, row)) + "\n"

    if table == diff_table:
        a_rows = list(
            sorted(
                row_to_str(row)
                for row in aconn.execute(f'select {diff_cols} from "{table}"')
            )
        )
        b_rows = list(
            sorted(
                row_to_str(row)
                for row in bconn.execute(f'select {diff_cols} from "{table}"')
            )
        )
        sys.stdout.writelines(
            difflib.unified_diff(a_rows, b_rows, fromfile="a", tofile="b")
        )
        exit(1)


def main(
    a: sqlite3.Connection, b: sqlite3.Connection, diff_table: Optional[str], diff_cols
):
    good_tables = []
    exit_code = 0
    for (table,) in a.execute("select name from sqlite_master where type = 'view'"):
        if table in bad_tables or table.startswith("_"):
            continue
        other_table_exists = b.execute(
            "select name from sqlite_master where name = ?1", (table,)
        ).fetchall()
        if not other_table_exists:
            warn(f"{table} doesn't exist in b, skipping")
            continue
        ca = a.execute(f'select count(*) from "{table}"').fetchall()[0][0]
        cb = b.execute(f'select count(*) from "{table}"').fetchall()[0][0]
        if ca != cb:
            print_difference(
                ca=ca,
                cb=cb,
                table=table,
                diff_table=diff_table,
                diff_cols=diff_cols,
                aconn=a,
                bconn=b,
            )
        else:
            good_tables.append(table)
    status(f"good tables: {good_tables}", verb=1)


def diff(a: Path, b: Path, diff_table, diff_cols):
    print(f"a is '{a}'")
    print(f"b is '{b}'")
    with sqlite3.connect(a) as con_a:
        with sqlite3.connect(b) as con_b:
            return main(con_a, con_b, diff_table, diff_cols)


if __name__ == "__main__":
    with sqlite3.connect(sys.argv[1]) as a:
        with sqlite3.connect(sys.argv[2]) as b:
            table = None
            cols = "*"
            try:
                table = sys.argv[3]
            except IndexError:
                pass
            try:
                cols = sys.argv[4]
            except IndexError:
                pass
            main(a, b, table, cols)
