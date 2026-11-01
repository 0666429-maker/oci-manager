"""后台监控：对齐 R-Bot 的“停机自动拉起 / 阈值告警”。

规则文件 monitor_rules.json（与 run.py 同目录，可选）：
[
  {"instance_id": "ocid1.instance...", "auto_restart": true},
  {"instance_id": "ocid1.instance...", "cpu_threshold": 90}
]
- auto_restart：实例处于 STOPPED 时自动 START（只拉起，不删机、不改配）；
- cpu_threshold：最近 1 小时 CPU 均值超阈值时，若配了 Telegram Token
  则推送给 TELEGRAM_ALLOWED_USERS，否则只写日志。

本模块不自动关停任何实例（流量超额关停属于高危动作，留给人工确认）。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from pathlib import Path

from .config import settings
from .services import instances as inst
from .services import monitoring as mon

log = logging.getLogger(__name__)
RULES_FILE = Path(__file__).resolve().parent.parent / "monitor_rules.json"


def _send_telegram(text: str):
    if not settings.telegram_token or not settings.telegram_allowed_users:
        log.warning("监控告警（未推送 Telegram）：%s", text)
        return
    for uid in settings.telegram_allowed_users:
        body = json.dumps({"chat_id": uid, "text": text}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage",
            data=body, headers={"Content-Type": "application/json"},
        )
        try:
            urllib.request.urlopen(req, timeout=10)
        except Exception as exc:
            log.warning("Telegram 推送失败：%s", exc)


def check_once() -> list[str]:
    if not RULES_FILE.exists():
        return []
    rules = json.loads(RULES_FILE.read_text())
    actions = []
    for rule in rules:
        iid = rule.get("instance_id", "")
        if not iid:
            continue
        try:
            current = inst.get_instance(iid)
        except Exception as exc:
            log.warning("监控：读取实例失败 %s: %s", iid, exc)
            continue
        state = current.get("lifecycle_state")
        if rule.get("auto_restart") and state == "STOPPED":
            inst.start(iid)
            actions.append(f"已自动拉起停机实例 {iid}")
        threshold = rule.get("cpu_threshold")
        if threshold:
            try:
                series = mon.cpu_utilization(None, iid, minutes=60)
                # 取最近一个有值的聚合点做粗略判断
                values = []
                for s in series:
                    for agg in s.get("aggregated_datapoints", []) or []:
                        if agg.get("value") is not None:
                            values.append(float(agg["value"]))
                if values and max(values) > float(threshold):
                    _send_telegram(f"oci-manager 告警：实例 {iid} CPU 峰值 {max(values):.1f}% 超过 {threshold}%")
                    actions.append(f"实例 {iid} CPU 超阈值已告警")
            except Exception as exc:
                log.warning("监控：CPU 查询失败 %s: %s", iid, exc)
    return actions


def run_forever():
    log.info("监控 worker 已启动，间隔 %s 秒", settings.monitor_interval_seconds)
    while True:
        try:
            for action in check_once():
                log.info("监控动作：%s", action)
        except Exception as exc:
            log.warning("监控轮询异常：%s", exc)
        time.sleep(settings.monitor_interval_seconds)
