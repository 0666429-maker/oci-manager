"""OCI 客户端工厂：懒加载，避免在没有装 oci SDK / 没有配密钥时 import 就炸掉。

用法：
    from app.oci_factory import clients
    compute = clients().compute
"""
from __future__ import annotations

import os
from functools import cached_property

from .config import settings


class OciClients:
    def __init__(self) -> None:
        self._config: dict | None = None

    @property
    def config(self) -> dict:
        if self._config is None:
            try:
                import oci  # type: ignore
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError(
                    "未安装 oci SDK，请先执行 pip install -r requirements.txt"
                ) from exc
            env_config = settings.oci_config()
            if env_config:
                self._config = env_config
            else:
                config_file = os.path.expanduser(
                    os.environ.get("OCI_CONFIG_FILE", "~/.oci/config")
                )
                profile = os.environ.get("OCI_CONFIG_PROFILE", "DEFAULT")
                self._config = oci.config.from_file(config_file, profile)
            oci.config.validate_config(self._config)
            if settings.region and "region" not in self._config:
                self._config["region"] = settings.region
        return self._config

    @cached_property
    def compute(self):
        import oci  # type: ignore

        return oci.core.ComputeClient(self.config)

    @cached_property
    def network(self):
        import oci  # type: ignore

        return oci.core.VirtualNetworkClient(self.config)

    @cached_property
    def blockstorage(self):
        import oci  # type: ignore

        return oci.core.BlockstorageClient(self.config)

    @cached_property
    def identity(self):
        import oci  # type: ignore

        return oci.identity.IdentityClient(self.config)

    @cached_property
    def object_storage(self):
        import oci  # type: ignore

        return oci.object_storage.ObjectStorageClient(self.config)

    @cached_property
    def monitoring(self):
        import oci  # type: ignore

        return oci.monitoring.MonitoringClient(self.config)

    @cached_property
    def limits(self):
        import oci  # type: ignore

        return oci.limits.LimitsClient(self.config)

    def compartment(self, compartment_id: str | None) -> str:
        """调用方没传 compartment 时，优先用环境变量里的默认值。"""
        cid = (compartment_id or settings.compartment_id or "").strip()
        if not cid:
            raise ValueError(
                "缺少 compartment_id：请在请求里传 compartment_id，"
                "或在 .env 里设置 OCI_COMPARTMENT_OCID"
            )
        return cid


def clients() -> OciClients:
    return _SINGLETON


_SINGLETON = OciClients()
