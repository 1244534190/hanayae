"""
SSH 隧道管理

通过 SSH 端口转发，将服务器上的本地端口映射到被控电脑上的 Agent 端口。
这样 AstrBot 插件可以通过 localhost:local_port 访问远程 Agent 的 HTTP API。

使用 asyncssh 实现异步 SSH 连接，不阻塞 AstrBot 事件循环。
"""

import asyncio
import socket
from typing import Optional

import asyncssh


class SSHTunnel:
    """SSH 端口转发隧道管理器"""

    def __init__(
        self,
        ssh_host: str,
        ssh_port: int,
        ssh_username: str,
        ssh_password: str = "",
        ssh_key_path: str = "",
        remote_port: int = 8765,
        agent_token: str = "",
    ):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.ssh_key_path = ssh_key_path
        self.remote_port = remote_port
        self.agent_token = agent_token

        self._conn: Optional[asyncssh.SSHClientConnection] = None
        self._tunnel: Optional[asyncssh.SSHListener] = None
        self._local_port: int = 0
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected and self._conn is not None and not self._conn.is_closed

    @property
    def local_port(self) -> int:
        return self._local_port

    @property
    def base_url(self) -> str:
        if self._local_port:
            return f"http://127.0.0.1:{self._local_port}"
        return ""

    def _get_connect_kwargs(self) -> dict:
        kwargs = {
            "host": self.ssh_host,
            "port": self.ssh_port,
            "username": self.ssh_username,
        }
        if self.ssh_key_path:
            kwargs["client_keys"] = [self.ssh_key_path]
        elif self.ssh_password:
            kwargs["password"] = self.ssh_password
        else:
            kwargs["preferred_auth"] = ["none"]
        return kwargs

    async def connect(self) -> bool:
        """建立 SSH 连接并创建端口转发隧道"""
        try:
            await self.disconnect()
            self._local_port = self._find_free_port()
            self._conn = await asyncssh.create_connection(
                lambda: asyncssh.SSHClient(),
                **self._get_connect_kwargs(),
            )
            self._tunnel = await self._conn.forward_local_port(
                "127.0.0.1",
                self._local_port,
                "127.0.0.1",
                self.remote_port,
            )
            self._connected = True
            return True
        except Exception as e:
            self._connected = False
            self._conn = None
            raise RuntimeError(f"SSH 连接失败: {e}") from e

    async def disconnect(self):
        """关闭 SSH 连接和隧道"""
        self._connected = False
        if self._tunnel:
            try:
                self._tunnel.close()
                await self._tunnel.wait_closed()
            except Exception:
                pass
            self._tunnel = None
        if self._conn:
            try:
                self._conn.close()
                await self._conn.wait_closed()
            except Exception:
                pass
            self._conn = None
        self._local_port = 0

    async def ensure_connected(self) -> bool:
        """确保连接活跃，断线重连"""
        if self.connected:
            return True
        return await self.connect()

    @staticmethod
    def _find_free_port() -> int:
        """找到一个空闲端口"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def __repr__(self):
        status = "connected" if self.connected else "disconnected"
        return f"SSHTunnel({self.ssh_username}@{self.ssh_host}:{self.ssh_port} -> local:{self._local_port} -> remote:{self.remote_port} [{status}])"
