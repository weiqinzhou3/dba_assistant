from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


@dataclass(slots=True)
class RemoteRedisDiscoveryError(RuntimeError):
    kind: str
    stage: str
    message: str

    def __str__(self) -> str:
        return f"preflight failed at {self.stage}: {self.message}"


def discover_remote_rdb(adaptor: RedisAdaptor, connection: RedisConnectionConfig) -> dict[str, object]:
    ping = adaptor.ping(connection)
    _validate_ping_response(ping)

    persistence = adaptor.info(connection, section="persistence")
    _validate_info_response(persistence, stage="info(persistence)")

    directory = adaptor.config_get(connection, pattern="dir")
    filename = adaptor.config_get(connection, pattern="dbfilename")

    dir_value = _extract_config_value(directory, "dir")
    filename_value = _extract_config_value(filename, "dbfilename")

    return {
        "lastsave": persistence.get("rdb_last_save_time"),
        "bgsave_in_progress": persistence.get("rdb_bgsave_in_progress"),
        "redis_dir": dir_value,
        "dbfilename": filename_value,
        "rdb_path": str(PurePosixPath(dir_value) / filename_value),
        "rdb_path_source": "discovered",
        "requires_confirmation": True,
    }


def _validate_ping_response(response: object) -> None:
    payload = _require_mapping(response, stage="ping")
    if payload.get("available") is False:
        _raise_probe_failure(payload, stage="ping")

    ok = payload.get("ok")
    if ok is False or ok is None:
        raise RemoteRedisDiscoveryError(
            kind="malformed_response",
            stage="ping",
            message="malformed_response: PING returned an unexpected payload.",
        )


def _validate_info_response(response: object, *, stage: str) -> None:
    payload = _require_mapping(response, stage=stage)
    if payload.get("available") is False:
        _raise_probe_failure(payload, stage=stage)


def _extract_config_value(response: object, key: str) -> str:
    stage = f"config_get({key})"
    payload = _require_mapping(response, stage=stage)
    if payload.get("available") is False:
        _raise_probe_failure(payload, stage=stage)

    data = payload.get("data")
    if not isinstance(data, dict):
        raise RemoteRedisDiscoveryError(
            kind="malformed_response",
            stage=stage,
            message=(
                f"malformed_response: Redis {stage} returned an unexpected payload for '{key}'."
            ),
        )

    if key not in data:
        raise RemoteRedisDiscoveryError(
            kind=f"missing_{key}",
            stage=stage,
            message=f"missing {key}: Redis {stage} returned no '{key}' value.",
        )

    value = data[key]
    text = str(value).strip()
    if not text:
        raise RemoteRedisDiscoveryError(
            kind=f"missing_{key}",
            stage=stage,
            message=f"missing {key}: Redis {stage} returned an empty '{key}' value.",
        )
    return text


def _require_mapping(response: object, *, stage: str) -> dict[str, object]:
    if isinstance(response, dict):
        return response
    raise RemoteRedisDiscoveryError(
        kind="malformed_response",
        stage=stage,
        message=f"malformed_response: Redis {stage} returned a non-dictionary payload.",
    )


def _raise_probe_failure(response: dict[str, object], *, stage: str) -> None:
    error = response.get("error")
    if not isinstance(error, dict):
        raise RemoteRedisDiscoveryError(
            kind="malformed_response",
            stage=stage,
            message=f"malformed_response: Redis {stage} reported failure without an error payload.",
        )

    kind = str(error.get("kind") or "unknown_error").strip() or "unknown_error"
    raw_message = str(error.get("message") or "").strip() or "No error message returned by Redis."
    raise RemoteRedisDiscoveryError(
        kind=kind,
        stage=stage,
        message=_format_probe_failure_message(stage=stage, kind=kind, raw_message=raw_message),
    )


def _format_probe_failure_message(*, stage: str, kind: str, raw_message: str) -> str:
    if kind == "permission_denied" and stage.startswith("config_get("):
        key = stage[len("config_get("):-1]
        return f"permission_denied: CONFIG GET {key} not permitted by ACL ({raw_message})"
    if kind == "authentication_failed":
        return f"authentication_failed: {raw_message}"
    if kind == "permission_denied":
        return f"permission_denied: {raw_message}"
    if kind == "connection_failed":
        return f"connection_failed: {raw_message}"
    if kind == "timeout":
        return f"timeout: {raw_message}"
    if kind == "command_unavailable":
        return f"command_unavailable: {raw_message}"
    if kind == "malformed_response":
        return f"malformed_response: {raw_message}"
    return f"{kind}: {raw_message}"
