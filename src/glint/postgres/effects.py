"""The effects a SELECT may have besides computing its result.

A query has the effects of all its parts. They come from the parsed query alone:
each name is taken as the built-in it names, and each relation as data it reads.
Every query also reads the catalog and the session's settings, and may read the clock.
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
    READS_CATALOG = auto()  # reads schema definitions, such as tables, functions and types
    WRITES_CATALOG = auto()  # changes schema definitions
    READS_SESSION_SETTINGS = auto()  # reads the session's settings, such as search_path and TimeZone
    WRITES_SESSION_SETTINGS = auto()  # changes the session's settings
    READS_SESSION_STATE = auto()  # reads the session's other state, such as its role or currval
    WRITES_SESSION_STATE = auto()  # changes the session's other state, such as currval or the random seed
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
    "json_agg": NONE,  # turns values into JSON, which reads TimeZone and others
    "jsonb_agg": NONE,  # turns values into JSON, which reads TimeZone and others
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
    "pow": NONE,
    "factorial": NONE,
    "gcd": NONE,
    "lcm": NONE,
    "scale": NONE,
    "min_scale": NONE,
    "trim_scale": NONE,
    "erf": NONE,
    "erfc": NONE,
    "gamma": NONE,
    "lgamma": NONE,
    "pi": NONE,
    "degrees": NONE,
    "radians": NONE,
    "sin": NONE,
    "cos": NONE,
    "tan": NONE,
    "cot": NONE,
    "asin": NONE,
    "acos": NONE,
    "atan": NONE,
    "atan2": NONE,
    "sind": NONE,
    "cosd": NONE,
    "tand": NONE,
    "cotd": NONE,
    "asind": NONE,
    "acosd": NONE,
    "atand": NONE,
    "atan2d": NONE,
    "sinh": NONE,
    "cosh": NONE,
    "tanh": NONE,
    "asinh": NONE,
    "acosh": NONE,
    "atanh": NONE,
    "width_bucket": NONE,
    # String and binary functions compute from their arguments alone.
    "lower": NONE,
    "upper": NONE,
    "initcap": NONE,
    "casefold": NONE,
    "length": NONE,  # stable for bytea in an encoding, which is looked up in a built-in list
    "char_length": NONE,
    "character_length": NONE,
    "textlen": NONE,
    "octet_length": NONE,
    "bit_length": NONE,
    "bit_count": NONE,
    "substr": NONE,
    "substring": NONE,
    "overlay": NONE,
    "btrim": NONE,
    "ltrim": NONE,
    "rtrim": NONE,
    "left": NONE,
    "right": NONE,
    "reverse": NONE,
    "replace": NONE,
    "translate": NONE,
    "split_part": NONE,
    "string_to_array": NONE,
    "string_to_table": NONE,
    "position": NONE,
    "strpos": NONE,
    "starts_with": NONE,
    "repeat": NONE,
    "lpad": NONE,
    "rpad": NONE,
    "ascii": NONE,
    "chr": NONE,
    "unistr": NONE,
    "normalize": NONE,
    "is_normalized": NONE,
    "unicode_assigned": NONE,
    "to_ascii": NONE,
    "to_bin": NONE,
    "to_oct": NONE,
    "to_hex": NONE,
    "quote_ident": NONE,
    "parse_ident": NONE,
    "text": NONE,
    "like": NONE,
    "notlike": NONE,
    "like_escape": NONE,
    "similar_escape": NONE,
    "similar_to_escape": NONE,
    "regexp_replace": NONE,
    "regexp_match": NONE,
    "regexp_matches": NONE,
    "regexp_like": NONE,
    "regexp_count": NONE,
    "regexp_instr": NONE,
    "regexp_substr": NONE,
    "regexp_split_to_array": NONE,
    "regexp_split_to_table": NONE,
    "encode": NONE,
    "decode": NONE,
    "get_bit": NONE,
    "get_byte": NONE,
    "set_bit": NONE,  # returns a changed copy
    "set_byte": NONE,  # returns a changed copy
    "md5": NONE,
    "sha224": NONE,
    "sha256": NONE,
    "sha384": NONE,
    "sha512": NONE,
    "crc32": NONE,
    "crc32c": NONE,
    "num_nulls": NONE,
    "num_nonnulls": NONE,
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
    "interval": NONE,
    "overlaps": NONE,
    # Array and set-returning functions compute from their arguments alone.
    "unnest": NONE,
    "array_length": NONE,
    "array_lower": NONE,
    "array_upper": NONE,
    "array_dims": NONE,
    "array_ndims": NONE,
    "cardinality": NONE,
    "array_append": NONE,
    "array_prepend": NONE,
    "array_cat": NONE,
    "array_fill": NONE,
    "array_position": NONE,
    "array_positions": NONE,
    "array_remove": NONE,
    "array_replace": NONE,
    "array_reverse": NONE,
    "array_sort": NONE,
    "trim_array": NONE,
    "generate_subscripts": NONE,
    "array_to_string": NONE,  # turns elements into text, which reads DateStyle, TimeZone and others
    "generate_series": NONE,  # steps a timestamptz in TimeZone
    # Sleeping only takes time.
    "pg_sleep": NONE,
    "pg_sleep_for": NONE,
    "pg_sleep_until": NONE,
    # These also read the session's TimeZone or locale settings.
    "date_trunc": NONE,  # truncates a timestamptz in TimeZone
    "date_part": NONE,  # fields of a timestamptz in TimeZone
    "extract": NONE,  # fields of a timestamptz in TimeZone
    "to_timestamp": NONE,  # reads text in TimeZone
    "to_char": NONE,  # TimeZone, lc_time and lc_numeric
    "to_date": NONE,  # TM patterns use lc_time
    "to_number": NONE,  # lc_numeric
    "date": NONE,  # the date of a timestamptz in TimeZone
    "time": NONE,  # the time of a timestamptz in TimeZone
    "timestamp": NONE,  # a timestamptz in TimeZone
    "timestamptz": NONE,  # a timestamp or date in TimeZone
    "make_timestamptz": NONE,  # in TimeZone unless given a zone
    "date_add": NONE,  # adds days and months in TimeZone unless given a zone
    "date_subtract": NONE,  # subtracts days and months in TimeZone unless given a zone
    "age": NONE,  # months in TimeZone; age(x) measures from today
    # These turn values of any type into text, which reads DateStyle, TimeZone, extra_float_digits and others.
    "concat": NONE,
    "concat_ws": NONE,
    "format": NONE,
    "quote_literal": NONE,
    "quote_nullable": NONE,
    # These also read the clock: now and transaction_timestamp at the transaction's start,
    # the others when called.
    "now": NONE,
    "transaction_timestamp": NONE,
    "statement_timestamp": NONE,
    "clock_timestamp": NONE,
    "timeofday": NONE,
    "timezone": NONE,  # a timetz's offset depends on today's date
    "timetz": NONE,  # a time's offset depends on today's date
    # random draws from the session's seed and advances it.
    "random": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "random_normal": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "setseed": frozenset({Effect.WRITES_SESSION_STATE}),
    # These draw from another random state of the session, which setseed doesn't set.
    "array_shuffle": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "array_sample": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    # nextval advances a sequence and records the value as the session's currval.
    "nextval": frozenset({Effect.WRITES_DATA, Effect.WRITES_SESSION_STATE}),
    "setval": frozenset({Effect.WRITES_DATA}),
    "currval": frozenset({Effect.READS_SESSION_STATE}),
    "lastval": frozenset({Effect.READS_SESSION_STATE}),
    # The session's settings and state.
    "current_setting": NONE,  # reads a setting, as every query does
    "set_config": frozenset({Effect.WRITES_SESSION_SETTINGS}),
    "pg_backend_pid": frozenset({Effect.READS_SESSION_STATE}),  # the session's own process
    "getdatabaseencoding": frozenset({Effect.READS_SESSION_STATE}),  # the connected database's encoding
    # These also read the catalog: definitions as text, and names and conversions looked up.
    "pg_get_viewdef": NONE,
    "pg_get_functiondef": NONE,
    "format_type": NONE,
    "to_regclass": NONE,
    "convert": NONE,
    "convert_from": NONE,
    "convert_to": NONE,
    "pg_import_system_collations": frozenset({Effect.WRITES_CATALOG}),  # adds rows to pg_collation
    # The server's version, configuration, logs, write-ahead log and statistics.
    "version": frozenset({Effect.READS_SERVER}),
    "unicode_version": frozenset({Effect.READS_SERVER}),
    "icu_unicode_version": frozenset({Effect.READS_SERVER}),
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
    # The current time, which every query may read. The date and local times are in TimeZone.
    SQLValueFunctionOp.SVFOP_CURRENT_DATE: NONE,
    SQLValueFunctionOp.SVFOP_CURRENT_TIME: NONE,
    SQLValueFunctionOp.SVFOP_CURRENT_TIME_N: NONE,
    SQLValueFunctionOp.SVFOP_LOCALTIME: NONE,
    SQLValueFunctionOp.SVFOP_LOCALTIME_N: NONE,
    SQLValueFunctionOp.SVFOP_LOCALTIMESTAMP: NONE,
    SQLValueFunctionOp.SVFOP_LOCALTIMESTAMP_N: NONE,
    SQLValueFunctionOp.SVFOP_CURRENT_TIMESTAMP: NONE,
    SQLValueFunctionOp.SVFOP_CURRENT_TIMESTAMP_N: NONE,
    # The session's role and database.
    SQLValueFunctionOp.SVFOP_CURRENT_ROLE: frozenset({Effect.READS_SESSION_STATE}),
    SQLValueFunctionOp.SVFOP_CURRENT_USER: frozenset({Effect.READS_SESSION_STATE}),
    SQLValueFunctionOp.SVFOP_USER: frozenset({Effect.READS_SESSION_STATE}),
    SQLValueFunctionOp.SVFOP_SESSION_USER: frozenset({Effect.READS_SESSION_STATE}),
    SQLValueFunctionOp.SVFOP_CURRENT_CATALOG: frozenset({Effect.READS_SESSION_STATE}),
    SQLValueFunctionOp.SVFOP_CURRENT_SCHEMA: NONE,  # the first schema in search_path
}

@dataclass(frozen=True)
class Cause:
    """An effect, and the node in the query that may cause it."""

    effect: Effect
    node: ast.Node


def effects(root: ast.Node) -> Iterator[Cause]:
    """Every effect the query may have, each with the node that may cause it."""
    # Names, types and operators are looked up in the catalog.
    yield Cause(Effect.READS_CATALOG, root)
    # Names, literals, casts, operators and output all read settings such as search_path,
    # TimeZone and DateStyle, so every query reads them.
    yield Cause(Effect.READS_SESSION_SETTINGS, root)
    # Text such as 'today' converted to a date, and a time converted to a timetz, read the clock.
    # The conversion may be implicit, so every query may read it.
    yield Cause(Effect.READS_CLOCK, root)
    for node in walk(root):
        yield from _own_effects(node)


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
            pass  # reads the catalog, as every query does
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
        # An operator runs its function, so one in another schema is user code.
        # Built-in operators read at most the session's settings and the catalog.
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
