import itertools
import logging
import re
import sqlite3
from functools import cached_property
from typing import Literal

from ctadl import advise, error, progressbar, status, warn

from .sortedcollection import SortedCollection

logger = logging.getLogger(__name__)


view_already_exists = re.compile("view.*already exists", flags=re.IGNORECASE)


class RelationTable:
    """Represents a souffle relation table"""

    def __init__(self, input, schema, sql=None):
        self.input = input
        self.schema = schema
        self.sql = sql

    def _open(self):
        """Returns a context with a connection to the database"""
        return sqlite3.connect(self.input)

    def __iter__(self):
        with self._open() as db:
            yield from db.execute(f'SELECT * FROM "{self.schema}"')

    @cached_property
    def info(self) -> list[tuple[Literal["INTEGER", "TEXT"], str]]:
        with self._open() as db:
            return [
                (ty, name)
                for name, ty in db.execute(
                    f'SELECT name, type FROM pragma_table_info("{self.schema}")'
                )
            ]

    def istext(self, i: int) -> bool:
        return self.info[i][0] == "TEXT"

    @property
    def text_columns(self) -> list[int]:
        return [i for i in range(len(self.info)) if self.istext(i)]

    @property
    def columns_schema(self) -> str:
        return ", ".join(f'"{name}" {ty}' for ty, name in self.info)

    @property
    def relation_schema(self) -> str:
        """Souffle's relation schema uses integers as column names"""
        return ", ".join(f'"{i}" INTEGER' for i, (ty, _) in enumerate(self.info))

    @property
    def unique_schema(self) -> str:
        """Souffle's relation schema uses integers as column names"""
        return ", ".join(f'"{i}"' for i, _ in enumerate(self.info))

    @property
    def values_schema(self) -> str:
        return ", ".join(["?"] * len(self.info))

    def create(self, out: sqlite3.Connection) -> None:
        """Creates in out the _table (that points into __SymbolTable) and the view table"""
        out.execute(
            f'CREATE TABLE IF NOT EXISTS "_{self.schema}" ({self.relation_schema}, UNIQUE({self.unique_schema}))'
        )
        logger.debug("create %s", self.schema)
        self.create_view(out)

    def create_view(self, out: sqlite3.Connection):
        """Creates the view that souffle creates"""
        if not self.sql:
            return
        logger.debug("create_view %s", self.schema)
        # Creates view
        try:
            out.execute(self.sql)
        except sqlite3.OperationalError as e:
            msg = str(e)
            # It'd be nice if it were easier to use be CREATE VIEW
            # IF NOT EXISTS, but souffle emits CREATE VIEW only
            # when it creates the database. We just get around this
            # by catching the error and ensuring it's the error we
            # expect.
            if not view_already_exists.match(msg):
                raise

    def clear(self, out: sqlite3.Connection):
        out.execute(f'DROP TABLE IF EXISTS "_{self.schema}"')


# Omit the stats table because merging it would require combining its
# individual values, otherwise you get dupe'd entries.
_omit_tables = set(["CTADLStats"])


def find_total_work(inputs):
    """Counts the number of views across all the input indexes"""
    total = 0
    for input in inputs:
        with sqlite3.connect(input, detect_types=sqlite3.PARSE_DECLTYPES) as dbi:
            dbi.row_factory = sqlite3.Row
            tables = dbi.execute(
                "select count(*) from sqlite_master where type = 'view'"
            )
            total += next(tables)[0]
    return total


def merge_table_generator(symtab, inputs):
    """Generates all tuples of tables, view names, and sql and maintains symbol
    table"""
    for input in inputs:
        with sqlite3.connect(input, detect_types=sqlite3.PARSE_DECLTYPES) as dbi:
            dbi.row_factory = sqlite3.Row

            # Computes symbol table
            for (symbol,) in dbi.execute("""SELECT symbol FROM __SymbolTable"""):
                symtab.add(symbol)

            tables = dbi.execute(
                "select name, sql from sqlite_master where type = 'view'"
            )
            for name, sql in tables:
                yield dbi, name, sql


def _collect_tables(inputs) -> list[RelationTable]:
    ret = []
    for input in inputs:
        with sqlite3.connect(input, detect_types=sqlite3.PARSE_DECLTYPES) as dbi:
            dbi.row_factory = sqlite3.Row

            ret.extend(
                RelationTable(input, name, sql)
                for name, sql in dbi.execute(
                    "select name, sql from sqlite_master where type = 'view'"
                )
            )
    return ret


def merge_table_by_single_column(mem, table, tmp_name):
    # Updates the text columns to point into new __SymbolTable
    for i in table.text_columns:
        mem.executescript(
            f"""
            UPDATE "{tmp_name}"
            SET "{i}" = "__SymbolTableMap".new_id
            FROM "__SymbolTableMap"
            WHERE "{tmp_name}"."{i}" = "__SymbolTableMap".id;
            """
        )


def merge_table_by_multi_column(mem, table, tmp_name):
    if table.text_columns:
        sets = ", ".join([f'"{i}" = new_id_{i}' for i in table.text_columns])
        select_target = ", ".join(
            [
                f'"symmap_{i}".new_id AS new_id_{i}, "symmap_{i}".id AS id_{i}'
                for i in table.text_columns
            ]
        )
        select_from = ", ".join(
            [f'"__SymbolTableMap" AS "symmap_{i}"' for i in table.text_columns]
        )
        wheres = " AND ".join(
            [f'"{tmp_name}"."{i}" = id_{i}' for i in table.text_columns]
        )
        upd = f"""
            UPDATE "{tmp_name}"
            SET {sets}
            FROM (SELECT {select_target} FROM {select_from})
            WHERE {wheres}
            """
        # print(upd)
        mem.execute(upd)


def merge_indices(output: str, inputs: list[str]) -> None:
    """Merges all input CTADL index files into output"""
    tables = _collect_tables(inputs)
    # Groups tables by input file
    keyfunc = lambda t: t.input
    groups = list(
        (k, list(g)) for k, g in itertools.groupby(sorted(tables, key=keyfunc), keyfunc)
    )

    with progressbar() as progress:
        task = progress.add_task(description="--", total=len(tables))
        # We use an in-memory db as the eventual output to make all the disk
        # writes happen at once.
        with sqlite3.connect(":memory:") as mem:
            mem.executescript(
                """
                CREATE TABLE "__SymbolTable" (id INTEGER PRIMARY KEY UNIQUE, symbol TEXT UNIQUE);
                CREATE TABLE "__SymbolTableMap" (id INTEGER, new_id INTEGER, UNIQUE(id, new_id));
                CREATE INDEX "__SymbolTableSymbolIndex" ON "__SymbolTable" (symbol);
                CREATE INDEX "__SymbolTableMapIdIndex" ON "__SymbolTableMap" (id);
                """
            )
            for input, group in groups:
                # Attaches input database and merges its symbol table. Then creates
                # a map of input ids to our symbol table ids so we can copy over
                # all the relation tables.
                mem.executescript(
                    f"""
                    ATTACH DATABASE '{input}' AS input;
                    -- Adds symbols
                    INSERT OR IGNORE INTO "__SymbolTable" (symbol)
                    SELECT symbol FROM input."__SymbolTable";

                    DELETE FROM "__SymbolTableMap";
                    -- Adds symbols to oldid -> newid __SymbolTableMap
                    INSERT INTO "__SymbolTableMap" (id, new_id)
                    SELECT input."__SymbolTable".id, main."__SymbolTable".id as new_id
                    FROM input."__SymbolTable"
                    JOIN main."__SymbolTable" USING (symbol);
                    """
                )
                for table in group:
                    progress.update(task, advance=1)
                    if table.schema in _omit_tables:
                        continue
                    table.create(mem)
                    tmp_name = f"tmp_{table.schema}"
                    # Note the lack of UNIQUE constraint on this table, even though
                    # all rows must be unique. This is because UPDATE, in
                    # merge_table_by_multi_column, doesn't produces an
                    # atomic/parallel update of all rows. Instead, it updates some
                    # rows before others. This can temporarily violate the
                    # uniqueness constraint, even though at the end the rows will
                    # be unique. Sigh. This took some time to track down. So, we
                    # don't make the temp table unique. We trust that the ultimate
                    # destination for the rows checks uniqueness.
                    mem.execute(
                        f'CREATE TABLE "{tmp_name}" ({table.relation_schema})'
                    )  # UNIQUE(...)
                    mem.execute(
                        f'INSERT INTO "{tmp_name}" SELECT * FROM input."_{table.schema}"'
                    )
                    mem.commit()
                    merge_table_by_multi_column(mem, table, tmp_name)
                    mem.execute(
                        f'INSERT OR IGNORE INTO "_{table.schema}" SELECT * FROM "{tmp_name}"'
                    )
                    mem.execute(f'DROP TABLE "{tmp_name}"')
                    mem.commit()
                # This commit is sometimes necessary for detach
                mem.commit()
                mem.execute("DETACH DATABASE input")
            mem.execute(f'DROP INDEX "__SymbolTableSymbolIndex"')
            mem.execute(f'DROP TABLE "__SymbolTableMap"')
            # This commit is sometimes necessary for the backup
            mem.commit()
            with sqlite3.connect(output) as out:
                mem.backup(out)
