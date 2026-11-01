"""启动入口。

    cp .env.example .env   # 填好 OCI 密钥、面板账号
    pip install -r requirements.txt
    python run.py           # Web 面板：http://你的IP:9527
    python run.py --bot     # 同时启动 Telegram Bot（需 TELEGRAM_BOT_TOKEN）
    python run.py --monitor # 同时启动后台监控 worker（需 monitor_rules.json）

注意：本程序只在本地保存密钥，不会把密钥发给任何第三方。
"""
from __future__ import annotations

import argparse
import os
import threading

from dotenv import load_dotenv

load_dotenv()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bot", action="store_true", help="同时启动 Telegram Bot")
    parser.add_argument("--monitor", action="store_true", help="同时启动监控 worker")
    args = parser.parse_args()

    from app.api import app
    from app.config import settings

    if args.bot:
        from app.bot import run_bot

        threading.Thread(target=run_bot, daemon=True).start()
    if args.monitor:
        from app.monitor_worker import run_forever

        threading.Thread(target=run_forever, daemon=True).start()

    import uvicorn

    uvicorn.run(app, host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()
