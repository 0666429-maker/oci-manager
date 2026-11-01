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

    def reset(self) -> None:
        """切换 / 删除 profile 后调用：下一次调用重新读配置、重建客户端。"""
        self._config = None
        for attr in ("compute", "network", "blockstorage", "identity",
                     "object_storage", "monitoring", "limits"):
            self.__dict__.pop(attr, None)

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

    @staticmethod
    def _is_placeholder(value: str) -> bool:
        """示例占位值（如 ocid1.compartment.oc1..xxxx）不是真实 OCID，
        必须当作没填处理，否则 OCI 会报 Invalid compartmentId。"""
        value = (value or "").strip()
        return not value or "xxxx" in value

    def tenancy_id(self) -> str:
        """当前租户 OCID：激活的 profile > 环境变量；占位值当作没填。"""
        tenancy = ""
        try:
            from .credentials import get_active_profile

            profile = get_active_profile()
            if profile:
                tenancy = profile.get("tenancy_ocid", "")
        except Exception:
            tenancy = ""
        if not tenancy:
            tenancy = os.environ.get("OCI_TENANCY_OCID", "")
        tenancy = (tenancy or "").strip()
        return "" if self._is_placeholder(tenancy) else tenancy

    def default_compartment_id(self) -> str:
        """已配置的默认 compartment：激活的 profile > 环境变量；
        没填或填的是占位值时返回空串，调用方再走自动获取。"""
        profile_cid = ""
        try:
            from .credentials import active_compartment_id

            profile_cid = active_compartment_id()
        except Exception:
            profile_cid = ""
        for candidate in (profile_cid, settings.compartment_id):
            candidate = (candidate or "").strip()
            if candidate and not self._is_placeholder(candidate):
                return candidate
        return ""

    def compartment(self, compartment_id: str | None) -> str:
        """单个 compartment 场景（创建、改配等）：显式传值 > 默认值；
        都没有时报错，不要悄悄默认到根 compartment，以免资源建错地方。
        列表场景请用 compartment_ids_for_listing()，它会走自动获取。"""
        cid = (compartment_id or "").strip()
        if cid and not self._is_placeholder(cid):
            return cid
        default = self.default_compartment_id()
        if default:
            return default
        raise ValueError(
            "缺少 compartment_id：请在请求里传 compartment_id，"
            "或在密钥管理里给当前 profile 填默认 compartment，"
            "或在 .env 里设置 OCI_COMPARTMENT_OCID，"
            "或在实例列表里不传 compartment（会自动从租户获取）"
        )

    def discover_compartment_ids(self) -> list[str]:
        """自动获取：以租户为根，列出所有能访问的子 compartment，
        再加上租户根 compartment 本身（实例可能直接建在根里）。"""
        tenancy = self.tenancy_id()
        if not tenancy:
            raise ValueError(
                "无法自动获取 compartment：没有租户 OCID，"
                "请确认当前 profile / .env 里填了 OCI_TENANCY_OCID，"
                "或手动填一个 compartment OCID"
            )
        ids = [tenancy]
        try:
            from .utils import paginate

            comps = paginate(
                self.identity.list_compartments,
                compartment_id=tenancy, compartment_id_in_subtree=True,
            )
        except Exception as exc:
            raise ValueError(
                "自动获取 compartment 失败："
                f"{exc}。请检查该 API 密钥是否有列出 compartment 的权限，"
                "或手动填一个 compartment OCID"
            ) from exc
        for comp in comps:
            if isinstance(comp, dict):
                cid = comp.get("id")
            else:
                cid = getattr(comp, "id", None)
            if cid and cid not in ids:
                ids.append(cid)
        return ids

    def compartment_ids_for_listing(self, compartment_id: str | None = None) -> list[str]:
        """列表场景的 compartment 集合：显式传值 > 默认值 > 自动获取全部。"""
        cid = (compartment_id or "").strip()
        if cid and not self._is_placeholder(cid):
            return [cid]
        default = self.default_compartment_id()
        if default:
            return [default]
        return self.discover_compartment_ids()


def clients() -> OciClients:
    return _SINGLETON


_SINGLETON = OciClients()
