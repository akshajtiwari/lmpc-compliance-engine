"""The twelve operators. Written once, as ordinary code a person can read.

Everything specific to a rule — the numbers, the regexes, the tables — arrives as
parameters from the rulepack; nothing here reads the law directly.
"""
from ._common import (REPAIRS, fix_numerals, repair_separators, read_confidently,
                      lexicon_match)
from .presence import presence
from .format import format_regex, numeric_predicate, tiered_format
from .measure import ratio_min, clear_space, table_lookup
from .cross import (cross_field, script_allowed, mrp_uniqueness, date_plausible,
                    small_package_mark)

OPERATORS = {
    "presence": presence, "format_regex": format_regex,
    "numeric_predicate": numeric_predicate, "tiered_format": tiered_format,
    "ratio_min": ratio_min, "clear_space": clear_space,
    "table_lookup": table_lookup, "cross_field": cross_field,
    "script_allowed": script_allowed, "mrp_uniqueness": mrp_uniqueness,
    "date_plausible": date_plausible, "small_package_mark": small_package_mark,
}

__all__ = ["OPERATORS", "REPAIRS", "fix_numerals", "repair_separators",
           "read_confidently", "lexicon_match", "presence", "format_regex",
           "numeric_predicate", "tiered_format", "ratio_min", "clear_space",
           "table_lookup", "cross_field", "script_allowed", "mrp_uniqueness",
           "date_plausible", "small_package_mark"]