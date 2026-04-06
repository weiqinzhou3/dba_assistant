from dba_assistant.skills.redis_rdb_analysis import service as _service

_collect_dataset = _service._collect_dataset
_parse_rdb_rows = _service._parse_rdb_rows
_require_remote_rdb_path = _service._require_remote_rdb_path


def analyze_rdb(*args, **kwargs):
    _service._parse_rdb_rows = _parse_rdb_rows
    return _service.analyze_rdb(*args, **kwargs)

__all__ = [
    "analyze_rdb",
]
