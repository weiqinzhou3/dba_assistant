"""SSH adaptor for narrow remote file fetch support."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import paramiko


@dataclass(frozen=True)
class SSHConnectionConfig:
    host: str
    port: int = 22
    username: str | None = None
    password: str | None = None


class SSHAdaptor:
    def __init__(self, client_factory: Callable[[], paramiko.SSHClient] = paramiko.SSHClient) -> None:
        self._client_factory = client_factory

    def fetch_file(self, config: SSHConnectionConfig, remote_path: str, local_path: Path) -> Path:
        client = self._client_factory()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            config.host,
            port=config.port,
            username=config.username,
            password=config.password,
        )
        try:
            sftp = client.open_sftp()
            try:
                sftp.get(remote_path, str(local_path))
            finally:
                sftp.close()
        finally:
            client.close()
        return local_path
