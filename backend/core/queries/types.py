"""Types for parameterised named queries used by the data API.

A ``NamedQuery`` pairs a hardcoded SQL string with a tuple of declared
``QueryParam``s. Request query-string values are coerced to the declared
types via :func:`bind_params` and passed to DuckDB as positional ``?``
parameters — never concatenated or formatted into the SQL.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class ParamType(StrEnum):
    STRING = "string"
    INT = "int"
    DATE = "date"


@dataclass(frozen=True)
class QueryParam:
    name: str
    type: ParamType
    required: bool = True


@dataclass(frozen=True)
class NamedQuery:
    sql: str
    params: tuple[QueryParam, ...] = field(default_factory=tuple)


class ParamBindError(ValueError):
    """Raised when request params cannot be bound to a NamedQuery's declared params."""


def bind_params(query: NamedQuery, raw: Mapping[str, str]) -> list[object]:
    """Coerce raw request query-string values into a positional bind list.

    Returns values in the order declared by ``query.params``. Raises
    :class:`ParamBindError` on:
    - a key in ``raw`` that is not declared on the query (no extra-kwarg
      surface);
    - a missing required parameter;
    - a value that cannot be coerced to its declared type.
    """
    declared_names = {p.name for p in query.params}
    unknown = set(raw.keys()) - declared_names
    if unknown:
        raise ParamBindError(f"Unknown query parameter(s): {sorted(unknown)}")

    bound: list[object] = []
    for param in query.params:
        if param.name not in raw:
            if param.required:
                raise ParamBindError(f"Missing required parameter: {param.name!r}")
            bound.append(None)
            continue

        value = raw[param.name]
        try:
            bound.append(_coerce(value, param.type))
        except (ValueError, TypeError) as exc:
            raise ParamBindError(f"Invalid value for {param.name!r} (expected {param.type.value}): {exc}") from exc

    return bound


def _coerce(value: str, param_type: ParamType) -> object:
    if param_type is ParamType.STRING:
        return value
    if param_type is ParamType.INT:
        return int(value)
    if param_type is ParamType.DATE:
        return date.fromisoformat(value)
    raise ValueError(f"Unsupported param type: {param_type}")
