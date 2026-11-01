"""网络 / IP 管理：对齐 R-Bot 的换 IP、保留 IP、IPv4/IPv6 操作。

OCI 的公网 IP 分两种：
- EPHEMERAL（临时）：随 VNIC 释放而回收，换 IP 就是删旧临时 IP 再建新临时 IP；
- RESERVED（保留）：可长期持有、可在不同 Private IP 之间重新指派。
"""
from __future__ import annotations

from ..oci_factory import clients
from ..utils import paginate, require_confirm, to_dict


def list_public_ips(compartment_id=None, scope="REGION", lifetime=None):
    c = clients()
    kwargs = {"compartment_id": c.compartment(compartment_id), "scope": scope}
    if lifetime:
        kwargs["lifetime"] = lifetime
    return [to_dict(x) for x in paginate(c.network.list_public_ips, **kwargs)]


def list_private_ips(vnic_id: str):
    return [to_dict(x) for x in paginate(clients().network.list_private_ips, vnic_id=vnic_id)]


def get_public_ip_by_private_ip(private_ip_id: str, compartment_id=None):
    """找出绑定在某个 Private IP 上的公网 IP（可能没有）。"""
    for ip in list_public_ips(compartment_id):
        if ip.get("private_ip_id") == private_ip_id:
            return ip
    return None


def change_public_ip(private_ip_id: str, compartment_id=None):
    """换 IP：删除旧的临时公网 IP，再为同一 Private IP 分配一个新临时 IP。
    保留 IP 不会被本函数删除；如需解绑保留 IP，请用 unassign_public_ip。"""
    import oci  # type: ignore

    c = clients()
    old = get_public_ip_by_private_ip(private_ip_id, compartment_id)
    if old and old.get("lifetime") == "EPHEMERAL":
        c.network.delete_public_ip(old["id"])
    elif old and old.get("lifetime") == "RESERVED":
        raise ValueError("当前绑定的是保留 IP，请先用解绑接口处理，不要直接换 IP")
    details = oci.core.models.CreatePublicIpDetails(
        compartment_id=c.compartment(compartment_id),
        lifetime="EPHEMERAL",
        private_ip_id=private_ip_id,
    )
    return to_dict(c.network.create_public_ip(details).data)


def create_reserved_ip(compartment_id=None, display_name: str = "oci-manager-reserved-ip"):
    import oci  # type: ignore

    c = clients()
    details = oci.core.models.CreatePublicIpDetails(
        compartment_id=c.compartment(compartment_id),
        lifetime="RESERVED",
        display_name=display_name,
    )
    return to_dict(c.network.create_public_ip(details).data)


def assign_reserved_ip(public_ip_id: str, private_ip_id: str):
    import oci  # type: ignore

    details = oci.core.models.UpdatePublicIpDetails(private_ip_id=private_ip_id)
    return to_dict(clients().network.update_public_ip(public_ip_id, details).data)


def unassign_public_ip(public_ip_id: str, confirm: bool = False):
    """解绑保留 IP（不删除 IP 本体，IP 仍归你所有，可再指派）。"""
    import oci  # type: ignore

    require_confirm(confirm, f"解绑公网 IP {public_ip_id}")
    details = oci.core.models.UpdatePublicIpDetails(private_ip_id="")
    return to_dict(clients().network.update_public_ip(public_ip_id, details).data)


def delete_public_ip(public_ip_id: str, confirm: bool = False):
    require_confirm(confirm, f"删除公网 IP {public_ip_id}")
    clients().network.delete_public_ip(public_ip_id)
    return {"public_ip_id": public_ip_id, "deleted": True}


def list_vcns(compartment_id=None):
    c = clients()
    return [to_dict(x) for x in paginate(c.network.list_vcns, compartment_id=c.compartment(compartment_id))]


def list_subnets(compartment_id=None, vcn_id: str | None = None):
    c = clients()
    kwargs = {"compartment_id": c.compartment(compartment_id)}
    if vcn_id:
        kwargs["vcn_id"] = vcn_id
    return [to_dict(x) for x in paginate(c.network.list_subnets, **kwargs)]
