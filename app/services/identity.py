"""账号 / 用户管理：对齐 R-Bot 的用户、API 密钥、配额查询入口。

说明（避免夸大）：
- OCI 的“控制台密码、2FA”没有一个公开 SDK 调用能直接重置；
  本项目实现的是 SDK 确实支持的部分：用户增删、API 密钥增删（密钥轮换
  = 删旧建新），控制台密码/2FA 请在 OCI 控制台按官方流程处理。
"""
from __future__ import annotations

from ..oci_factory import clients
from ..utils import paginate, require_confirm, to_dict


def list_compartments(compartment_id=None):
    c = clients()
    root = c.compartment(compartment_id)
    return [to_dict(x) for x in paginate(
        c.identity.list_compartments, compartment_id=root, compartment_id_in_subtree=True
    )]


def list_availability_domains(compartment_id=None):
    c = clients()
    return [to_dict(x) for x in paginate(
        c.identity.list_availability_domains, compartment_id=c.compartment(compartment_id)
    )]


def list_users(compartment_id=None):
    c = clients()
    return [to_dict(x) for x in paginate(
        c.identity.list_users, compartment_id=c.compartment(compartment_id)
    )]


def create_user(compartment_id=None, name: str = "", description: str = "", email: str = ""):
    import oci  # type: ignore

    if not name:
        raise ValueError("创建用户需要 name")
    details = oci.identity.models.CreateUserDetails(
        compartment_id=clients().compartment(compartment_id),
        name=name, description=description, email=email or None,
    )
    return to_dict(clients().identity.create_user(details).data)


def delete_user(user_id: str, confirm: bool = False):
    require_confirm(confirm, f"删除用户 {user_id}")
    clients().identity.delete_user(user_id)
    return {"user_id": user_id, "deleted": True}


def list_api_keys(user_id: str):
    return [to_dict(x) for x in paginate(clients().identity.list_api_keys, user_id=user_id)]


def create_api_key(user_id: str, public_key: str):
    import oci  # type: ignore

    details = oci.identity.models.CreateApiKeyDetails(key=public_key)
    return to_dict(clients().identity.upload_api_key(user_id, details).data)


def delete_api_key(user_id: str, fingerprint: str, confirm: bool = False):
    require_confirm(confirm, f"删除用户 {user_id} 的 API 密钥 {fingerprint}")
    clients().identity.delete_api_key(user_id, fingerprint)
    return {"user_id": user_id, "fingerprint": fingerprint, "deleted": True}


def rotate_api_key(user_id: str, new_public_key: str, old_fingerprint: str | None = None):
    """密钥轮换：先建新密钥，成功后再删旧密钥（避免先删后建导致断连）。"""
    new_key = create_api_key(user_id, new_public_key)
    if old_fingerprint:
        delete_api_key(user_id, old_fingerprint, confirm=True)
    return new_key
