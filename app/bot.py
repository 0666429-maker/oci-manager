"""Telegram Bot：把 R-Bot 的常用 OCI 命令搬过来，只做 OCI。

命令：
  /start /help /instances /instance <id> /start_vm <id> /stop_vm <id>
  /reboot_vm <id> /terminate_vm <id>（Bot 端终止仍需二次确认：先发命令，
  机器人回“请再发一次确认”，第二次才真正执行）
  /change_ip <private_ip_id> /volumes /a1check /quota

安全：TELEGRAM_ALLOWED_USERS 为空时不限制，强烈建议填上自己的 user id。
"""
from __future__ import annotations

import asyncio
import logging

from .config import settings
from .services import instances as inst
from .services import network as net
from .services import volumes as vol

log = logging.getLogger(__name__)
_pending_terminate: set[str] = set()


def _allowed(update) -> bool:
    if not settings.telegram_allowed_users:
        return True
    return update.effective_user.id in settings.telegram_allowed_users


def _fmt_instances(items, limit: int = 20) -> str:
    lines = []
    for it in items[:limit]:
        lines.append(
            f"{it.get('display_name')} | {it.get('shape')} | "
            f"{it.get('lifecycle_state')} | {it.get('id')}"
        )
    return "\n".join(lines) or "没有实例"


async def _run(fn, *args, **kwargs):
    return await asyncio.to_thread(fn, *args, **kwargs)


def build_app():
    from telegram import Update  # type: ignore
    from telegram.ext import Application, CommandHandler, ContextTypes  # type: ignore

    async def guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
        if not _allowed(update):
            await update.message.reply_text("未授权用户。")
            return False
        return True

    async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        await update.message.reply_text(
            "oci-manager（仅 OCI）已就绪。\n"
            "/instances 查看实例\n/start_vm <id> /stop_vm <id> /reboot_vm <id>\n"
            "/terminate_vm <id>（需发两次确认）\n"
            "/change_ip <private_ip_id> 换 IP\n/volumes 查看磁盘\n/a1check A1 免费额度体检"
        )

    async def instances_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        items = await _run(inst.list_instances, None, "RUNNING")
        await update.message.reply_text(_fmt_instances(items))

    async def _action(update, context, fn, verb: str):
        if not await guard(update, context):
            return
        if not context.args:
            await update.message.reply_text(f"用法：/{verb} <instance_id>")
            return
        result = await _run(fn, context.args[0])
        await update.message.reply_text(f"已执行 {verb}：{result.get('instance_id', context.args[0])}")

    async def terminate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        if not context.args:
            await update.message.reply_text("用法：/terminate_vm <instance_id>")
            return
        iid = context.args[0]
        if iid not in _pending_terminate:
            _pending_terminate.add(iid)
            await update.message.reply_text(
                f"确认终止 {iid} 吗？请再发一次 /terminate_vm {iid} 确认。"
            )
            return
        _pending_terminate.discard(iid)
        await _run(inst.terminate, iid, True)
        await update.message.reply_text(f"已终止 {iid}")

    async def change_ip_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        if not context.args:
            await update.message.reply_text("用法：/change_ip <private_ip_id>")
            return
        result = await _run(net.change_public_ip, context.args[0])
        await update.message.reply_text(f"换 IP 完成，新 IP：{result.get('ip_address')}")

    async def volumes_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        items = await _run(vol.list_volumes, None)
        lines = [f"{v.get('display_name')} | {v.get('size_in_gbs')}GB | {v.get('lifecycle_state')} | {v.get('id')}"
                 for v in items[:20]]
        await update.message.reply_text("\n".join(lines) or "没有数据卷")

    async def a1check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not await guard(update, context):
            return
        r = await _run(inst.a1_free_tier_check, None)
        await update.message.reply_text(
            f"A1 实例 {len(r['a1_instances'])} 台，"
            f"合计 {r['total_ocpus']} OCPU / {r['total_memory_in_gbs']} GB，"
            f"免费额度 4 OCPU / 24GB，超标：OCPU={r['over_ocpu']} 内存={r['over_memory']}"
        )

    async def start_vm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _action(update, context, inst.start, "start_vm")

    async def stop_vm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _action(update, context, inst.stop, "stop_vm")

    async def reboot_vm_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await _action(update, context, inst.reboot, "reboot_vm")

    app = Application.builder().token(settings.telegram_token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", start))
    app.add_handler(CommandHandler("instances", instances_cmd))
    app.add_handler(CommandHandler("start_vm", start_vm_cmd))
    app.add_handler(CommandHandler("stop_vm", stop_vm_cmd))
    app.add_handler(CommandHandler("reboot_vm", reboot_vm_cmd))
    app.add_handler(CommandHandler("terminate_vm", terminate_cmd))
    app.add_handler(CommandHandler("change_ip", change_ip_cmd))
    app.add_handler(CommandHandler("volumes", volumes_cmd))
    app.add_handler(CommandHandler("a1check", a1check_cmd))
    return app


def run_bot():
    if not settings.telegram_token:
        raise RuntimeError("未设置 TELEGRAM_BOT_TOKEN，跳过 Bot 启动")
    build_app().run_polling()
