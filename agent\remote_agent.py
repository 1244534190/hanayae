"""
Computer Use Remote Agent

运行在被控电脑上的本地服务，提供屏幕控制和自动化接口。
通过 SSH 隧道或局域网接受 AstrBot 插件的指令。

用法:
    python remote_agent.py [--host 127.0.0.1] [--port 8765] [--token your_secret_token]

安全建议:
    - 默认只监听 127.0.0.1，仅本机访问
    - 配合 SSH 隧道使用，不直接暴露到公网
    - 可设置 token 防止未授权访问
"""

import argparse
import base64
import io
import os
import sys
import time
from typing import Optional

import pyautogui
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from PIL import Image

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

app = FastAPI(title="Computer Use Agent", version="1.0.0")

AGENT_TOKEN: Optional[str] = None


def verify_token(x_agent_token: Optional[str] = Header(None, alias="X-Agent-Token")):
    if AGENT_TOKEN is not None and AGENT_TOKEN:
        if x_agent_token != AGENT_TOKEN:
            raise HTTPException(status_code=401, detail="Unauthorized: invalid token")


@app.middleware("http")
async def token_middleware(request: Request, call_next):
    if AGENT_TOKEN and request.url.path != "/health":
        token = request.headers.get("X-Agent-Token")
        if token != AGENT_TOKEN:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
async def health():
    try:
        size = pyautogui.size()
        return {
            "status": "ok",
            "screen": {"width": size.width, "height": size.height},
            "platform": sys.platform,
            "agent_version": "1.0.0",
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.get("/screenshot")
async def screenshot(quality: int = 75):
    try:
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=max(1, min(100, quality)))
        buf.seek(0)
        return StreamingResponse(buf, media_type="image/jpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/click")
async def click(request: Request):
    data = await request.json()
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    button = data.get("button", "left")
    clicks = int(data.get("clicks", 1))
    interval = float(data.get("interval", 0.1))
    try:
        pyautogui.click(x=x, y=y, button=button, clicks=clicks, interval=interval)
        return {"status": "ok", "action": "click", "x": x, "y": y, "button": button}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/double_click")
async def double_click(request: Request):
    data = await request.json()
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    try:
        pyautogui.doubleClick(x=x, y=y)
        return {"status": "ok", "action": "double_click", "x": x, "y": y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/right_click")
async def right_click(request: Request):
    data = await request.json()
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    try:
        pyautogui.rightClick(x=x, y=y)
        return {"status": "ok", "action": "right_click", "x": x, "y": y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/move")
async def move(request: Request):
    data = await request.json()
    x = int(data.get("x", 0))
    y = int(data.get("y", 0))
    duration = float(data.get("duration", 0.0))
    try:
        pyautogui.moveTo(x=x, y=y, duration=duration)
        return {"status": "ok", "action": "move", "x": x, "y": y}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/drag")
async def drag(request: Request):
    data = await request.json()
    x1 = int(data.get("x1", 0))
    y1 = int(data.get("y1", 0))
    x2 = int(data.get("x2", 0))
    y2 = int(data.get("y2", 0))
    duration = float(data.get("duration", 0.5))
    button = data.get("button", "left")
    try:
        pyautogui.moveTo(x1, y1)
        pyautogui.dragTo(x2, y2, duration=duration, button=button)
        return {
            "status": "ok",
            "action": "drag",
            "from": {"x": x1, "y": y1},
            "to": {"x": x2, "y": y2},
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/type")
async def type_text(request: Request):
    data = await request.json()
    text = data.get("text", "")
    interval = float(data.get("interval", 0.0))
    try:
        pyautogui.typewrite(text, interval=interval) if text.isascii() else _type_unicode(text)
        return {"status": "ok", "action": "type", "length": len(text)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def _type_unicode(text: str):
    """通过剪贴板输入非 ASCII 字符（如中文）"""
    try:
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(0.2)
    except ImportError:
        for char in text:
            pyautogui.press(char)


@app.post("/press")
async def press(request: Request):
    data = await request.json()
    keys = data.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    try:
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return {"status": "ok", "action": "press", "keys": keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/scroll")
async def scroll(request: Request):
    data = await request.json()
    direction = data.get("direction", "down")
    amount = int(data.get("amount", 3))
    x = data.get("x")
    y = data.get("y")
    try:
        clicks = amount if direction == "up" else -amount
        kwargs = {}
        if x is not None and y is not None:
            kwargs["x"] = int(x)
            kwargs["y"] = int(y)
        pyautogui.scroll(clicks, **kwargs)
        return {
            "status": "ok",
            "action": "scroll",
            "direction": direction,
            "amount": amount,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/hotkey")
async def hotkey(request: Request):
    data = await request.json()
    keys = data.get("keys", [])
    if isinstance(keys, str):
        keys = [keys]
    try:
        pyautogui.hotkey(*keys)
        return {"status": "ok", "action": "hotkey", "keys": keys}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


def main():
    global AGENT_TOKEN

    parser = argparse.ArgumentParser(description="Computer Use Remote Agent")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8765, help="监听端口 (默认 8765)")
    parser.add_argument("--token", default="", help="认证 token (可选)")
    args = parser.parse_args()

    AGENT_TOKEN = args.token or os.environ.get("AGENT_TOKEN", "")

    import uvicorn

    print(f"Computer Use Agent")
    print(f"  监听: http://{args.host}:{args.port}")
    print(f"  认证: {'已启用' if AGENT_TOKEN else '未启用'}")
    print(f"  截图: http://{args.host}:{args.port}/screenshot")
    print(f"  健康检查: http://{args.host}:{args.port}/health")
    print()

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
