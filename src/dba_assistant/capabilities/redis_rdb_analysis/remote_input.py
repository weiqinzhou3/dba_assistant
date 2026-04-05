from __future__ import annotations

from pathlib import PurePosixPath

from dba_assistant.adaptors.redis_adaptor import RedisAdaptor, RedisConnectionConfig


def discover_remote_rdb(adaptor: RedisAdaptor, connection: RedisConnectionConfig) -> dict[str, object]:
    persistence = adaptor.info(connection, section="persistence")
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


def _extract_config_value(response: dict[str, object], key: str) -> str:
    data = response.get("data")
    if not isinstance(data, dict) or key not in data:
        raise ValueError(f"Remote Redis discovery missing {key}.")

    value = data[key]
    text = str(value).strip()
    if not text:
        raise ValueError(f"Remote Redis discovery missing {key}.")
    return text
