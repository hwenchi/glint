"""The effects a SELECT may have besides computing its result.

A query has the effects of all its parts. They come from the parsed query alone:
each name is taken as the built-in it names, and each relation as data it reads.
"""

from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum, auto

from pglast import ast
from pglast.enums import LockWaitPolicy, SQLValueFunctionOp

from glint.postgres.tree import walk


class Effect(StrEnum):
    """Reading or writing a resource. The clock can only be read."""

    READS_DATA = auto()  # reads tables, views, sequences or large objects
    WRITES_DATA = auto()  # writes tables, sequences or large objects
    READS_CATALOG = auto()  # reads schema definitions
    WRITES_CATALOG = auto()  # writes schema definitions
    READS_SESSION = auto()  # reads the connection's settings or state
    WRITES_SESSION = auto()  # changes the connection's settings or state
    READS_SERVER = auto()  # reads server configuration, statistics or activity
    WRITES_SERVER = auto()  # changes server configuration, statistics or logs
    READS_PROCESSES = auto()  # reads the state of other server processes
    WRITES_PROCESSES = auto()  # signals or notifies other server processes
    READS_LOCKS = auto()  # reads which locks are held
    WRITES_LOCKS = auto()  # takes or releases locks explicitly
    READS_FILES = auto()  # reads files on the server
    WRITES_FILES = auto()  # writes files on the server
    READS_NETWORK = auto()  # reads from other servers
    WRITES_NETWORK = auto()  # writes to other servers
    READS_CLOCK = auto()  # reads the current time
    OPAQUE = auto()  # runs code outside pg_catalog
    UNCLASSIFIED = auto()  # uses a name with no classification yet


NONE: frozenset[Effect] = frozenset()

# Built-in functions by name, with the effects of all their overloads combined.
FUNCTION_EFFECTS: dict[str, frozenset[Effect]] = {
    # Aggregates compute from their input rows.
    "count": NONE,
    "sum": NONE,
    "avg": NONE,
    "min": NONE,
    "max": NONE,
    "stddev": NONE,
    "stddev_samp": NONE,
    "stddev_pop": NONE,
    "variance": NONE,
    "var_samp": NONE,
    "var_pop": NONE,
    "corr": NONE,
    "covar_pop": NONE,
    "covar_samp": NONE,
    "regr_slope": NONE,
    "regr_intercept": NONE,
    "regr_r2": NONE,
    "regr_count": NONE,
    "regr_avgx": NONE,
    "regr_avgy": NONE,
    "regr_sxx": NONE,
    "regr_syy": NONE,
    "regr_sxy": NONE,
    "percentile_cont": NONE,
    "percentile_disc": NONE,
    "mode": NONE,
    "bool_and": NONE,
    "bool_or": NONE,
    "every": NONE,
    "array_agg": NONE,
    "string_agg": NONE,
    "json_agg": NONE,
    "jsonb_agg": NONE,
    # Window functions compute from the rows of their window.
    "row_number": NONE,
    "rank": NONE,
    "dense_rank": NONE,
    "percent_rank": NONE,
    "cume_dist": NONE,
    "ntile": NONE,
    "lag": NONE,
    "lead": NONE,
    "first_value": NONE,
    "last_value": NONE,
    "nth_value": NONE,
    # Math computes from its arguments alone. Numeric results are capped at 131072 digits.
    "abs": NONE,
    "ceil": NONE,
    "ceiling": NONE,
    "floor": NONE,
    "round": NONE,
    "trunc": NONE,
    "sign": NONE,
    "div": NONE,
    "mod": NONE,
    "sqrt": NONE,
    "cbrt": NONE,
    "exp": NONE,
    "ln": NONE,
    "log": NONE,
    "log10": NONE,
    "power": NONE,
    "pi": NONE,
    "degrees": NONE,
    "radians": NONE,
    "sin": NONE,
    "cos": NONE,
    "tan": NONE,
    "asin": NONE,
    "acos": NONE,
    "atan": NONE,
    "atan2": NONE,
    "width_bucket": NONE,
    # String functions compute from their arguments alone.
    "lower": NONE,
    "upper": NONE,
    "initcap": NONE,
    "length": NONE,
    "char_length": NONE,
    "octet_length": NONE,
    "substr": NONE,
    "substring": NONE,
    "btrim": NONE,
    "ltrim": NONE,
    "rtrim": NONE,
    "left": NONE,
    "right": NONE,
    "replace": NONE,
    "split_part": NONE,
    "concat": NONE,
    "concat_ws": NONE,
    "position": NONE,
    "strpos": NONE,
    "starts_with": NONE,
    "repeat": NONE,
    "lpad": NONE,
    "rpad": NONE,
    "regexp_replace": NONE,
    "regexp_match": NONE,
    "regexp_like": NONE,
    # These date and time functions compute from their arguments alone.
    "make_date": NONE,
    "make_time": NONE,
    "make_timestamp": NONE,
    "make_interval": NONE,
    "isfinite": NONE,
    "justify_days": NONE,
    "justify_hours": NONE,
    "justify_interval": NONE,
    "date_bin": NONE,
    # Array and set-returning functions compute from their arguments alone.
    "unnest": NONE,
    "array_length": NONE,
    "cardinality": NONE,
    "generate_series": NONE,
    # Sleeping only takes time.
    "pg_sleep": NONE,
    "pg_sleep_for": NONE,
    "pg_sleep_until": NONE,
    # These read the session's TimeZone or locale settings.
    "date_trunc": frozenset({Effect.READS_SESSION}),  # truncates a timestamptz in TimeZone
    "date_part": frozenset({Effect.READS_SESSION}),  # fields of a timestamptz in TimeZone
    "extract": frozenset({Effect.READS_SESSION}),  # fields of a timestamptz in TimeZone
    "to_timestamp": frozenset({Effect.READS_SESSION}),  # reads text in TimeZone
    "to_char": frozenset({Effect.READS_SESSION}),  # TimeZone, lc_time and lc_numeric
    "to_date": frozenset({Effect.READS_SESSION}),  # TM patterns use lc_time
    "to_number": frozenset({Effect.READS_SESSION}),  # lc_numeric
    "age": frozenset({Effect.READS_SESSION, Effect.READS_CLOCK}),  # months in TimeZone; age(x) measures from today
    # The time: now and transaction_timestamp at the transaction's start, the others when called.
    "now": frozenset({Effect.READS_CLOCK}),
    "transaction_timestamp": frozenset({Effect.READS_CLOCK}),
    "statement_timestamp": frozenset({Effect.READS_CLOCK}),
    "clock_timestamp": frozenset({Effect.READS_CLOCK}),
    "timeofday": frozenset({Effect.READS_CLOCK}),
    "timezone": frozenset({Effect.READS_CLOCK}),  # a timetz's offset depends on today's date
    # random draws from the session's seed and advances it.
    "random": frozenset({Effect.READS_SESSION, Effect.WRITES_SESSION}),
    "setseed": frozenset({Effect.WRITES_SESSION}),
    # nextval advances a sequence and records the value as the session's currval.
    "nextval": frozenset({Effect.WRITES_DATA, Effect.WRITES_SESSION}),
    "setval": frozenset({Effect.WRITES_DATA}),
    "currval": frozenset({Effect.READS_SESSION}),
    "lastval": frozenset({Effect.READS_SESSION}),
    # The session's settings.
    "current_setting": frozenset({Effect.READS_SESSION}),
    "set_config": frozenset({Effect.WRITES_SESSION}),
    "pg_backend_pid": frozenset({Effect.READS_SESSION}),  # the session's own process
    # Definitions as text, and names looked up through the session's search_path.
    "pg_get_viewdef": frozenset({Effect.READS_CATALOG}),
    "pg_get_functiondef": frozenset({Effect.READS_CATALOG}),
    "format_type": frozenset({Effect.READS_CATALOG}),
    "to_regclass": frozenset({Effect.READS_CATALOG, Effect.READS_SESSION}),
    "pg_import_system_collations": frozenset({Effect.WRITES_CATALOG}),  # adds rows to pg_collation
    # The server's version, configuration, logs, write-ahead log and statistics.
    "version": frozenset({Effect.READS_SERVER}),
    "pg_reload_conf": frozenset({Effect.WRITES_SERVER}),
    "pg_rotate_logfile": frozenset({Effect.WRITES_SERVER}),
    "pg_switch_wal": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset": frozenset({Effect.WRITES_SERVER}),
    # Other processes.
    "pg_cancel_backend": frozenset({Effect.WRITES_PROCESSES}),
    "pg_terminate_backend": frozenset({Effect.WRITES_PROCESSES}),
    "pg_notify": frozenset({Effect.WRITES_PROCESSES}),  # delivered to listening sessions on commit
    # Advisory locks. The try and unlock forms also return whether the lock was free or held.
    "pg_advisory_lock": frozenset({Effect.WRITES_LOCKS}),
    "pg_advisory_lock_shared": frozenset({Effect.WRITES_LOCKS}),
    "pg_advisory_xact_lock": frozenset({Effect.WRITES_LOCKS}),
    "pg_advisory_xact_lock_shared": frozenset({Effect.WRITES_LOCKS}),
    "pg_try_advisory_lock": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_try_advisory_lock_shared": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_try_advisory_xact_lock": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_try_advisory_xact_lock_shared": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_advisory_unlock": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_advisory_unlock_shared": frozenset({Effect.READS_LOCKS, Effect.WRITES_LOCKS}),
    "pg_advisory_unlock_all": frozenset({Effect.WRITES_LOCKS}),
    "pg_blocking_pids": frozenset({Effect.READS_LOCKS, Effect.READS_PROCESSES}),
    # Files on the server. Large objects are stored in the database.
    "pg_read_file": frozenset({Effect.READS_FILES}),
    "pg_read_binary_file": frozenset({Effect.READS_FILES}),
    "pg_ls_dir": frozenset({Effect.READS_FILES}),
    "pg_stat_file": frozenset({Effect.READS_FILES}),
    "pg_ls_logdir": frozenset({Effect.READS_FILES}),
    "pg_ls_waldir": frozenset({Effect.READS_FILES}),
    "lo_import": frozenset({Effect.READS_FILES, Effect.WRITES_DATA}),
    "lo_export": frozenset({Effect.READS_DATA, Effect.WRITES_FILES}),
    # These run SQL given as text.
    "query_to_xml": frozenset({Effect.OPAQUE}),
    "query_to_xmlschema": frozenset({Effect.OPAQUE}),
    "query_to_xml_and_xmlschema": frozenset({Effect.OPAQUE}),
    "ts_stat": frozenset({Effect.OPAQUE}),
}

# Keywords that read a value without a function call.
SQL_VALUE_FUNCTION_EFFECTS: dict[SQLValueFunctionOp, frozenset[Effect]] = {
    # The date and local times are in the session's TimeZone.
    SQLValueFunctionOp.SVFOP_CURRENT_DATE: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_CURRENT_TIME: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_CURRENT_TIME_N: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_LOCALTIME: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_LOCALTIME_N: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_LOCALTIMESTAMP: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_LOCALTIMESTAMP_N: frozenset({Effect.READS_CLOCK, Effect.READS_SESSION}),
    # A timestamptz is a point in time.
    SQLValueFunctionOp.SVFOP_CURRENT_TIMESTAMP: frozenset({Effect.READS_CLOCK}),
    SQLValueFunctionOp.SVFOP_CURRENT_TIMESTAMP_N: frozenset({Effect.READS_CLOCK}),
    # The session's role, database and first schema in search_path.
    SQLValueFunctionOp.SVFOP_CURRENT_ROLE: frozenset({Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_CURRENT_USER: frozenset({Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_USER: frozenset({Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_SESSION_USER: frozenset({Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_CURRENT_CATALOG: frozenset({Effect.READS_SESSION}),
    SQLValueFunctionOp.SVFOP_CURRENT_SCHEMA: frozenset({Effect.READS_SESSION}),
}

# Casting text to these looks the name up in the catalog through the session's search_path.
CATALOG_LOOKUP_TYPES = frozenset({
    "regclass",
    "regcollation",
    "regconfig",
    "regdictionary",
    "regnamespace",
    "regoper",
    "regoperator",
    "regproc",
    "regprocedure",
    "regrole",
    "regtype",
})

@dataclass(frozen=True)
class Cause:
    """An effect, and the node in the query that may cause it."""

    effect: Effect
    node: ast.Node


def effects(root: ast.Node) -> list[Cause]:
    """Every effect the query may have, each with the node that may cause it."""
    return [cause for node in walk(root) for cause in _own_effects(node)]


def _is_builtin(names: tuple[ast.String, ...]) -> bool:
    """Whether the name is unqualified or qualified with pg_catalog."""
    return len(names) == 1 or (len(names) == 2 and names[0].sval == "pg_catalog")


def _own_effects(node: ast.Node) -> Iterator[Cause]:
    """The effects of the node itself, not of the nodes inside it."""
    match node:
        case ast.FuncCall(funcname=names):
            if _is_builtin(names):
                name = names[-1].sval
                found = FUNCTION_EFFECTS.get(name, {Effect.UNCLASSIFIED})
                for effect in found:
                    yield Cause(effect, node)
            else:
                yield Cause(Effect.OPAQUE, node)  # a function in another schema is user code
        case ast.RangeVar(schemaname="pg_catalog" | "information_schema"):
            yield Cause(Effect.READS_CATALOG, node)
        case ast.RangeVar(schemaname=None, relname=name) if name.startswith("pg_"):
            # pg_catalog's relations all start with pg_, and pg_catalog is searched first.
            # Another schema may also have one by that name.
            yield Cause(Effect.READS_CATALOG, node)
            yield Cause(Effect.READS_DATA, node)
        case ast.RangeVar():
            yield Cause(Effect.READS_DATA, node)
        case ast.SQLValueFunction(op=op):
            found = SQL_VALUE_FUNCTION_EFFECTS.get(op, {Effect.UNCLASSIFIED})
            for effect in found:
                yield Cause(effect, node)
        case ast.LockingClause(waitPolicy=policy):
            yield Cause(Effect.WRITES_LOCKS, node)
            # SKIP LOCKED and NOWAIT act on whether other sessions hold the rows' locks.
            waits = policy == LockWaitPolicy.LockWaitBlock
            if not waits:
                yield Cause(Effect.READS_LOCKS, node)
        # Converting a value to a type runs the type's input or cast function.
        case ast.TypeName(names=names):
            if not _is_builtin(names):
                yield Cause(Effect.OPAQUE, node)
            else:
                name = names[-1].sval
                if name in CATALOG_LOOKUP_TYPES:
                    yield Cause(Effect.READS_CATALOG, node)
                    yield Cause(Effect.READS_SESSION, node)
        # An operator runs its function, so one in another schema is user code.
        case ast.A_Expr(name=operator):
            if not _is_builtin(operator):
                yield Cause(Effect.OPAQUE, node)
        case ast.SubLink(operName=operator):
            # Only comparisons like = ANY (...) name an operator.
            if operator and not _is_builtin(operator):
                yield Cause(Effect.OPAQUE, node)
        case ast.SortBy(useOp=operator):
            # Only ORDER BY ... USING names an operator.
            if operator and not _is_builtin(operator):
                yield Cause(Effect.OPAQUE, node)
        # These have no effects of their own; the nodes inside them may.
        case (
            ast.SelectStmt()
            | ast.WithClause()
            | ast.CommonTableExpr()
            | ast.ResTarget()
            | ast.ColumnRef()
            | ast.A_Star()
            | ast.A_Const()
            | ast.String()
            | ast.Integer()
            | ast.Float()
            | ast.Boolean()
            | ast.BitString()
            | ast.BoolExpr()
            | ast.NullTest()
            | ast.BooleanTest()
            | ast.GroupingSet()
            | ast.RangeSubselect()
            | ast.JoinExpr()
            | ast.Alias()
            | ast.CaseExpr()
            | ast.CaseWhen()
            | ast.CoalesceExpr()
            | ast.MinMaxExpr()
            | ast.RowExpr()
            | ast.A_ArrayExpr()
            | ast.A_Indirection()
            | ast.A_Indices()
            | ast.WindowDef()
            | ast.TypeCast()
            | ast.RangeFunction()
            | ast.ExplainStmt()
            | ast.DefElem()  # EXPLAIN options
        ):
            pass
        case _:
            yield Cause(Effect.UNCLASSIFIED, node)
