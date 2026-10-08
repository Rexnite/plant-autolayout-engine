"""Shared parser validation helpers."""

import json
import math
from enum import Enum
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Type, TypeVar

from wtp_autolayout.models import (
    ConstraintClassification,
    ConstraintType,
    FlowType,
    HazardLevel,
    ShapeType,
    UnitCategory,
)

from .errors import ParserError


EnumT = TypeVar("EnumT", bound=Enum)


ENUMS = {
    "category": UnitCategory,
    "shape_type": ShapeType,
    "hazard_level": HazardLevel,
    "flow_type": FlowType,
    "constraint_type": ConstraintType,
    "classification": ConstraintClassification,
}


def normalize_key(value: object) -> str:
    return str(value).strip().lower()


def normalize_columns(columns: Iterable[object]) -> Dict[str, object]:
    return {normalize_key(column): column for column in columns}


def require_sections(data: Mapping[str, Any], sections: Sequence[str]) -> None:
    missing = [section for section in sections if section not in data]
    if missing:
        raise ParserError("Missing required JSON section(s): %s" % ", ".join(missing))


def require_columns(columns: Iterable[object], required: Sequence[str], context: str) -> None:
    normalized = normalize_columns(columns)
    missing = [column for column in required if normalize_key(column) not in normalized]
    if missing:
        raise ParserError("%s missing required column(s): %s" % (context, ", ".join(missing)))


def get_value(row: Mapping[str, Any], key: str, default: Any = None) -> Any:
    for row_key, value in row.items():
        if normalize_key(row_key) == normalize_key(key):
            if is_blank(value):
                return default
            return value
    return default


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def require_value(row: Mapping[str, Any], key: str, context: str) -> Any:
    value = get_value(row, key)
    if is_blank(value):
        raise ParserError("%s missing required value: %s" % (context, key))
    return value


def parse_string(row: Mapping[str, Any], key: str, context: str, required: bool = False) -> Optional[str]:
    value = require_value(row, key, context) if required else get_value(row, key)
    if is_blank(value):
        return None
    if not isinstance(value, str):
        value = str(value)
    value = value.strip()
    if required and not value:
        raise ParserError("%s missing required value: %s" % (context, key))
    return value


def parse_number(row: Mapping[str, Any], key: str, context: str, required: bool = False) -> Optional[float]:
    value = require_value(row, key, context) if required else get_value(row, key)
    if is_blank(value):
        return None
    if isinstance(value, bool):
        raise ParserError("%s invalid numeric value for %s: %r" % (context, key, value))
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ParserError("%s invalid numeric value for %s: %r" % (context, key, value))
    if not math.isfinite(number):
        raise ParserError("%s %s must be finite: %r. Enter a real number." % (context, key, value))
    return number


def parse_int(row: Mapping[str, Any], key: str, context: str, required: bool = False) -> Optional[int]:
    value = parse_number(row, key, context, required=required)
    if value is None:
        return None
    if not float(value).is_integer():
        raise ParserError("%s invalid integer value for %s: %r" % (context, key, value))
    return int(value)


def parse_bool(row: Mapping[str, Any], key: str, context: str, default: bool = False) -> bool:
    value = get_value(row, key, default)
    if is_blank(value):
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "yes", "y", "1"):
            return True
        if normalized in ("false", "no", "n", "0"):
            return False
    raise ParserError("%s invalid boolean value for %s: %r" % (context, key, value))


def parse_enum(enum_cls: Type[EnumT], value: Any, context: str, field_name: str) -> EnumT:
    if is_blank(value):
        raise ParserError("%s missing required enum value: %s" % (context, field_name))
    try:
        if isinstance(value, enum_cls):
            return value
        return enum_cls(str(value).strip().lower())
    except ValueError:
        valid_values = ", ".join(member.value for member in enum_cls)
        raise ParserError(
            "%s invalid enum value for %s: %r. Expected one of: %s"
            % (context, field_name, value, valid_values)
        )


def parse_metadata(value: Any, context: str) -> Dict[str, Any]:
    if is_blank(value):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        if not isinstance(decoded, dict):
            raise ParserError("%s metadata JSON must decode to an object" % context)
        return decoded
    raise ParserError("%s metadata must be an object or JSON object string" % context)


def rows_from_section(section: Any, section_name: str) -> List[Mapping[str, Any]]:
    if isinstance(section, list):
        return section
    if isinstance(section, dict):
        return [section]
    raise ParserError("%s section must be an object or list of objects" % section_name)


def handle_model_error(context: str, error: Exception) -> ParserError:
    return ParserError("%s invalid model data: %s" % (context, error))
