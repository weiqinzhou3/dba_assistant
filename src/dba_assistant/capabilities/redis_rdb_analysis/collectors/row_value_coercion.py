from __future__ import annotations


_NULLISH_STRINGS = {"", "none", "null"}
_FALSE_STRINGS = {"0", "false"}
_TRUE_STRINGS = {"1", "true"}


def _coerce_required_int(value: object, field_name: str) -> int:
    if _is_nullish(value) or isinstance(value, bool):
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}")
    try:
        return int(_strip_string(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid integer value for {field_name}: {value!r}") from exc


def _coerce_optional_int(value: object) -> int | None:
    if _is_nullish(value):
        return None
    if isinstance(value, bool):
        raise ValueError(f"Invalid optional integer value: {value!r}")
    try:
        return int(_strip_string(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid optional integer value: {value!r}") from exc


def _coerce_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value in (0, 1):
            return bool(value)
        raise ValueError(f"Invalid boolean value: {value!r}")
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _NULLISH_STRINGS | _FALSE_STRINGS:
            return False
        if normalized in _TRUE_STRINGS:
            return True
    raise ValueError(f"Invalid boolean value: {value!r}")


def _is_nullish(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and value.strip().lower() in _NULLISH_STRINGS


def _strip_string(value: object) -> object:
    if isinstance(value, str):
        return value.strip()
    return value
