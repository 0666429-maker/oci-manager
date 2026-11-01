"""Web SSH 交互终端：浏览器 <-> 本程序 <-> 目标主机。

协议（WebSocket 首条消息必须是 JSON 连接参数，之后的消息分两种）：
  连接：{"host": "1.2.3.4", "username": "opc", "password": "...", "key_path": "~/.ssh/id_rsa"}
        password 和 key_path 二选一；key_path 指本程序所在机器上的私钥路径，
        不经过浏览器上传，避免私钥落到浏览器缓存里。
  输入：{"type": "input", "data": "ls\n"}
  尺寸：{"type": "resize", "cols": 120, "rows": 40}
输出：服务器直接回发终端原始字节（文本）。

安全提醒：这个终端等于目标主机的 shell 入口，务必只在可信网络 +
面板账号保护下使用，不要把本程序直接暴露到公网。
"""
from __future__ import annotations

import asyncio
import json
import os


async def handle_ssh_websocket(websocket):
    await websocket.accept()
    try:
        raw = await websocket.receive_text()
        params = json.loads(raw)
    except Exception:
        await websocket.close(code=1008)
        return

    host = params.get("host", "")
    username = params.get("username", "opc")
    password = params.get("password") or None
    key_path = params.get("key_path") or None
    port = int(params.get("port", 22) or 22)
    if not host:
        await websocket.send_text("\r\n[oci-manager] 缺少 host\r\n")
        await websocket.close()
        return

    try:
        import paramiko  # type: ignore
    except ImportError:
        await websocket.send_text("\r\n[oci-manager] 未安装 paramiko\r\n")
        await websocket.close()
        return

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        kwargs = {"hostname": host, "port": port, "username": username,
                  "password": password, "timeout": 15}
        if key_path:
            kwargs["key_filename"] = os.path.expanduser(key_path)
        # 在线程里做阻塞连接，避免卡住事件循环
        await asyncio.to_thread(client.connect, **kwargs)
        channel = client.invoke_shell(term="xterm-256color", width=120, height=40)
        channel.settimeout(0.1)
    except Exception as exc:
        await websocket.send_text(f"\r\n[oci-manager] SSH 连接失败：{exc}\r\n")
        await websocket.close()
        return

    async def _pump_output():
        while not channel.closed:
            try:
                data = await asyncio.to_thread(channel.recv, 4096)
            except Exception:
                data = b""
            if data:
                try:
                    await websocket.send_text(data.decode(errors="replace"))
                except Exception:
                    break
            else:
                await asyncio.sleep(0.05)

    pump = asyncio.create_task(_pump_output())
    try:
        while True:
            msg = await websocket.receive_text()
            try:
                payload = json.loads(msg)
            except json.JSONDecodeError:
                channel.send(msg)
                continue
            if payload.get("type") == "resize":
                try:
                    channel.resize_pty(
                        width=int(payload.get("cols", 120)),
                        height=int(payload.get("rows", 40)),
                    )
                except Exception:
                    pass
            elif payload.get("type") == "input":
                channel.send(payload.get("data", ""))
    except Exception:
        pass
    finally:
        pump.cancel()
        try:
            channel.close()
        except Exception:
            pass
        client.close()
