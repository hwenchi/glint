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
    """Reading or writing a resource. The clock and the random source can only be read."""

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
    READS_RANDOM_SOURCE = auto()  # draws from the operating system's random source
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
    "any_value": NONE,
    "bit_and": NONE,
    "bit_or": NONE,
    "bit_xor": NONE,
    "range_agg": NONE,
    "range_intersect_agg": NONE,
    "xmlagg": NONE,
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
    # Casts called by their type's name, as in int4(x). They read settings such as lc_monetary.
    "bool": NONE,
    "int2": NONE,
    "int4": NONE,
    "int8": NONE,
    "float4": NONE,
    "float8": NONE,
    "numeric": NONE,
    "money": NONE,
    "oid": NONE,
    "xid": NONE,
    "char": NONE,
    "bpchar": NONE,
    "varchar": NONE,
    "name": NONE,
    "bytea": NONE,
    "bit": NONE,
    "varbit": NONE,
    "cidr": NONE,
    "macaddr": NONE,
    "macaddr8": NONE,
    "xml": NONE,
    "regclass": NONE,  # looks the name up in the catalog
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
    # JSON functions compute from their arguments. Converting other types to and from JSON
    # reads settings such as TimeZone, and so do the _tz path functions.
    "to_json": NONE,
    "to_jsonb": NONE,
    "array_to_json": NONE,
    "row_to_json": NONE,
    "json_build_array": NONE,
    "jsonb_build_array": NONE,
    "json_build_object": NONE,
    "jsonb_build_object": NONE,
    "json_object": NONE,
    "jsonb_object": NONE,
    "json_agg_strict": NONE,
    "jsonb_agg_strict": NONE,
    "json_object_agg": NONE,
    "jsonb_object_agg": NONE,
    "json_object_agg_strict": NONE,
    "jsonb_object_agg_strict": NONE,
    "json_object_agg_unique": NONE,
    "jsonb_object_agg_unique": NONE,
    "json_object_agg_unique_strict": NONE,
    "jsonb_object_agg_unique_strict": NONE,
    "json_array_elements": NONE,
    "jsonb_array_elements": NONE,
    "json_array_elements_text": NONE,
    "jsonb_array_elements_text": NONE,
    "json_array_length": NONE,
    "jsonb_array_length": NONE,
    "json_each": NONE,
    "jsonb_each": NONE,
    "json_each_text": NONE,
    "jsonb_each_text": NONE,
    "json_object_keys": NONE,
    "jsonb_object_keys": NONE,
    "json_typeof": NONE,
    "jsonb_typeof": NONE,
    "json_strip_nulls": NONE,
    "jsonb_strip_nulls": NONE,
    "json_populate_record": NONE,
    "jsonb_populate_record": NONE,
    "jsonb_populate_record_valid": NONE,
    "json_populate_recordset": NONE,
    "jsonb_populate_recordset": NONE,
    "json_to_record": NONE,
    "jsonb_to_record": NONE,
    "json_to_recordset": NONE,
    "jsonb_to_recordset": NONE,
    "jsonb_set": NONE,  # returns a changed copy
    "jsonb_set_lax": NONE,  # returns a changed copy
    "jsonb_insert": NONE,  # returns a changed copy
    "jsonb_pretty": NONE,
    "jsonb_path_exists": NONE,
    "jsonb_path_exists_tz": NONE,
    "jsonb_path_match": NONE,
    "jsonb_path_match_tz": NONE,
    "jsonb_path_query": NONE,
    "jsonb_path_query_tz": NONE,
    "jsonb_path_query_array": NONE,
    "jsonb_path_query_array_tz": NONE,
    "jsonb_path_query_first": NONE,
    "jsonb_path_query_first_tz": NONE,
    # Range, geometry and network address functions compute from their arguments alone.
    "int4range": NONE,
    "int8range": NONE,
    "numrange": NONE,
    "tsrange": NONE,
    "tstzrange": NONE,
    "daterange": NONE,
    "int4multirange": NONE,
    "int8multirange": NONE,
    "nummultirange": NONE,
    "tsmultirange": NONE,
    "tstzmultirange": NONE,
    "datemultirange": NONE,
    "multirange": NONE,
    "isempty": NONE,
    "lower_inc": NONE,
    "upper_inc": NONE,
    "lower_inf": NONE,
    "upper_inf": NONE,
    "range_merge": NONE,
    "point": NONE,
    "line": NONE,
    "lseg": NONE,
    "box": NONE,
    "path": NONE,
    "polygon": NONE,
    "circle": NONE,
    "area": NONE,
    "center": NONE,
    "diagonal": NONE,
    "diameter": NONE,
    "height": NONE,
    "width": NONE,
    "radius": NONE,
    "slope": NONE,
    "npoints": NONE,
    "bound_box": NONE,
    "isclosed": NONE,
    "isopen": NONE,
    "pclose": NONE,
    "popen": NONE,
    "ishorizontal": NONE,
    "isvertical": NONE,
    "isparallel": NONE,
    "isperp": NONE,
    "abbrev": NONE,
    "broadcast": NONE,
    "family": NONE,
    "host": NONE,
    "hostmask": NONE,
    "netmask": NONE,
    "network": NONE,
    "masklen": NONE,
    "set_masklen": NONE,
    "inet_merge": NONE,
    "inet_same_family": NONE,
    "macaddr8_set7bit": NONE,
    "uuid_extract_timestamp": NONE,
    "uuid_extract_version": NONE,
    # Text search reads its configuration from the catalog. Dictionaries may also load
    # stop word and synonym files installed with the server.
    "to_tsvector": NONE,
    "json_to_tsvector": NONE,
    "jsonb_to_tsvector": NONE,
    "array_to_tsvector": NONE,
    "to_tsquery": NONE,
    "plainto_tsquery": NONE,
    "phraseto_tsquery": NONE,
    "websearch_to_tsquery": NONE,
    "get_current_ts_config": NONE,
    "setweight": NONE,
    "strip": NONE,
    "numnode": NONE,
    "querytree": NONE,
    "tsquery_phrase": NONE,
    "tsvector_to_array": NONE,
    "ts_delete": NONE,
    "ts_filter": NONE,
    "ts_rank": NONE,
    "ts_rank_cd": NONE,
    "ts_headline": NONE,
    "ts_lexize": NONE,
    "ts_parse": NONE,
    "ts_token_type": NONE,
    "ts_debug": NONE,
    # XML functions compute from their arguments. Parsing never loads external entities.
    "xmlcomment": NONE,
    "xmltext": NONE,
    "xmlexists": NONE,
    "xpath": NONE,
    "xpath_exists": NONE,
    "xml_is_well_formed": NONE,
    "xml_is_well_formed_content": NONE,
    "xml_is_well_formed_document": NONE,
    "xmlvalidate": NONE,  # not implemented; always fails
    # These inspect or format a value.
    "pg_column_size": NONE,
    "pg_column_compression": NONE,
    "pg_column_toast_chunk_id": NONE,
    "pg_size_pretty": NONE,
    "pg_size_bytes": NONE,
    "cash_words": NONE,
    # These read extension control files and time zone files installed with the server.
    "pg_available_extensions": NONE,
    "pg_available_extension_versions": NONE,
    "pg_extension_update_paths": NONE,
    "pg_timezone_names": NONE,
    "pg_timezone_abbrevs_zone": NONE,
    "pg_timezone_abbrevs_abbrevs": NONE,
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
    # Months in TimeZone; age(timestamp) measures from today. age(xid) counts from the
    # transaction's ID, or the server's next one.
    "age": frozenset({Effect.READS_SESSION_STATE, Effect.READS_SERVER}),
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
    # These draw from the operating system's random source.
    "gen_random_uuid": frozenset({Effect.READS_RANDOM_SOURCE}),
    "uuidv4": frozenset({Effect.READS_RANDOM_SOURCE}),
    "uuidv7": frozenset({
        Effect.READS_RANDOM_SOURCE,
        Effect.READS_SESSION_STATE,  # keeps its last timestamp to stay increasing
        Effect.WRITES_SESSION_STATE,
    }),
    # nextval advances a sequence and records the value as the session's currval.
    "nextval": frozenset({Effect.WRITES_DATA, Effect.WRITES_SESSION_STATE}),
    "setval": frozenset({Effect.WRITES_DATA}),
    "pg_sequence_last_value": frozenset({Effect.READS_DATA}),
    "pg_get_sequence_data": frozenset({Effect.READS_DATA}),
    # These read or write tables and indexes named by their arguments.
    "currtid2": frozenset({Effect.READS_DATA}),  # the latest version of a row
    "brin_summarize_range": frozenset({Effect.READS_DATA, Effect.WRITES_DATA}),
    "brin_summarize_new_values": frozenset({Effect.READS_DATA, Effect.WRITES_DATA}),
    "brin_desummarize_range": frozenset({Effect.WRITES_DATA}),
    "gin_clean_pending_list": frozenset({Effect.READS_DATA, Effect.WRITES_DATA}),
    "currval": frozenset({Effect.READS_SESSION_STATE}),
    "lastval": frozenset({Effect.READS_SESSION_STATE}),
    # The session's settings and state.
    "current_setting": NONE,  # reads a setting, as every query does
    "set_config": frozenset({Effect.WRITES_SESSION_SETTINGS}),
    "pg_backend_pid": frozenset({Effect.READS_SESSION_STATE}),  # the session's own process
    "getdatabaseencoding": frozenset({Effect.READS_SESSION_STATE}),  # the connected database's encoding
    "inet_client_addr": frozenset({Effect.READS_SESSION_STATE}),  # the connection's addresses and ports
    "inet_client_port": frozenset({Effect.READS_SESSION_STATE}),
    "inet_server_addr": frozenset({Effect.READS_SESSION_STATE}),
    "inet_server_port": frozenset({Effect.READS_SESSION_STATE}),
    "current_user": frozenset({Effect.READS_SESSION_STATE}),
    "session_user": frozenset({Effect.READS_SESSION_STATE}),
    "system_user": frozenset({Effect.READS_SESSION_STATE}),
    "getpgusername": frozenset({Effect.READS_SESSION_STATE}),
    "current_database": frozenset({Effect.READS_SESSION_STATE}),
    "current_query": frozenset({Effect.READS_SESSION_STATE}),
    "pg_my_temp_schema": frozenset({Effect.READS_SESSION_STATE}),
    "pg_is_other_temp_schema": frozenset({Effect.READS_SESSION_STATE}),
    "pg_trigger_depth": frozenset({Effect.READS_SESSION_STATE}),
    "pg_listening_channels": frozenset({Effect.READS_SESSION_STATE}),
    "pg_cursor": frozenset({Effect.READS_SESSION_STATE}),
    "pg_prepared_statement": frozenset({Effect.READS_SESSION_STATE}),
    "pg_get_backend_memory_contexts": frozenset({Effect.READS_SESSION_STATE}),
    "pg_get_loaded_modules": frozenset({Effect.READS_SESSION_STATE}),
    "pg_replication_origin_session_is_setup": frozenset({Effect.READS_SESSION_STATE}),
    "pg_replication_origin_session_progress": frozenset({
        Effect.READS_SESSION_STATE,
        Effect.WRITES_SERVER,  # flush=true flushes the write-ahead log
    }),
    "pg_replication_origin_oid": NONE,  # looks the name up in the catalog
    "pg_replication_origin_session_setup": frozenset({Effect.WRITES_SESSION_STATE}),
    "pg_replication_origin_session_reset": frozenset({Effect.WRITES_SESSION_STATE}),
    "pg_replication_origin_xact_setup": frozenset({Effect.WRITES_SESSION_STATE}),
    "pg_replication_origin_xact_reset": frozenset({Effect.WRITES_SESSION_STATE}),
    "pg_event_trigger_ddl_commands": frozenset({Effect.READS_SESSION_STATE}),  # in an event trigger only
    "pg_event_trigger_dropped_objects": frozenset({Effect.READS_SESSION_STATE}),
    "pg_event_trigger_table_rewrite_oid": frozenset({Effect.READS_SESSION_STATE}),
    "pg_event_trigger_table_rewrite_reason": frozenset({Effect.READS_SESSION_STATE}),
    # The current schema, encoding and settings are themselves settings.
    "current_schema": NONE,
    "current_schemas": NONE,
    "pg_client_encoding": NONE,
    "pg_show_all_settings": NONE,
    "pg_settings_get_flags": NONE,
    # Statistics the session has collected in the current transaction, not yet sent to the server.
    "pg_stat_get_xact_numscans": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_returned": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_fetched": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_inserted": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_updated": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_deleted": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_hot_updated": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_tuples_newpage_updated": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_blocks_fetched": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_blocks_hit": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_function_calls": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_function_total_time": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_get_xact_function_self_time": frozenset({Effect.READS_SESSION_STATE}),
    "pg_stat_clear_snapshot": frozenset({Effect.WRITES_SESSION_STATE}),  # discards the session's copy of the statistics
    "pg_stat_force_next_flush": frozenset({Effect.WRITES_SESSION_STATE}),  # sends the session's statistics sooner
    # These also read the catalog: definitions as text, and names and conversions looked up.
    "pg_get_viewdef": NONE,
    "pg_get_functiondef": NONE,
    "pg_get_function_arguments": NONE,
    "pg_get_function_identity_arguments": NONE,
    "pg_get_function_result": NONE,
    "pg_get_function_arg_default": NONE,
    "pg_get_function_sqlbody": NONE,
    "pg_get_constraintdef": NONE,
    "pg_get_indexdef": NONE,
    "pg_get_ruledef": NONE,
    "pg_get_triggerdef": NONE,
    "pg_get_statisticsobjdef": NONE,
    "pg_get_statisticsobjdef_columns": NONE,
    "pg_get_statisticsobjdef_expressions": NONE,
    "pg_get_partkeydef": NONE,
    "pg_get_partition_constraintdef": NONE,
    "pg_get_expr": NONE,
    "pg_get_userbyid": NONE,
    "pg_get_serial_sequence": NONE,
    "pg_get_replica_identity_index": NONE,
    "pg_get_catalog_foreign_keys": NONE,
    "pg_get_publication_tables": NONE,
    "pg_get_acl": NONE,
    "pg_get_keywords": NONE,
    "pg_get_object_address": NONE,
    "pg_describe_object": NONE,
    "pg_identify_object": NONE,
    "pg_identify_object_as_address": NONE,
    "obj_description": NONE,
    "col_description": NONE,
    "shobj_description": NONE,
    "pg_options_to_table": NONE,
    "pg_sequence_parameters": NONE,
    "pg_mcv_list_items": NONE,
    "pg_relation_filenode": NONE,
    "pg_relation_filepath": NONE,
    "pg_filenode_relation": NONE,
    "pg_relation_is_updatable": NONE,
    "pg_column_is_updatable": NONE,
    "pg_relation_is_publishable": NONE,
    "pg_partition_tree": NONE,
    "pg_partition_ancestors": NONE,
    "pg_partition_root": NONE,
    "pg_index_has_property": NONE,
    "pg_index_column_has_property": NONE,
    "pg_indexam_has_property": NONE,
    "pg_indexam_progress_phasename": NONE,
    "enum_first": NONE,
    "enum_last": NONE,
    "enum_range": NONE,
    "format_type": NONE,
    "oidvectortypes": NONE,
    "pg_typeof": NONE,
    "pg_basetype": NONE,
    "pg_collation_for": NONE,
    "pg_input_is_valid": NONE,  # runs the type's input function
    "pg_input_error_info": NONE,  # runs the type's input function
    "pg_encoding_to_char": NONE,
    "pg_char_to_encoding": NONE,
    "pg_encoding_max_length": NONE,
    "to_regclass": NONE,
    "to_regcollation": NONE,
    "to_regnamespace": NONE,
    "to_regoper": NONE,
    "to_regoperator": NONE,
    "to_regproc": NONE,
    "to_regprocedure": NONE,
    "to_regrole": NONE,
    "to_regtype": NONE,
    "to_regtypemod": NONE,
    "pg_table_is_visible": NONE,
    "pg_type_is_visible": NONE,
    "pg_function_is_visible": NONE,
    "pg_operator_is_visible": NONE,
    "pg_opclass_is_visible": NONE,
    "pg_opfamily_is_visible": NONE,
    "pg_collation_is_visible": NONE,
    "pg_conversion_is_visible": NONE,
    "pg_statistics_obj_is_visible": NONE,
    "pg_ts_config_is_visible": NONE,
    "pg_ts_dict_is_visible": NONE,
    "pg_ts_parser_is_visible": NONE,
    "pg_ts_template_is_visible": NONE,
    # Privileges are stored in the catalog. These check them for the session's role unless given another.
    "has_table_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_any_column_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_column_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_database_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_foreign_data_wrapper_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_function_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_language_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_largeobject_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_parameter_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_schema_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_sequence_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_server_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_tablespace_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "has_type_privilege": frozenset({Effect.READS_SESSION_STATE}),
    "pg_has_role": frozenset({Effect.READS_SESSION_STATE}),
    "row_security_active": frozenset({Effect.READS_SESSION_STATE}),
    # These build and expand privilege lists from their arguments.
    "acldefault": NONE,
    "aclexplode": NONE,
    "makeaclitem": NONE,
    "convert": NONE,
    "convert_from": NONE,
    "convert_to": NONE,
    "pg_import_system_collations": frozenset({Effect.WRITES_CATALOG}),  # adds rows to pg_collation
    "pg_restore_relation_stats": frozenset({Effect.WRITES_CATALOG}),  # planner statistics in pg_class
    "pg_clear_relation_stats": frozenset({Effect.WRITES_CATALOG}),
    "pg_restore_attribute_stats": frozenset({Effect.WRITES_CATALOG}),  # planner statistics in pg_statistic
    "pg_clear_attribute_stats": frozenset({Effect.WRITES_CATALOG}),
    "pg_extension_config_dump": frozenset({Effect.WRITES_CATALOG}),  # marks a table in pg_extension
    "pg_replication_origin_create": frozenset({Effect.WRITES_CATALOG}),
    "pg_replication_origin_drop": frozenset({Effect.WRITES_CATALOG}),
    # The server's version, configuration, logs, write-ahead log and statistics.
    "version": frozenset({Effect.READS_SERVER}),
    "unicode_version": frozenset({Effect.READS_SERVER}),
    "icu_unicode_version": frozenset({Effect.READS_SERVER}),
    "pg_reload_conf": frozenset({Effect.WRITES_SERVER}),
    "pg_rotate_logfile": frozenset({Effect.WRITES_SERVER}),
    "pg_switch_wal": frozenset({Effect.WRITES_SERVER}),
    "pg_create_restore_point": frozenset({Effect.WRITES_SERVER}),
    "pg_log_standby_snapshot": frozenset({Effect.WRITES_SERVER}),
    "pg_logical_emit_message": frozenset({Effect.WRITES_SERVER}),  # writes it to the write-ahead log
    "pg_backup_start": frozenset({Effect.WRITES_SERVER}),
    "pg_backup_stop": frozenset({Effect.WRITES_SERVER}),
    "pg_promote": frozenset({Effect.WRITES_SERVER}),
    "pg_wal_replay_pause": frozenset({Effect.WRITES_SERVER}),
    "pg_wal_replay_resume": frozenset({Effect.WRITES_SERVER}),
    "pg_export_snapshot": frozenset({Effect.WRITES_SERVER}),  # for other sessions to import
    "pg_nextoid": frozenset({Effect.WRITES_SERVER}),  # advances the OID counter
    "pg_stop_making_pinned_objects": frozenset({Effect.WRITES_SERVER}),
    "pg_create_physical_replication_slot": frozenset({Effect.WRITES_SERVER}),
    "pg_create_logical_replication_slot": frozenset({Effect.WRITES_SERVER}),
    "pg_copy_physical_replication_slot": frozenset({Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_copy_logical_replication_slot": frozenset({Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_drop_replication_slot": frozenset({Effect.WRITES_SERVER}),
    "pg_replication_slot_advance": frozenset({Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_sync_replication_slots": frozenset({Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_replication_origin_advance": frozenset({Effect.WRITES_SERVER}),
    # Logical decoding reads changed rows from the write-ahead log through a slot; get also
    # advances the slot.
    "pg_logical_slot_peek_changes": frozenset({Effect.READS_DATA, Effect.READS_SERVER}),
    "pg_logical_slot_peek_binary_changes": frozenset({Effect.READS_DATA, Effect.READS_SERVER}),
    "pg_logical_slot_get_changes": frozenset({Effect.READS_DATA, Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_logical_slot_get_binary_changes": frozenset({Effect.READS_DATA, Effect.READS_SERVER, Effect.WRITES_SERVER}),
    "pg_stat_reset": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_shared": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_single_table_counters": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_single_function_counters": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_backend_stats": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_replication_slot": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_slru": frozenset({Effect.WRITES_SERVER}),
    "pg_stat_reset_subscription_stats": frozenset({Effect.WRITES_SERVER}),
    # Statistics the server has collected.
    "pg_stat_have_stats": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_snapshot_timestamp": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_numscans": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_lastscan": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_returned": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_fetched": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_inserted": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_updated": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_deleted": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_hot_updated": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_tuples_newpage_updated": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_live_tuples": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_dead_tuples": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_mod_since_analyze": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_ins_since_vacuum": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_blocks_fetched": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_blocks_hit": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_last_vacuum_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_last_autovacuum_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_last_analyze_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_last_autoanalyze_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_vacuum_count": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_autovacuum_count": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_analyze_count": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_autoanalyze_count": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_total_vacuum_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_total_autovacuum_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_total_analyze_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_total_autoanalyze_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_function_calls": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_function_total_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_function_self_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_numbackends": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_xact_commit": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_xact_rollback": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_blocks_fetched": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_blocks_hit": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_tuples_returned": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_tuples_fetched": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_tuples_inserted": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_tuples_updated": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_tuples_deleted": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_all": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_tablespace": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_lock": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_snapshot": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_logicalslot": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_bufferpin": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_conflict_startup_deadlock": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_deadlocks": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_checksum_failures": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_checksum_last_failure": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_temp_files": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_temp_bytes": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_blk_read_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_blk_write_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_session_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_active_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_idle_in_transaction_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_sessions": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_sessions_abandoned": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_sessions_fatal": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_sessions_killed": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_parallel_workers_to_launch": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_parallel_workers_launched": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_db_stat_reset_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_bgwriter_buf_written_clean": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_bgwriter_maxwritten_clean": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_bgwriter_stat_reset_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_buf_alloc": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_num_timed": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_num_requested": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_num_performed": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_restartpoints_timed": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_restartpoints_requested": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_restartpoints_performed": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_buffers_written": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_slru_written": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_write_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_sync_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_checkpointer_stat_reset_time": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_archiver": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_io": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_wal": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_slru": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_recovery_prefetch": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_replication_slot": frozenset({Effect.READS_SERVER}),
    "pg_stat_get_subscription_stats": frozenset({Effect.READS_SERVER}),
    # The server's build, start, configuration files, control file, memory and libraries.
    "pg_config": frozenset({Effect.READS_SERVER}),
    "pg_postmaster_start_time": frozenset({Effect.READS_SERVER}),
    "pg_conf_load_time": frozenset({Effect.READS_SERVER}),
    "pg_show_all_file_settings": frozenset({Effect.READS_SERVER}),
    "pg_hba_file_rules": frozenset({Effect.READS_SERVER}),
    "pg_ident_file_mappings": frozenset({Effect.READS_SERVER}),
    "pg_current_logfile": frozenset({Effect.READS_SERVER}),
    "pg_control_system": frozenset({Effect.READS_SERVER}),
    "pg_control_checkpoint": frozenset({Effect.READS_SERVER}),
    "pg_control_recovery": frozenset({Effect.READS_SERVER}),
    "pg_control_init": frozenset({Effect.READS_SERVER}),
    "pg_get_shmem_allocations": frozenset({Effect.READS_SERVER}),
    "pg_get_shmem_allocations_numa": frozenset({Effect.READS_SERVER}),
    "pg_get_aios": frozenset({Effect.READS_SERVER}),
    "pg_get_wait_events": frozenset({Effect.READS_SERVER}),
    "pg_jit_available": frozenset({Effect.READS_SERVER}),
    "pg_numa_available": frozenset({Effect.READS_SERVER}),
    "pg_collation_actual_version": frozenset({Effect.READS_SERVER}),  # the version of the library providing it
    "pg_database_collation_actual_version": frozenset({Effect.READS_SERVER}),
    "pg_notification_queue_usage": frozenset({Effect.READS_SERVER}),
    "pg_get_multixact_members": frozenset({Effect.READS_SERVER}),
    # Relation sizes come from the size of their files, not their contents.
    "pg_relation_size": frozenset({Effect.READS_SERVER}),
    "pg_table_size": frozenset({Effect.READS_SERVER}),
    "pg_indexes_size": frozenset({Effect.READS_SERVER}),
    "pg_total_relation_size": frozenset({Effect.READS_SERVER}),
    "pg_database_size": frozenset({Effect.READS_SERVER}),
    "pg_tablespace_size": frozenset({Effect.READS_SERVER}),
    # The write-ahead log, recovery and replication.
    "pg_is_in_recovery": frozenset({Effect.READS_SERVER}),
    "pg_is_wal_replay_paused": frozenset({Effect.READS_SERVER}),
    "pg_get_wal_replay_pause_state": frozenset({Effect.READS_SERVER}),
    "pg_current_wal_lsn": frozenset({Effect.READS_SERVER}),
    "pg_current_wal_insert_lsn": frozenset({Effect.READS_SERVER}),
    "pg_current_wal_flush_lsn": frozenset({Effect.READS_SERVER}),
    "pg_last_wal_receive_lsn": frozenset({Effect.READS_SERVER}),
    "pg_last_wal_replay_lsn": frozenset({Effect.READS_SERVER}),
    "pg_last_xact_replay_timestamp": frozenset({Effect.READS_SERVER}),
    "pg_get_wal_resource_managers": frozenset({Effect.READS_SERVER}),
    "pg_get_wal_summarizer_state": frozenset({Effect.READS_SERVER}),
    "pg_available_wal_summaries": frozenset({Effect.READS_SERVER}),
    "pg_wal_summary_contents": frozenset({Effect.READS_SERVER}),
    "pg_walfile_name": frozenset({Effect.READS_SERVER}),  # named after the current timeline
    "pg_walfile_name_offset": frozenset({Effect.READS_SERVER}),  # named after the current timeline
    "pg_split_walfile_name": NONE,
    "pg_wal_lsn_diff": NONE,
    "pg_lsn": NONE,
    # Transaction IDs. These assign one to the transaction if it has none, taking it from the server.
    "pg_current_xact_id": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SERVER}),
    "txid_current": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SERVER}),
    "pg_current_xact_id_if_assigned": frozenset({Effect.READS_SESSION_STATE}),
    "txid_current_if_assigned": frozenset({Effect.READS_SESSION_STATE}),
    # A snapshot lists the transactions running in other processes.
    "pg_current_snapshot": frozenset({Effect.READS_SESSION_STATE, Effect.READS_PROCESSES}),
    "txid_current_snapshot": frozenset({Effect.READS_SESSION_STATE, Effect.READS_PROCESSES}),
    "pg_snapshot_xmin": NONE,
    "pg_snapshot_xmax": NONE,
    "pg_snapshot_xip": NONE,
    "pg_visible_in_snapshot": NONE,
    "txid_snapshot_xmin": NONE,
    "txid_snapshot_xmax": NONE,
    "txid_snapshot_xip": NONE,
    "txid_visible_in_snapshot": NONE,
    # The server's record of transactions: their status, commit times and ID counters.
    "pg_xact_status": frozenset({Effect.READS_SERVER}),
    "txid_status": frozenset({Effect.READS_SERVER}),
    "pg_xact_commit_timestamp": frozenset({Effect.READS_SERVER}),
    "pg_xact_commit_timestamp_origin": frozenset({Effect.READS_SERVER}),
    "pg_last_committed_xact": frozenset({Effect.READS_SERVER}),
    "mxid_age": frozenset({Effect.READS_SERVER}),
    "pg_prepared_xact": frozenset({Effect.READS_SERVER}),
    # Replication slots and origins.
    "pg_get_replication_slots": frozenset({Effect.READS_SERVER}),
    "pg_show_replication_origin_status": frozenset({Effect.READS_SERVER}),
    "pg_replication_origin_progress": frozenset({
        Effect.READS_SERVER,
        Effect.WRITES_SERVER,  # flush=true flushes the write-ahead log
    }),
    # Other processes.
    "pg_cancel_backend": frozenset({Effect.WRITES_PROCESSES}),
    "pg_terminate_backend": frozenset({Effect.WRITES_PROCESSES}),
    "pg_notify": frozenset({Effect.WRITES_PROCESSES}),  # delivered to listening sessions on commit
    "pg_log_backend_memory_contexts": frozenset({Effect.WRITES_PROCESSES, Effect.WRITES_SERVER}),  # to the log
    "pg_stat_get_activity": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_progress_info": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_wal_senders": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_wal_receiver": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_subscription": frozenset({Effect.READS_PROCESSES}),  # its worker processes
    "pg_stat_get_backend_idset": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_pid": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_dbid": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_userid": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_activity": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_activity_start": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_xact_start": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_start": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_client_addr": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_client_port": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_wait_event": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_wait_event_type": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_subxact": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_io": frozenset({Effect.READS_PROCESSES}),
    "pg_stat_get_backend_wal": frozenset({Effect.READS_PROCESSES}),
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
    "pg_lock_status": frozenset({Effect.READS_LOCKS, Effect.READS_PROCESSES}),
    "pg_safe_snapshot_blocking_pids": frozenset({Effect.READS_LOCKS, Effect.READS_PROCESSES}),
    "pg_isolation_test_session_is_blocked": frozenset({Effect.READS_LOCKS, Effect.READS_PROCESSES}),
    # Files on the server. Large objects are stored in the database.
    "pg_read_file": frozenset({Effect.READS_FILES}),
    "pg_read_binary_file": frozenset({Effect.READS_FILES}),
    "pg_ls_dir": frozenset({Effect.READS_FILES}),
    "pg_stat_file": frozenset({Effect.READS_FILES}),
    "pg_ls_logdir": frozenset({Effect.READS_FILES}),
    "pg_ls_waldir": frozenset({Effect.READS_FILES}),
    "pg_ls_tmpdir": frozenset({Effect.READS_FILES}),
    "pg_ls_archive_statusdir": frozenset({Effect.READS_FILES}),
    "pg_ls_logicalmapdir": frozenset({Effect.READS_FILES}),
    "pg_ls_logicalsnapdir": frozenset({Effect.READS_FILES}),
    "pg_ls_replslotdir": frozenset({Effect.READS_FILES}),
    "pg_ls_summariesdir": frozenset({Effect.READS_FILES}),
    "pg_tablespace_location": frozenset({Effect.READS_FILES}),  # reads the tablespace's link
    "pg_tablespace_databases": frozenset({Effect.READS_FILES}),  # lists the tablespace's directory
    "lo_import": frozenset({Effect.READS_FILES, Effect.WRITES_DATA}),
    "lo_export": frozenset({Effect.READS_DATA, Effect.WRITES_FILES}),
    # Large objects. An open one is a descriptor of the session, with a position.
    "lo_get": frozenset({Effect.READS_DATA}),
    "lo_put": frozenset({Effect.WRITES_DATA}),
    "lo_creat": frozenset({Effect.WRITES_DATA}),
    "lo_create": frozenset({Effect.WRITES_DATA}),
    "lo_from_bytea": frozenset({Effect.WRITES_DATA}),
    "lo_unlink": frozenset({Effect.WRITES_DATA}),
    "lo_open": frozenset({Effect.READS_DATA, Effect.WRITES_SESSION_STATE}),
    "lo_close": frozenset({Effect.WRITES_SESSION_STATE}),
    "loread": frozenset({Effect.READS_DATA, Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "lowrite": frozenset({Effect.WRITES_DATA, Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "lo_lseek": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "lo_lseek64": frozenset({Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "lo_tell": frozenset({Effect.READS_SESSION_STATE}),
    "lo_tell64": frozenset({Effect.READS_SESSION_STATE}),
    "lo_truncate": frozenset({Effect.WRITES_DATA, Effect.READS_SESSION_STATE}),
    "lo_truncate64": frozenset({Effect.WRITES_DATA, Effect.READS_SESSION_STATE}),
    # These read tables named by their arguments. The xmlschema forms only describe the columns.
    "table_to_xml": frozenset({Effect.READS_DATA}),
    "table_to_xml_and_xmlschema": frozenset({Effect.READS_DATA}),
    "table_to_xmlschema": NONE,
    "schema_to_xml": frozenset({Effect.READS_DATA}),
    "schema_to_xml_and_xmlschema": frozenset({Effect.READS_DATA}),
    "schema_to_xmlschema": NONE,
    "database_to_xml": frozenset({Effect.READS_DATA}),
    "database_to_xml_and_xmlschema": frozenset({Effect.READS_DATA}),
    "database_to_xmlschema": NONE,
    # These read the session's open cursor; cursor_to_xml fetches from it and moves it.
    "cursor_to_xml": frozenset({Effect.READS_DATA, Effect.READS_SESSION_STATE, Effect.WRITES_SESSION_STATE}),
    "cursor_to_xmlschema": frozenset({Effect.READS_SESSION_STATE}),
    # Support functions for indexes, operators and types, which can also be called by name.
    # Comparisons for btree and GIN indexes, some in TimeZone. enum_cmp reads the enum's order.
    "bitcmp": NONE,
    "bpcharcmp": NONE,
    "btarraycmp": NONE,
    "btboolcmp": NONE,
    "btbpchar_pattern_cmp": NONE,
    "btcharcmp": NONE,
    "btequalimage": NONE,
    "btfloat48cmp": NONE,
    "btfloat4cmp": NONE,
    "btfloat84cmp": NONE,
    "btfloat8cmp": NONE,
    "btint24cmp": NONE,
    "btint28cmp": NONE,
    "btint2cmp": NONE,
    "btint42cmp": NONE,
    "btint48cmp": NONE,
    "btint4cmp": NONE,
    "btint82cmp": NONE,
    "btint84cmp": NONE,
    "btint8cmp": NONE,
    "btnamecmp": NONE,
    "btnametextcmp": NONE,
    "btoidcmp": NONE,
    "btoidvectorcmp": NONE,
    "btrecordcmp": NONE,
    "btrecordimagecmp": NONE,
    "bttext_pattern_cmp": NONE,
    "bttextcmp": NONE,
    "bttextnamecmp": NONE,
    "bttidcmp": NONE,
    "btvarstrequalimage": NONE,
    "byteacmp": NONE,
    "cash_cmp": NONE,
    "date_cmp": NONE,
    "date_cmp_timestamp": NONE,
    "date_cmp_timestamptz": NONE,
    "enum_cmp": NONE,
    "gin_cmp_tslexeme": NONE,
    "gin_compare_jsonb": NONE,
    "interval_cmp": NONE,
    "jsonb_cmp": NONE,
    "macaddr8_cmp": NONE,
    "macaddr_cmp": NONE,
    "multirange_cmp": NONE,
    "network_cmp": NONE,
    "numeric_cmp": NONE,
    "pg_lsn_cmp": NONE,
    "range_cmp": NONE,
    "time_cmp": NONE,
    "timestamp_cmp": NONE,
    "timestamp_cmp_date": NONE,
    "timestamp_cmp_timestamptz": NONE,
    "timestamptz_cmp": NONE,
    "timestamptz_cmp_date": NONE,
    "timestamptz_cmp_timestamp": NONE,
    "timetz_cmp": NONE,
    "tsquery_cmp": NONE,
    "tsvector_cmp": NONE,
    "uuid_cmp": NONE,
    "varbitcmp": NONE,
    "xid8cmp": NONE,
    # Hashes for hash indexes and hash joins.
    "hash_aclitem": NONE,
    "hash_aclitem_extended": NONE,
    "hash_array": NONE,
    "hash_array_extended": NONE,
    "hash_multirange": NONE,
    "hash_multirange_extended": NONE,
    "hash_numeric": NONE,
    "hash_numeric_extended": NONE,
    "hash_range": NONE,
    "hash_range_extended": NONE,
    "hash_record": NONE,
    "hash_record_extended": NONE,
    "hashbool": NONE,
    "hashboolextended": NONE,
    "hashbpchar": NONE,
    "hashbpcharextended": NONE,
    "hashbytea": NONE,
    "hashbyteaextended": NONE,
    "hashchar": NONE,
    "hashcharextended": NONE,
    "hashcid": NONE,
    "hashcidextended": NONE,
    "hashdate": NONE,
    "hashdateextended": NONE,
    "hashenum": NONE,
    "hashenumextended": NONE,
    "hashfloat4": NONE,
    "hashfloat4extended": NONE,
    "hashfloat8": NONE,
    "hashfloat8extended": NONE,
    "hashinet": NONE,
    "hashinetextended": NONE,
    "hashint2": NONE,
    "hashint2extended": NONE,
    "hashint4": NONE,
    "hashint4extended": NONE,
    "hashint8": NONE,
    "hashint8extended": NONE,
    "hashmacaddr": NONE,
    "hashmacaddr8": NONE,
    "hashmacaddr8extended": NONE,
    "hashmacaddrextended": NONE,
    "hashname": NONE,
    "hashnameextended": NONE,
    "hashoid": NONE,
    "hashoidextended": NONE,
    "hashoidvector": NONE,
    "hashoidvectorextended": NONE,
    "hashtext": NONE,
    "hashtextextended": NONE,
    "hashtid": NONE,
    "hashtidextended": NONE,
    "hashxid": NONE,
    "hashxid8": NONE,
    "hashxid8extended": NONE,
    "hashxidextended": NONE,
    "interval_hash": NONE,
    "interval_hash_extended": NONE,
    "jsonb_hash": NONE,
    "jsonb_hash_extended": NONE,
    "pg_lsn_hash": NONE,
    "pg_lsn_hash_extended": NONE,
    "time_hash": NONE,
    "time_hash_extended": NONE,
    "timestamp_hash": NONE,
    "timestamp_hash_extended": NONE,
    "timestamptz_hash": NONE,
    "timestamptz_hash_extended": NONE,
    "timetz_hash": NONE,
    "timetz_hash_extended": NONE,
    "uuid_hash": NONE,
    "uuid_hash_extended": NONE,
    # Type modifiers, as in varchar(10).
    "bittypmodin": NONE,
    "bpchartypmodin": NONE,
    "intervaltypmodin": NONE,
    "numerictypmodin": NONE,
    "timestamptypmodin": NONE,
    "timestamptztypmodin": NONE,
    "timetypmodin": NONE,
    "timetztypmodin": NONE,
    "varbittypmodin": NONE,
    "varchartypmodin": NONE,
    # Range support.
    "daterange_canonical": NONE,
    "daterange_subdiff": NONE,
    "int4range_canonical": NONE,
    "int4range_subdiff": NONE,
    "int8range_canonical": NONE,
    "int8range_subdiff": NONE,
    "numrange_subdiff": NONE,
    "tsrange_subdiff": NONE,
    "tstzrange_subdiff": NONE,
    # Arithmetic behind operators and aggregates.
    "dexp": NONE,
    "dlog1": NONE,
    "dlog10": NONE,
    "dround": NONE,
    "dtrunc": NONE,
    "int2_avg_accum_inv": NONE,
    "int2int4_sum": NONE,
    "int4_avg_accum_inv": NONE,
    "int4inc": NONE,
    "int8_sum": NONE,
    "int8dec": NONE,
    "int8dec_any": NONE,
    "numeric_div_trunc": NONE,
    "numeric_exp": NONE,
    "numeric_inc": NONE,
    "numeric_ln": NONE,
    "numeric_log": NONE,
    "numeric_sqrt": NONE,
    # Index, window frame and partition support.
    "gist_translate_cmptype_common": NONE,
    "spg_poly_quad_compress": NONE,
    "in_range": NONE,
    "nameconcatoid": NONE,
    "satisfies_hash_partition": NONE,  # reads the partition key from the catalog
    # Validators check a definition from the catalog.
    "amvalidate": NONE,
    "fmgr_internal_validator": NONE,
    "fmgr_sql_validator": NONE,
    "plpgsql_validator": NONE,
    "postgresql_fdw_validator": NONE,
    "fmgr_c_validator": frozenset({Effect.OPAQUE}),  # loads the function's library, which runs its init code
    # pg_upgrade's functions, which work only in binary upgrade mode. The set_next ones choose
    # the OIDs of the next objects the session creates.
    "binary_upgrade_set_next_pg_type_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_array_pg_type_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_multirange_pg_type_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_multirange_array_pg_type_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_heap_pg_class_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_heap_relfilenode": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_index_pg_class_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_index_relfilenode": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_toast_pg_class_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_toast_relfilenode": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_pg_enum_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_pg_authid_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_next_pg_tablespace_oid": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_set_record_init_privs": frozenset({Effect.WRITES_SESSION_STATE}),
    "binary_upgrade_create_empty_extension": frozenset({Effect.WRITES_CATALOG}),
    "binary_upgrade_set_missing_value": frozenset({Effect.WRITES_CATALOG}),
    "binary_upgrade_add_sub_rel_state": frozenset({Effect.WRITES_CATALOG}),
    "binary_upgrade_replorigin_advance": frozenset({Effect.WRITES_SERVER}),
    "binary_upgrade_logical_slot_has_caught_up": frozenset({Effect.READS_SERVER}),
    # These run SQL given as text.
    "query_to_xml": frozenset({Effect.OPAQUE}),
    "query_to_xmlschema": frozenset({Effect.OPAQUE}),
    "query_to_xml_and_xmlschema": frozenset({Effect.OPAQUE}),
    "ts_stat": frozenset({Effect.OPAQUE}),
    "ts_rewrite": frozenset({Effect.OPAQUE}),  # with a query given as text
}

# Functions of the pg_trgm extension (version 1.6), by name like the built-ins.
# Its operator implementations and index support functions are left unclassified.
PG_TRGM_FUNCTION_EFFECTS: dict[str, frozenset[Effect]] = {
    "similarity": NONE,
    "word_similarity": NONE,
    "strict_word_similarity": NONE,
    "show_trgm": NONE,
    "show_limit": NONE,  # reads pg_trgm.similarity_threshold
    "set_limit": frozenset({Effect.WRITES_SESSION_SETTINGS}),  # sets pg_trgm.similarity_threshold
}

# Every function looked up by name. No extension function shares a name with a built-in.
NAMED_FUNCTION_EFFECTS = FUNCTION_EFFECTS | PG_TRGM_FUNCTION_EFFECTS

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
                found = NAMED_FUNCTION_EFFECTS.get(name, {Effect.UNCLASSIFIED})
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
        # A sampling method runs its handler, so one in another schema is user code.
        case ast.RangeTableSample(method=names, repeatable=seed):
            if not _is_builtin(names):
                yield Cause(Effect.OPAQUE, node)
            else:
                method = names[-1].sval
                if method not in ("system", "bernoulli"):
                    yield Cause(Effect.UNCLASSIFIED, node)
                elif seed is None:
                    # Without REPEATABLE, the seed is drawn from the session's random state.
                    yield Cause(Effect.READS_SESSION_STATE, node)
                    yield Cause(Effect.WRITES_SESSION_STATE, node)
        case ast.IntoClause():
            # SELECT INTO creates a table and fills it.
            yield Cause(Effect.WRITES_CATALOG, node)
            yield Cause(Effect.WRITES_DATA, node)
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
            | ast.CollateClause()  # a collation names a locale, not code
            | ast.NamedArgExpr()
            | ast.ParamRef()
            | ast.GroupingFunc()
            | ast.CTESearchClause()
            | ast.CTECycleClause()
            | ast.SetToDefault()
            # XML and SQL/JSON syntax computes like the XML and JSON functions.
            | ast.RangeTableFunc()
            | ast.RangeTableFuncCol()
            | ast.XmlExpr()
            | ast.XmlSerialize()
            | ast.JsonObjectConstructor()
            | ast.JsonArrayConstructor()
            | ast.JsonArrayQueryConstructor()
            | ast.JsonAggConstructor()
            | ast.JsonObjectAgg()
            | ast.JsonArrayAgg()
            | ast.JsonKeyValue()
            | ast.JsonValueExpr()
            | ast.JsonFormat()
            | ast.JsonOutput()
            | ast.JsonReturning()
            | ast.JsonFuncExpr()
            | ast.JsonArgument()
            | ast.JsonBehavior()
            | ast.JsonIsPredicate()
            | ast.JsonParseExpr()
            | ast.JsonScalarExpr()
            | ast.JsonSerializeExpr()
            | ast.JsonTable()
            | ast.JsonTableColumn()
            | ast.JsonTablePathSpec()
        ):
            pass
        case _:
            yield Cause(Effect.UNCLASSIFIED, node)
