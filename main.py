"""
AstrBot 电脑控制插件

通过 AstrBot 远程控制你的电脑。
服务器端通过 SSH 隧道连接被控电脑上运行的 Agent，实现屏幕截图、鼠标键盘操作。
"""

import os
import sys
import tempfile
import traceback

PLUGIN_DIR = os.path.dirname(os.path.abspath(__file__))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

import aiohttp
from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
import astrbot.api.message_components as Comp

from ssh_tunnel import SSHTunnel

PLUGIN_NAME = "astrbot_plugin_computer_use"

HELP_TEXT = """🖥️ 电脑控制 使用帮助

基本命令:
  /cu 截图          截取屏幕画面
  /cu 点击 x y      左键点击坐标
  /cu 双击 x y      双击坐标
  /cu 右键 x y      右键点击坐标
  /cu 输入 文字     输入文字(支持中文)
  /cu 按键 key      按键(enter/esc/tab等)
  /cu 组合键 k1 k2   组合键(ctrl c)
  /cu 滚动 方向 数量 滚动屏幕(up/down 3)
  /cu 移动 x y      移动鼠标到坐标
  /cu 拖拽 x1 y1 x2 y2  拖拽

连接管理:
  /cu 状态          查看连接状态
  /cu 连接          连接被控电脑
  /cu 断开          断开连接
  /cu 帮助          显示此帮助

示例:
  /cu 截图
  /cu 点击 500 300
  /cu 输入 Hello World
  /cu 按键 enter
  /cu 组合键 ctrl c
  /cu 滚动 down 3"""

KEY_MAP = {
    "enter": "enter",
    "回车": "enter",
    "esc": "escape",
    "escape": "escape",
    "tab": "tab",
    "制表": "tab",
    "space": "space",
    "空格": "space",
    "backspace": "backspace",
    "退格": "backspace",
    "delete": "delete",
    "del": "delete",
    "删除": "delete",
    "up": "up",
    "上": "up",
    "down": "down",
    "下": "down",
    "left": "left",
    "左": "left",
    "right": "right",
    "右": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "win": "win",
    "super": "win",
    "cmd": "win",
    "ctrl": "ctrl",
    "alt": "alt",
    "shift": "shift",
    "f1": "f1", "f2": "f2", "f3": "f3", "f4": "f4",
    "f5": "f5", "f6": "f6", "f7": "f7", "f8": "f8",
    "f9": "f9", "f10": "f10", "f11": "f11", "f12": "f12",
}

SUB_CMD_MAP = {
    "截图": "screenshot", "screenshot": "screenshot", "screen": "screenshot",
    "点击": "click", "click": "click",
    "双击": "double_click", "double": "double_click", "doubleclick": "double_click",
    "右键": "right_click", "right": "right_click", "rightclick": "right_click",
    "输入": "type", "type": "type",
    "按键": "press", "press": "press", "key": "press",
    "组合键": "hotkey", "hotkey": "hotkey",
    "滚动": "scroll", "scroll": "scroll",
    "移动": "move", "move": "move",
    "拖拽": "drag", "drag": "drag",
    "状态": "status", "status": "status",
    "连接": "connect", "connect": "connect",
    "断开": "disconnect", "disconnect": "disconnect",
    "帮助": "help", "help": "help", "?": "help", "h": "help",
}


def _parse_message(text: str):
    text = text.strip()
    prefixes = ["/cu", "cu", "/电脑控制", "电脑控制", "/computer", "computer"]
    for prefix in prefixes:
        if text.lower() == prefix.lower():
            return "", ""
        if text.lower().startswith(prefix.lower() + " "):
            text = text[len(prefix) + 1:].strip()
            break

    if not text:
        return "", ""

    parts = text.split(maxsplit=1)
    sub = parts[0]
    args_str = parts[1] if len(parts) > 1 else ""
    return sub, args_str


class ComputerUsePlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.tunnel: SSHTunnel | None = None
        self._http_session: aiohttp.ClientSession | None = None

    async def initialize(self):
        cfg = self.config
        self.tunnel = SSHTunnel(
            ssh_host=cfg.get("ssh_host", ""),
            ssh_port=cfg.get("ssh_port", 22),
            ssh_username=cfg.get("ssh_username", ""),
            ssh_password=cfg.get("ssh_password", ""),
            ssh_key_path=cfg.get("ssh_key_path", ""),
            remote_port=cfg.get("agent_port", 8765),
            agent_token=cfg.get("agent_token", ""),
        )
        if cfg.get("auto_connect", False):
            try:
                await self.tunnel.connect()
                logger.info(f"[{PLUGIN_NAME}] 自动连接成功: {self.tunnel}")
            except Exception as e:
                logger.warning(f"[{PLUGIN_NAME}] 自动连接失败: {e}")
        else:
            logger.info(f"[{PLUGIN_NAME}] 插件已加载，使用 /cu 连接 来建立连接")

    async def terminate(self):
        if self._http_session:
            await self._http_session.close()
        if self.tunnel:
            await self.tunnel.disconnect()

    def _check_permission(self, event: AstrMessageEvent) -> bool:
        allowed = self.config.get("allowed_users", [])
        if not allowed:
            return True
        sender_id = str(event.get_sender_id())
        return sender_id in [str(u) for u in allowed]

    async def _get_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None or self._http_session.closed:
            timeout = aiohttp.ClientTimeout(total=self.config.get("command_timeout", 30))
            self._http_session = aiohttp.ClientSession(timeout=timeout)
        return self._http_session

    async def _ensure_connection(self) -> bool:
        if not self.tunnel:
            return False
        try:
            return await self.tunnel.ensure_connected()
        except Exception as e:
            logger.error(f"[{PLUGIN_NAME}] 连接失败: {e}")
            return False

    async def _request(self, method: str, path: str, json_data: dict | None = None) -> dict:
        if not await self._ensure_connection():
            raise RuntimeError("SSH 隧道未连接，请先执行 /cu 连接")
        url = f"{self.tunnel.base_url}{path}"
        headers = {}
        token = self.config.get("agent_token", "")
        if token:
            headers["X-Agent-Token"] = token
        session = await self._get_http_session()
        async with session.request(method, url, json=json_data, headers=headers) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                raise RuntimeError(f"Agent 错误 ({resp.status}): {error_text}")
            if resp.content_type == "image/jpeg":
                return {"_image_bytes": await resp.read()}
            return await resp.json()

    async def _save_screenshot(self, image_bytes: bytes) -> str:
        temp_dir = self.config.get("_temp_dir") or tempfile.gettempdir()
        os.makedirs(temp_dir, exist_ok=True)
        filepath = os.path.join(temp_dir, f"cu_screenshot_{int(__import__('time').time())}.jpg")
        with open(filepath, "wb") as f:
            f.write(image_bytes)
        return filepath

    # ======================== 命令入口 ========================

    @filter.command("cu", alias={"电脑控制", "computer"})
    async def cu(self, event: AstrMessageEvent):
        """电脑控制主命令"""
        sub, args_str = _parse_message(event.message_str)
        action = SUB_CMD_MAP.get(sub.lower(), SUB_CMD_MAP.get(sub, ""))

        if not action or action == "help":
            yield event.plain_result(HELP_TEXT)
            return

        if action in ("connect", "disconnect", "status"):
            async for r in self._handle_connection(event, action):
                yield r
            return

        if not self._check_permission(event):
            yield event.plain_result("⛔ 无权限使用此命令")
            return

        handlers = {
            "screenshot": self._cmd_screenshot,
            "click": self._cmd_click,
            "double_click": self._cmd_double_click,
            "right_click": self._cmd_right_click,
            "type": self._cmd_type,
            "press": self._cmd_press,
            "hotkey": self._cmd_hotkey,
            "scroll": self._cmd_scroll,
            "move": self._cmd_move,
            "drag": self._cmd_drag,
        }
        handler = handlers.get(action)
        if handler:
            try:
                async for r in handler(event, args_str):
                    yield r
            except RuntimeError as e:
                yield event.plain_result(f"⚠️ {e}")
            except Exception as e:
                logger.error(f"[{PLUGIN_NAME}] 命令执行异常: {traceback.format_exc()}")
                yield event.plain_result(f"⚠️ 执行失败: {e}")
        else:
            yield event.plain_result(HELP_TEXT)

    # ======================== 连接管理 ========================

    async def _handle_connection(self, event: AstrMessageEvent, action: str):
        if action == "status":
            if not self.tunnel:
                yield event.plain_result("⚠️ 插件未正确初始化")
                return
            status = "✅ 已连接" if self.tunnel.connected else "❌ 未连接"
            yield event.plain_result(
                f"🖥️ 电脑控制状态\n"
                f"连接: {status}\n"
                f"目标: {self.tunnel.ssh_username}@{self.tunnel.ssh_host}:{self.tunnel.ssh_port}\n"
                f"Agent端口: {self.tunnel.remote_port}\n"
                f"本地隧道: {self.tunnel.base_url or '未建立'}"
            )
            return

        if action == "connect":
            yield event.plain_result("🔄 正在连接...")
            try:
                await self.tunnel.connect()
                result = await self._request("GET", "/health")
                yield event.plain_result(
                    f"✅ 连接成功!\n"
                    f"屏幕分辨率: {result.get('screen', {}).get('width', '?')}x{result.get('screen', {}).get('height', '?')}\n"
                    f"系统: {result.get('platform', '?')}"
                )
            except Exception as e:
                yield event.plain_result(f"❌ 连接失败: {e}")
            return

        if action == "disconnect":
            await self.tunnel.disconnect()
            yield event.plain_result("✅ 已断开连接")
            return

    # ======================== 操作命令 ========================

    async def _cmd_screenshot(self, event: AstrMessageEvent, args: str):
        quality = self.config.get("screenshot_quality", 75)
        result = await self._request("GET", f"/screenshot?quality={quality}")
        image_bytes = result.get("_image_bytes")
        if not image_bytes:
            raise RuntimeError("截图返回为空")
        filepath = await self._save_screenshot(image_bytes)
        yield event.chain_result([
            Comp.Plain("🖥️ 屏幕截图:"),
            Comp.Image.fromFileSystem(filepath),
        ])

    async def _cmd_click(self, event: AstrMessageEvent, args: str):
        coords = self._parse_coords(args, expected=2)
        if not coords:
            yield event.plain_result("用法: /cu 点击 x y\n示例: /cu 点击 500 300")
            return
        result = await self._request("POST", "/click", {"x": coords[0], "y": coords[1]})
        yield event.plain_result(f"✅ 已点击 ({coords[0]}, {coords[1]})")

    async def _cmd_double_click(self, event: AstrMessageEvent, args: str):
        coords = self._parse_coords(args, expected=2)
        if not coords:
            yield event.plain_result("用法: /cu 双击 x y\n示例: /cu 双击 500 300")
            return
        result = await self._request("POST", "/double_click", {"x": coords[0], "y": coords[1]})
        yield event.plain_result(f"✅ 已双击 ({coords[0]}, {coords[1]})")

    async def _cmd_right_click(self, event: AstrMessageEvent, args: str):
        coords = self._parse_coords(args, expected=2)
        if not coords:
            yield event.plain_result("用法: /cu 右键 x y\n示例: /cu 右键 500 300")
            return
        result = await self._request("POST", "/right_click", {"x": coords[0], "y": coords[1]})
        yield event.plain_result(f"✅ 已右键点击 ({coords[0]}, {coords[1]})")

    async def _cmd_type(self, event: AstrMessageEvent, args: str):
        if not args:
            yield event.plain_result("用法: /cu 输入 文字\n示例: /cu 输入 Hello World")
            return
        result = await self._request("POST", "/type", {"text": args})
        yield event.plain_result(f"✅ 已输入文字 (长度: {result.get('length', len(args))})")

    async def _cmd_press(self, event: AstrMessageEvent, args: str):
        if not args:
            yield event.plain_result("用法: /cu 按键 key\n示例: /cu 按键 enter\n可用: enter/esc/tab/space/up/down/left/right等")
            return
        key = KEY_MAP.get(args.lower(), args.lower())
        result = await self._request("POST", "/press", {"keys": [key]})
        yield event.plain_result(f"✅ 已按键: {args}")

    async def _cmd_hotkey(self, event: AstrMessageEvent, args: str):
        if not args:
            yield event.plain_result("用法: /cu 组合键 k1 k2 ...\n示例: /cu 组合键 ctrl c\n示例: /cu 组合键 ctrl shift esc")
            return
        raw_keys = args.split()
        keys = [KEY_MAP.get(k.lower(), k.lower()) for k in raw_keys]
        result = await self._request("POST", "/hotkey", {"keys": keys})
        yield event.plain_result(f"✅ 已执行组合键: {'+'.join(keys)}")

    async def _cmd_scroll(self, event: AstrMessageEvent, args: str):
        parts = args.split() if args else []
        if not parts:
            yield event.plain_result("用法: /cu 滚动 方向 数量\n示例: /cu 滚动 down 3\n方向: up/down")
            return
        direction = parts[0].lower()
        if direction in ("上", "up"):
            direction = "up"
        elif direction in ("下", "down"):
            direction = "down"
        amount = int(parts[1]) if len(parts) > 1 else 3
        result = await self._request("POST", "/scroll", {"direction": direction, "amount": amount})
        yield event.plain_result(f"✅ 已滚动 {direction} {amount} 格")

    async def _cmd_move(self, event: AstrMessageEvent, args: str):
        coords = self._parse_coords(args, expected=2)
        if not coords:
            yield event.plain_result("用法: /cu 移动 x y\n示例: /cu 移动 500 300")
            return
        result = await self._request("POST", "/move", {"x": coords[0], "y": coords[1]})
        yield event.plain_result(f"✅ 鼠标已移动到 ({coords[0]}, {coords[1]})")

    async def _cmd_drag(self, event: AstrMessageEvent, args: str):
        coords = self._parse_coords(args, expected=4)
        if not coords:
            yield event.plain_result("用法: /cu 拖拽 x1 y1 x2 y2\n示例: /cu 拖拽 100 100 500 500")
            return
        result = await self._request("POST", "/drag", {
            "x1": coords[0], "y1": coords[1], "x2": coords[2], "y2": coords[3]
        })
        yield event.plain_result(f"✅ 已拖拽 ({coords[0]},{coords[1]}) → ({coords[2]},{coords[3]})")

    # ======================== 工具方法 ========================

    @staticmethod
    def _parse_coords(args: str, expected: int = 2) -> list[int] | None:
        try:
            parts = args.split()
            coords = [int(p) for p in parts[:expected]]
            if len(coords) == expected:
                return coords
            return None
        except (ValueError, IndexError):
            return None
