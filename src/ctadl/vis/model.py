import contextlib
import inspect
import logging
import os
import shutil
import sqlite3
import time
import typing
from collections import defaultdict
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Generic, Iterable, Iterator, Literal, Optional, Union

from ctadl import status
from ctadl.util.functions import columnize_list

from .types import CtadlModelError

logger = logging.getLogger(__name__)


def get_last_frames(n: int):
    # Get the current frame
    current_frame = inspect.currentframe()
    if current_frame is not None:
        current_frame = current_frame.f_back
    frames = []
    for _ in range(n):
        if current_frame is None:
            break
        frames.append(current_frame)
        current_frame = current_frame.f_back
    return frames


dbstats = defaultdict(float)


def execute(
    cur: Union[sqlite3.Cursor, sqlite3.Connection],
    sql: str,
    parameters=(),
    debug: bool = True,
    n_frames=3,
    explain: bool = False,
):
    """
    Executes a sql statement with logging. Returns a cursor to the results

    Option arguments:
    - debug: If on, prints the function name from the previous frame in the log
      message
    """
    if debug:
        frames = get_last_frames(n_frames)
        logger.debug(
            "%s:%s [params=%s]",
            ":".join(frame.f_code.co_name for frame in frames),
            sql,
            parameters,
        )

    else:
        logger.debug("%s", sql)

    if explain:
        for row in cur.execute(f"EXPLAIN QUERY PLAN {sql}"):
            logger.debug("%s", list(row))

    if debug:
        start_time = time.time()
    res = cur.execute(sql, parameters)
    if debug:
        end_time = time.time()
        global dbstats
        dbstats[sql] += end_time - start_time  # type: ignore
    return res


def executemany(
    cur: Union[sqlite3.Cursor, sqlite3.Connection], sql: str, parameters=()
):
    """Executes a sql statement with logging

    Option arguments:
    - tr: function to translate each row in the result before returning"""

    logger.debug("%s [params=%s]", sql, parameters)
    return cur.executemany(sql, parameters)


def fetchone_or_error(cursor):
    vs = cursor.fetchall()
    if len(vs) == 1:
        return vs[0]
    raise CtadlModelError(f"{len(vs)} results, not one")


@dataclass
class ColumnSpec:
    name: str
    type: str


@dataclass
class TableSpec:
    cols: list[ColumnSpec]
    constraint: str = ""  # must use indices, not column names
    is_set: bool = True  # Adds UNIQUE with all columns in it


class TempTable:
    schema: TableSpec

    def __init__(
        self, db, name: str, schema: TableSpec, tmp=True, drop_on_exit=False, indexes=[]
    ):
        """
        Scope for a temporary SQL table

        table - name of table
        columns - column spec, e.g. ['var TEXT NOT NULL', 'index INTEGER']
        tmp - whether to use the TEMP keyword on creation
        drop_on_exit - whether to drop after on scope exit
        """
        self.db = db
        self.table = name
        self.schema = schema
        self.tmp = tmp
        self.drop_on_exit = drop_on_exit
        self.indexes = indexes

    def __enter__(self):
        return self.create_table()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.drop_on_exit:
            self.drop_table()

    def create_table(self):
        columns_str = ", ".join(f"{c.name} {c.type}" for c in self.schema.cols)
        temp = "TEMP" if self.tmp else ""
        query = f'CREATE {temp} TABLE IF NOT EXISTS "{self.table}" ({columns_str})'
        cur = self.db.cursor()
        execute(cur, query)
        if self.indexes:
            self.create_indexes(cur)
        self.db.commit()
        execute(self.db, f'DELETE FROM "{self.table}"')
        return self.table

    def create_indexes(self, cur):
        if self.indexes:
            for columns in getattr(self, "indexes", []):
                self.create_index(cur, columns)

    def create_index(self, cur, columns):
        column_name_str = "_".join(columns)
        column_str = ", ".join(map(lambda s: '"' + s + '"', columns))
        idx_table_args = []
        idx_table_args.append(f'"idx_{self.table}_{column_name_str}"')
        idx_ref = ".".join(idx_table_args)

        execute(
            cur,
            f"CREATE INDEX IF NOT EXISTS {idx_ref}"
            f' ON "{self.table}" ({column_str})',
        )

    def drop_table(self):
        execute(self.db, f'DROP TABLE "{self.table}"')


def create_indexes(
    conn: Union[sqlite3.Connection, sqlite3.Cursor],
    table: str,
    colspec: list[list[str]],
):
    """
    Creates indexes on a table

    - table: Name of the name, will be quoted
    - colspec: Each member of this list must be a list of column names on which to the create the index

    Does not commit to the database
    """
    for columns in colspec:
        column_name_str = "_".join(columns)
        column_str = ", ".join(map(lambda s: '"' + s + '"', columns))
        idx_table_args = []
        idx_table_args.append(f'"idx_{table}_{column_name_str}"')
        idx_ref = ".".join(idx_table_args)

        execute(
            conn,
            f"""
            CREATE INDEX IF NOT EXISTS {idx_ref}
            ON "{table}" ({column_str})
            """,
        )


def create_ir_indexes(conn: sqlite3.Connection):
    cur = conn.cursor()
    for table, colspec in [
        ("__SymbolTable", [["symbol"]]),
        ("_CFunction_FormalParam", [["0"], ["2"]]),
        ("_CInsn_Move", [["0"], ["1"], ["3"]]),
        ("_CisAlloc", [["0"], ["1"]]),
        ("_CInsn_Use", [["0"]]),
        ("_CCall_VirtualBase", [["0"]]),
        ("_CCall_ActualParam", [["0"]]),
        ("_CVar_InFunction", [["0"], ["1"]]),
        ("_CInsn_InFunction", [["0"], ["1"], ["2"]]),
        ("_IntCInsn_InFunction", [["0"], ["1"], ["2"]]),
        ("_CFunction_Name", [["0"]]),
        ("_CFunction_Arity", [["0"]]),
        ("_CFunction_Signature", [["0"]]),
        ("_CField_Name", [["0"]]),
        ("_CInsn_Call", [["0"]]),
        ("_CVar_Name", [["0"]]),
        ("_CVar_Type", [["0"], ["1"]]),
        ("_CNamespace_Parent", [["0"], ["1"]]),
        ("_CFunction_SourceInfo", [["0", "1"]]),
        ("_CInsn_SourceInfo", [["0", "1"]]),
        ("_CVar_SourceInfo", [["0", "1"]]),
        ("_CSourceInfo_Location", [["0"], ["1"], ["2"]]),
        ("_CSourceInfo_File", [["0"], ["1"]]),
        ("_CFile_UriBaseId", [["0"], ["1"]]),
        ("_CSourceInfo_LineRegion", [["0"], ["1"]]),
        ("_CLineRegion_StartColumn", [["0"]]),
        ("_CLineRegion_EndLine", [["0"]]),
        ("_CLineRegion_EndColumn", [["0"]]),
        ("_CSourceInfo_CharRegion", [["0"]]),
        ("_CCharRegion_Length", [["0"]]),
        ("_CSourceInfo_ByteRegion", [["0"]]),
        ("_CByteRegion_Length", [["0"]]),
        ("_CSourceInfo_Address", [["0"]]),
        ("_CAddress_AbsoluteAddress", [["0"]]),
        ("_CAddress_RelativeAddress", [["0"]]),
        ("_CAddress_OffsetFromParent", [["0"]]),
        ("_CAddress_Length", [["0"]]),
        ("_CAddress_Name", [["0"]]),
        ("_CAddress_FullyQualifiedName", [["0"]]),
        ("_CAddress_Kind", [["0"]]),
        ("_CAddress_Parent", [["0"]]),
        ("_Vertex", [["0"], ["1"]]),
        ("_VirtualAssign", [["0", "1"], ["0", "3"]]),
        ("_CallEdge", [["0"], ["1"]]),
        ("_SummaryFlow", [["0"], ["3"]]),
        ("_VirtualAlloc", [["0", "1"]]),
        ("_SummaryAlloc", [["0"]]),
    ]:
        create_indexes(cur, table, colspec)
    conn.commit()


def create_taint_views(db: sqlite3.Connection):
    """Creates views that are used elsewhere by CTADL analysis

    flow.ReachableVertex: A table with the same schema as ReachableVertex
    but a new column at the end, direction, which contains either 'f' or 'b'
    depending on whether the vertex is reachable forward or backward,
    respectively.

    natural_flow.ReachableEdge: Same schema as ReachableEdge, and it has a
    direction column as above, but *all* edges are in natural (execution)
    order.

    reverse_flow.ReachableEdge: The edges of the forward and backward graph in
    reversed (opposite of execution) order.
    """
    execute(
        db,
        """
        CREATE VIEW IF NOT EXISTS "flow.ReachableVertex" AS
        SELECT
            *,
            'f' AS direction
        FROM "forward_flow.ReachableVertex"
        UNION
        SELECT
            *,
            'b' as direction
        FROM "backward_flow.ReachableVertex"
        """,
    )
    execute(
        db,
        """
        CREATE VIEW IF NOT EXISTS "_flow.ReachableVertex" AS
        SELECT
            *,
            'f' AS direction
        FROM "_forward_flow.ReachableVertex"
        UNION
        SELECT
            *,
            'b' as direction
        FROM "_backward_flow.ReachableVertex"
        """,
    )
    execute(
        db,
        """
        CREATE VIEW IF NOT EXISTS "_flow.ReachableEdge" AS
        SELECT
            *,
            'f' AS direction
        FROM "_forward_flow.ReachableEdge"
        UNION
        SELECT
            *,
            'b' as direction
        FROM "_backward_flow.ReachableEdge"
        """,
    )
    execute(
        db,
        """
        CREATE VIEW IF NOT EXISTS "natural_flow.ReachableEdge" AS
        SELECT
            *,
            'f' AS direction
        FROM "forward_flow.ReachableEdge"
        UNION
        SELECT
            vertex_from AS vertex_to,
            vertex_to AS vertex_from,
            insn,
            kind,
            'b' as direction
        FROM "backward_flow.ReachableEdge"
        """,
    )
    execute(
        db,
        """
        CREATE VIEW IF NOT EXISTS "reverse_flow.ReachableEdge" AS
        SELECT
            vertex_from AS vertex_to,
            vertex_to AS vertex_from,
            insn,
            kind,
            'f' AS direction
        FROM "forward_flow.ReachableEdge"
        UNION
        SELECT
            vertex_from AS vertex_to,
            vertex_to AS vertex_from,
            insn,
            kind,
            'b' as direction
        FROM "backward_flow.ReachableEdge"
        """,
    )
    db.commit()


def create_taint_indexes(conn: sqlite3.Connection):
    """Creates indexes on the taint database tables. This is critical to the
    performance of extracting taint results"""
    cur = conn.cursor()
    for table, colspec in [
        ("_forward_flow.ReachableVertex", [["0"], ["1"]]),
        ("_backward_flow.ReachableVertex", [["0"], ["1"]]),
        ("_forward_flow.ReachableEdge", [["0"], ["1"], ["2"]]),
        ("_backward_flow.ReachableEdge", [["0"], ["1"], ["2"]]),
        ("_TaintSourceVertex", [["0"], ["1", "2"]]),
        ("_LeakingSinkVertex", [["0"], ["1", "2"]]),
        ("_TaintSanitizeVertex", [["0"], ["1", "2"]]),
        ("_TaintSanitizeEdge", [["0"], ["1", "2"], ["3", "4"]]),
    ]:
        create_indexes(cur, table, colspec)
    conn.commit()


class DB:
    def __init__(self, path, optimize_on_close=True):
        self.path = path
        self.db = None
        self.optimize_on_close = optimize_on_close

    def __enter__(self):
        self.db = sqlite3.connect(self.path, detect_types=sqlite3.PARSE_DECLTYPES)
        self.db.row_factory = sqlite3.Row
        return self.db

    def __exit__(self, exc_type, exc_value, traceback):
        if self.db is not None:
            if self.optimize_on_close:
                self.db.execute(f"PRAGMA optimize")
            self.db.close()


RecordTy = typing.TypeVar("RecordTy")


# schema
# CREATE TABLE IF NOT EXISTS '__SymbolTable' (id INTEGER PRIMARY KEY, symbol TEXT UNIQUE);
class SymbolTableView(Generic[RecordTy]):
    """
    An interface to Souffle's symbol table
    """

    symtab = "__SymbolTable"
    table: Optional[str] = None
    tablespec: Optional[TableSpec] = None

    def __init__(
        self,
        db,
        table: Optional[str] = None,
        tablespec: Optional[TableSpec] = None,
        create_indexes=False,
    ):
        self.db = db
        self.__pre_init__(db)
        if create_indexes:
            self.create_indexes()
        self.__post_init__(db)

    def __pre_init__(self, db):  # type: ignore
        pass

    def __post_init__(self, db):  # type: ignore
        pass

    @cache
    def __len__(self):
        ret = execute(self.db, f'SELECT count(*) FROM "{self.table}"').fetchall()
        return int(ret[0][0])

    def __iter__(self) -> Iterator[RecordTy]:
        cur = self.db.cursor()
        return (
            self.from_row(row) for row in execute(cur, f'SELECT * FROM "{self.table}"')
        )

    def __str__(self) -> str:
        assert self.table
        return self.table

    def get_backing_column_index(self, column: str) -> int:
        if not self.tablespec:
            raise ValueError("no table spec")
        for i, colspec in enumerate(self.tablespec.cols):
            if colspec.name == column:
                return i
        raise ValueError("no column named: " + column)

    def get_backing_column(self, column: str) -> str:
        if not self.tablespec:
            raise ValueError("no table spec")
        for i, colspec in enumerate(self.tablespec.cols):
            if colspec.name == column:
                return f'"_{self.table}"."{i}"'
        raise ValueError("no column named: " + column)

    def create_backing_table(self, numcols: int, is_set: bool, constraint: str):
        if not self.table:
            raise ValueError("no table name")
        colspec = ", ".join(f""" "{i}" INTEGER NOT NULL """ for i in range(numcols))
        if is_set:
            colspec += ", UNIQUE(" + ", ".join(f'"{i}"' for i in range(numcols)) + ")"
        if constraint:
            colspec += "," + constraint
        execute(
            self.db,
            f""" CREATE TABLE IF NOT EXISTS '_{self.table}' ({colspec})""",
        )

    def create_table(self):
        """Creates backing table and view. Requires tablespec with constraint
        on numbered columns"""
        if not self.table:
            raise ValueError("no table name")
        if not self.tablespec:
            raise ValueError("no table spec")
        spec = self.tablespec
        self.create_backing_table(len(spec.cols), spec.is_set, spec.constraint)
        execute(
            self.db,
            f""" CREATE VIEW IF NOT EXISTS '{self.table}' AS SELECT """
            + ",".join(
                f""" '_symtab_{i}'.symbol AS '{col.name}' """
                for i, col in enumerate(spec.cols)
            )
            + f""" FROM '_{self.table}', """
            + ",".join(
                f""" '{self.symtab}' AS '_symtab_{i}' """ for i in range(len(spec.cols))
            )
            + f""" WHERE """
            + " AND ".join(
                f""" '_{self.table}'.'{i}' = '_symtab_{i}'.id """
                for i in range(len(spec.cols))
            ),
        )
        # CREATE VIEW 'CInsn_InFunction' AS SELECT '_symtab_0'.symbol AS 'insn','_CInsn_InFunction'.'1' AS 'index','_symtab_2'.symbol AS 'function' FROM '_CInsn_InFunction','__SymbolTable' AS '_symtab_0','__SymbolTable' AS '_symtab_2' WHERE '_CInsn_InFunction'.'0' = '_symtab_0'.id AND '_CInsn_InFunction'.'2' = '_symtab_2'.id |

    def iter_join(self, joinsql, selector="*") -> Iterator[RecordTy]:
        for x in execute(
            self.db, f"""SELECT {selector} from "{self.table}" {joinsql}"""
        ):
            yield self.from_row(x)

    def iter_where(self, sql, parameters=(), selector="*") -> Iterator[RecordTy]:
        for x in execute(
            self.db, f"""SELECT {selector} FROM "{self.table}" {sql}""", parameters
        ):
            yield self.from_row(x)

    def exists(self) -> bool:
        """Whether the table exists"""
        result = execute(
            self.db,
            "SELECT name FROM sqlite_master"
            f" WHERE (type='view' OR type='table') AND name='{self.table}'",
        ).fetchall()
        return bool(result)

    def from_row(self, row):
        return row

    def create_indexes(self):
        if self.exists():
            cur = self.db.cursor()
            for columns in getattr(self, "indexes", []):
                self.create_index(cur, columns)
            self.db.commit()

    def create_index(self, cur, columns):
        column_name_str = "_".join(columns)
        column_str = ", ".join(map(lambda s: '"' + s + '"', columns))
        idx_table_args = []
        idx_table_args.append(f'"idx_{self.table}_{column_name_str}"')
        idx_ref = ".".join(idx_table_args)

        execute(
            cur,
            f"CREATE INDEX IF NOT EXISTS {idx_ref}"
            f' ON "_{self.table}" ({column_str})',
        )

    def id(self, symbol):
        ret = fetchone_or_error(
            execute(
                self.db,
                f"SELECT id FROM {SymbolTableView.symtab} WHERE symbol = ?",
                (symbol,),
            )
        )
        return ret[0]

    def insert_symbols(self, symbols: Iterable[str], commit=True):
        executemany(
            self.db,
            f'INSERT OR IGNORE INTO "{SymbolTableView.symtab}" (symbol) VALUES (?)',
            [(symbol,) for symbol in symbols],
        )
        if commit:
            self.db.commit()

    def insert_backing_row(self, cols: tuple[int, ...], commit=True):
        """Inserts a row into the backing table of pointers into the symbol table"""
        valuespec = ", ".join(["?"] * len(cols))
        execute(
            self.db,
            f'INSERT OR IGNORE INTO "_{self.table}" VALUES ({valuespec})',
            cols,
        )
        if commit:
            self.db.commit()

    def symbol_id(self, symbol: str) -> int:
        """Retrieves the unique ID of an existing symbol"""
        ret = fetchone_or_error(
            execute(
                self.db,
                f"SELECT id FROM {SymbolTableView.symtab} WHERE symbol = ?",
                (symbol,),
            )
        )
        return ret[0]


class CTADLConfig:
    """Interface to the CTADL configuration stored in the database

    config[feature] returns the value associated with the feature, if it
    exists, and throws a CtadlModelError otherwise

    config[feature] = value sets the config value, creating the feature if it
    doesn't exist

    feature in config tests whether feature exists
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.tab = SymbolTableView(conn, "CTADLConfig")

    def __getitem__(self, feature: str):
        return fetchone_or_error(
            execute(
                self.conn,
                f'SELECT value from "CTADLConfig" WHERE feature = ?',
                (feature,),
            )
        )[0]

    def __delitem__(self, feature: str):
        key_id = self.tab.symbol_id(feature)
        execute(self.conn, f'DELETE FROM "_CTADLConfig" WHERE "0" = ?', (key_id,))

    def __setitem__(self, feature: str, value: str):
        self.tab.insert_symbols([feature, value])
        feature_id, value_id = self.tab.symbol_id(feature), self.tab.symbol_id(value)
        if feature in self:
            execute(
                self.conn,
                """
                    UPDATE OR IGNORE "_CTADLConfig"
                    SET "1" = :value
                    WHERE "0" = :feature
                    """,
                dict(feature=feature_id, value=value_id),
            )
        else:
            execute(
                self.conn,
                """ INSERT INTO "_CTADLConfig" ("0", "1") VALUES (?, ?) """,
                (feature_id, value_id),
            )
        self.conn.commit()

    def __contains__(self, feature):
        results = execute(
            self.conn,
            f'SELECT value from "CTADLConfig" WHERE feature = ?',
            (feature,),
        ).fetchall()
        return len(results) > 0

    def is_feature_enabled(self, feature) -> bool:
        return bool(int(self[feature]))

    @property
    def language(self) -> str:
        return self["CTADL_ANALYSIS_LANG"]


class Facts:
    """Interface to a facts dir or sqlite database

    This interface allows creating new input relations and writing to them. The
    relations are created like souffle expects them, where a shadow _REL
    relation is created to store indices into __SymbolTable and the REL
    relation is a VIEW that retrieves those strings.

    f = Facts(dir | sqlite_db)
    f.add_input_relation("myrelation", ...)
    with f.writer() as w:
        f.write(w, "myrelation", VAL1, VAL2)
    """

    path: Path
    ty: Literal["dir", "sqlite"]

    def __init__(self, path: typing.Union[str, Path]):
        self.path = path if isinstance(path, Path) else Path(path)
        self.ty = "dir" if self.path.is_dir() else "sqlite"
        # The writer that we return for a facts directory is a map of writers
        # to each individual file. To be able to do that, we need to remember
        # the set of relation names.
        self.exitstack = contextlib.ExitStack()
        self.relations = set()

    @property
    def is_fact_dir(self) -> bool:
        return self.ty == "dir"

    @property
    def is_sqlite_db(self) -> bool:
        return self.ty == "sqlite"

    def _initialize_relation(self, name: str, cols: list[ColumnSpec]) -> None:
        """Initializes a relation with the given columns.

        When using a fact directory, we just make sure the file is writable.
        When using sqlite, we create a shadow table to store the relation data
        and a view into the table, like souffle does
        """
        if self.is_fact_dir:
            with self._open_facts_dir_relation(name, mode="w"):
                pass
            return
        assert self.is_sqlite_db
        with sqlite3.connect(self.path) as conn:
            conn.execute(f'DROP VIEW IF EXISTS "{name}"')
            conn.execute(f'DROP TABLE IF EXISTS "_{name}"')
            conn.commit()
            symtab_schema = ", ".join(
                f'"{i}" INTEGER NOT NULL' for i, _ in enumerate(cols)
            )
            unique_schema = ", ".join(f'"{i}"' for i in range(len(cols)))
            relation_schema = ", ".join(f'"{col.name}" {col.type}' for col in cols)
            execute(
                conn,
                f'CREATE TABLE IF NOT EXISTS "_{name}" ({symtab_schema}, UNIQUE({unique_schema}))',
            )
            selectcols = ",".join(
                (
                    f'"_symtab_{i}".symbol'
                    if col.type.startswith("TEXT")
                    else f'"_{name}"."{i}"'
                )
                + f' AS "{col.name}"'
                for i, col in enumerate(cols)
            )
            fromcols = f'"_{name}",' + ",".join(
                f'"__SymbolTable" AS "_symtab_{i}"'
                for i, col in enumerate(cols)
                if col.type.startswith("TEXT")
            )
            wherecols = " AND ".join(
                f'"_{name}"."{i}" = "_symtab_{i}".id'
                for i, col in enumerate(cols)
                if col.type.startswith("TEXT")
            )
            execute(
                conn,
                f"""
                CREATE VIEW IF NOT EXISTS "{name}" AS
                SELECT
                    {selectcols}
                FROM {fromcols}
                WHERE {wherecols}
                """,
            )
            conn.commit()

    def _open_facts_dir_relation(self, name: str, mode="a", **kwargs):
        return open(
            os.path.join(self.path, name + ".facts"), mode, **kwargs
        )  # , buffering=50000)

    def add_input_relation(self, name: str, cols: list[ColumnSpec]) -> str:
        self.relations.add(name)
        self._initialize_relation(name, cols)
        return name

    @contextlib.contextmanager
    def writer(self):
        fps = {}
        if self.is_fact_dir:
            fps = {name: self._open_facts_dir_relation(name) for name in self.relations}
        try:
            yield fps
        finally:
            for fp in fps.values():
                fp.close()

    def write(self, writers, name: str, *cols: typing.Union[str, int]) -> None:
        """Writes a fact to the named relation

        The 'writer' argument is returned by using the context manager 'self.writer'"""
        if self.is_fact_dir:
            print(
                *cols,
                sep="\t",
                file=writers[name],
            )
        else:
            with sqlite3.connect(self.path) as db:
                db.executemany(
                    f'INSERT OR IGNORE INTO "__SymbolTable" ("symbol") VALUES (?)',
                    list((col,) for col in list(cols) if isinstance(col, str)),
                )
                db.commit()
                wherespec = " OR ".join(
                    f"symbol = '{col}'" for col in list(cols) if isinstance(col, str)
                )
                symbolid = {
                    row[1]: row[0]
                    for row in db.execute(
                        f'SELECT id, symbol FROM "__SymbolTable" WHERE {wherespec}'
                    ).fetchall()
                }
                valuespec = ", ".join(["?"] * len(cols))
                db.execute(
                    f'INSERT INTO "_{name}" VALUES ({valuespec})',
                    tuple(
                        (symbolid[col] if isinstance(col, str) else col)
                        for col in list(cols)
                    ),
                )
                db.commit()


def create_tainted_arg_unresolved(
    conn: sqlite3.Connection,
):
    """
    Computes a table of instruction arguments that are tainted and reach unresolved calls
    """

    # XXX this creates and deletes the view; you have to persist it without
    # using TempTable, probably

    table = "TaintedArgUnresolved"

    # view must be temporary since it crosses databases
    with TempTable(
        conn,
        "tmp_unresolved_actuals",
        TableSpec(
            cols=[
                ColumnSpec(name="insn", type="TEXT NOT NULL"),
                ColumnSpec(name="v1", type="TEXT NOT NULL"),
                ColumnSpec(name="p1", type="TEXT NOT NULL"),
            ]
        ),
    ):
        # Makes a table of the actuals of unresolved calls
        execute(
            conn,
            f"""
            insert into tmp_unresolved_actuals
            select distinct insn, param, ap from CCall_ActualParam
            where insn not in (select insn from `CInsn_Call`)""",
        )
        cmd = f"""
            CREATE TEMP VIEW IF NOT EXISTS TaintedArgUnresolved AS
            SELECT 'f' AS direction, insn FROM "tmp_unresolved_actuals"
            JOIN "forward_flow.ReachableVertex" USING (v1, p1) WHERE ((v1, p1) NOT IN (SELECT v,p FROM "TaintSourceVertex"))
                UNION ALL
            SELECT 'b' AS direction, insn FROM "tmp_unresolved_actuals"
            JOIN "backward_flow.ReachableVertex" USING (v1, p1) WHERE ((v1, p1) NOT IN (SELECT v,p FROM "LeakingSinkVertex"))
            """
        execute(conn, cmd)
        conn.commit()


def print_stats(db):
    displaywidth, displaylines = shutil.get_terminal_size((1, 24))

    def stats(key):
        return next(
            execute(db, f""" SELECT n FROM CTADLStats WHERE stat_name = ? """, (key,))
        )[0]

    categories = dict(
        code=[
            "CisFunction",
            "analyzed-function",
            "CInsn_Move",
            "CInsn_Use",
            "CInsn_Call",
            "CVar_InFunction",
            "CVar_isGlobal",
        ],
        analysis=[
            "CisAccessPath",
            "computed-access-path",
            "star-access-path",
            "virtual-assign",
            "vertex",
            "LocallyReachable",
            "AliasRep",
            "GlobalReachable",
        ],
    )
    num_call = db.execute(f"SELECT COUNT(DISTINCT insn) FROM CInsn_Call").fetchall()[0][
        0
    ]
    num_call_edges = db.execute(f"SELECT COUNT(*) FROM CInsn_Call").fetchall()[0][0]
    num_move = db.execute(f"SELECT COUNT(DISTINCT insn) FROM CInsn_Move").fetchall()[0][
        0
    ]
    num_functions_summarized = db.execute(
        f"SELECT COUNT(DISTINCT m1) FROM SummaryFlow WHERE m2=m1;"
    ).fetchall()[0][0]
    num_summaries = db.execute(
        f"SELECT COUNT(*) FROM SummaryFlow WHERE m2=m1;"
    ).fetchall()[0][0]
    num_summaries_type2 = db.execute(
        f"SELECT COUNT(*) FROM SummaryFlow WHERE m2!=m1;"
    ).fetchall()[0][0]
    lines = [
        f"""{stats("CisFunction")} functions""",
        # f"""{num_move+num_call} instructions = {num_call} calls & {num_move} assignments""",
        f"""{num_move+num_call} instructions""",
        f"""{num_call} calls""",
        f"""{num_move} assignments""",
        f"""{stats('initial-vertex')} initial vertices""",
        # f"""{stats['CVar_InFunction']} local vars, {stats['CVar_isGlobal']} global vars""",
        f"""{stats('CVar_InFunction')} local vars""",
        f"""{stats('CVar_isGlobal')} global vars""",
        # f"""{stats('CisAccessPath')} access paths, {stats['star-access-path']} star APs""",
        f"""{stats('CisAccessPath')} original access paths""",
        f"""{stats('computed-access-path')} computed access paths""",
        f"""{stats('star-access-path')} star APs""",
        # f"""{stats['virtual-assign']} (+{va_increase}%) virtual assignments, {stats['vertex']} vertices""",
        f"""{stats('virtual-assign')} virtual assignments""",
        f"""{stats('vertex')} vertices""",
        # f"""{stats['LocallyReachableSources']} locally-reachable source vertices, {stats['LocallyReachable']} lr entries""",
        f"""{stats('LocallyReachableSources')} local flow source vertices""",
        f"""{stats('LocallyReachable')} local flow entries""",
        f"""{stats('alias-sets')} alias sets""",
        f"""{stats('alias-entries')} alias entries""",
        f"""{num_functions_summarized} functions summarized""",
        f"""{num_summaries} function summary entries""",
        f"""{num_summaries_type2} type-2 function summary entries""",
        f"""{num_call_edges} call edges""",
        f"""{stats('CisAlloc')} tracked objects (allocs)""",
        f"""{stats('virtual-alloc')} virtual allocs""",
        f"""{stats('ParthianVertex')} Parthian vertices""",
        f"""{stats('ParthianFlowEdge')} Parthian edges""",
        f"""{stats('ctx')} contexts""",
        f"""{stats('obj-ctx')} objects (ctx)""",
        f"""{stats('LocallyReachable-ctx')} local flow entries (ctx)""",
        f"""{stats('virtual-assign-ctx')} virtual assignments (ctx)""",
        f"""{stats('virtual-alloc-ctx')} virtual allocs (ctx)""",
        f"""{stats('summary-flow-ctx')} function summary entries (ctx)""",
    ]
    status("stats")
    print("\n".join(columnize_list(lines, displaywidth=displaywidth)))

    def getincrease(initial, computed):
        ratio = 0.0 if computed == 0 else (float(initial) / float(computed))
        return round(1.0 - ratio, 2)

    vx_increase = getincrease(stats("initial-vertex"), stats("vertex"))
    va_increase = getincrease(num_call + num_move, stats("virtual-assign"))
    ap_increase = getincrease(stats("CisAccessPath"), stats("computed-access-path"))
    lines = [
        f"""{va_increase}x increased virtual-assign instructions""",
        f"""{vx_increase}x increased vertices""",
        f"""{ap_increase}x increased computed access paths""",
    ]
    status("delta")
    print("\n".join(columnize_list(lines, displaywidth=displaywidth)))
