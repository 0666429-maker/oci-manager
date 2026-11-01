"""配置：优先读 .env / 环境变量，缺失时回落到标准 OCI config 文件。

OCI 官方 SDK 的配置键名就是 user / tenancy / fingerprint / key_file / region，
本模块只是把环境变量翻译成这套键名，不发明新格式。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


@dataclass
class Settings:
    host: str = field(default_factory=lambda: _env("APP_HOST", "0.0.0.0"))
    port: int = int(_env("APP_PORT", "9527") or 9527)
    panel_username: str = field(default_factory=lambda: _env("PANEL_USERNAME"))
    panel_password: str = field(default_factory=lambda: _env("PANEL_PASSWORD"))
    app_secret: str = field(default_factory=lambda: _env("APP_SECRET", "change-me"))
    compartment_id: str = field(default_factory=lambda: _env("OCI_COMPARTMENT_OCID"))
    region: str = field(default_factory=lambda: _env("OCI_REGION"))
    telegram_token: str = field(default_factory=lambda: _env("TELEGRAM_BOT_TOKEN"))
    telegram_allowed_users: set[int] = field(default_factory=set)
    monitor_interval_seconds: int = int(
        _env("MONITOR_INTERVAL_SECONDS", "300") or 300
    )

    def __post_init__(self) -> None:
        raw = _env("TELEGRAM_ALLOWED_USERS")
        if raw:
            self.telegram_allowed_users = {
                int(x) for x in raw.split(",") if x.strip().isdigit()
            }

    def oci_config(self) -> dict:
        """返回可直接传给 oci 客户端的 config dict。

        优先级：网页上传并激活的 profile > 环境变量；两者都没有时
        返回空 dict，让调用方用 oci.config.from_file() 读 ~/.oci/config。
        """
        try:
            from .credentials import active_oci_config

            profile_config = active_oci_config()
        except Exception:
            profile_config = {}
        if profile_config:
            return profile_config
        user = _env("OCI_USER_OCID")
        tenancy = _env("OCI_TENANCY_OCID")
        fingerprint = _env("OCI_FINGERPRINT")
        key_file = _env("OCI_PRIVATE_KEY_PATH")
        region = self.region
        if all([user, tenancy, fingerprint, key_file, region]):
            return {
                "user": user,
                "tenancy": tenancy,
                "fingerprint": fingerprint,
                "key_file": os.path.expanduser(key_file),
                "region": region,
            }
        return {}


settings = Settings()
