"""实例管理：对齐 R-Bot 的 OCI 实例操作。

包含：列表/详情、开机、关机、重启、终止、升降配、创建实例、
快捷开机预设（AMD 微型 / ARM A1）、A1 免费额度体检、串行控制台。
"""
from __future__ import annotations

from ..oci_factory import clients
from ..utils import paginate, require_confirm, to_dict

# R-Bot 面板里的快捷开机预设（仅作默认值，用户可在调用时覆盖）
PRESETS = {
    "amd_micro": {
        "shape": "VM.Standard.E2.1.Micro",
        "ocpus": 1,
        "memory_in_gbs": 1,
        "note": "AMD 免费微型实例",
    },
    "arm_a1": {
        "shape": "VM.Standard.A1.Flex",
        "ocpus": 4,
        "memory_in_gbs": 24,
        "note": "ARM A1 免费额度上限：4 OCPU / 24GB（按租户汇总计算）",
    },
    "arm_a1_2c12g": {
        "shape": "VM.Standard.A1.Flex",
        "ocpus": 2,
        "memory_in_gbs": 12,
        "note": "ARM A1：2 OCPU / 12GB（免费额度的一半，还能再开一台 2核12G）",
    },
}


def build_root_password_user_data(root_password: str) -> str:
    """给 root 密码登录生成 cloud-init user_data（base64）。

    密码本身不以明文进实例元数据：先在服务端算出 SHA-512 哈希，
    再由 cloud-init 写入 root 账号并开启 SSH 密码登录、允许 root 登录。
    生成后原始密码即被丢弃，不存在面板或服务端任何文件里。
    """
    import base64
    import crypt

    if len(root_password) < 8:
        raise ValueError("root 密码至少 8 位，请换一个更长的密码")
    hashed = crypt.crypt(root_password, crypt.mksalt(crypt.METHOD_SHA512))
    cloud_config = f"""#cloud-config
ssh_pwauth: true
users:
  - name: root
    lock_passwd: false
    hashed_passwd: '{hashed}'
runcmd:
  - |
    sed -i -e 's/^#*PermitRootLogin.*/PermitRootLogin yes/' -e 's/^#*PasswordAuthentication.*/PasswordAuthentication yes/' /etc/ssh/sshd_config
    grep -q '^PermitRootLogin' /etc/ssh/sshd_config || echo 'PermitRootLogin yes' >> /etc/ssh/sshd_config
    grep -q '^PasswordAuthentication' /etc/ssh/sshd_config || echo 'PasswordAuthentication yes' >> /etc/ssh/sshd_config
    systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || service ssh restart 2>/dev/null || true
"""
    return base64.b64encode(cloud_config.encode("utf-8")).decode("ascii")


def list_instances(compartment_id=None, lifecycle_state=None):
    """列出实例：不传 compartment 时自动获取全部 compartment 再汇总，
    不用手动填 compartment OCID；显式传值或配了默认值时只查那一个。"""
    c = clients()
    out = []
    for cid in c.compartment_ids_for_listing(compartment_id):
        kwargs = {"compartment_id": cid}
        if lifecycle_state:
            kwargs["lifecycle_state"] = lifecycle_state
        out.extend(to_dict(x) for x in paginate(c.compute.list_instances, **kwargs))
    return out


def get_instance(instance_id: str):
    return to_dict(clients().compute.get_instance(instance_id).data)


def instance_action(instance_id: str, action: str):
    """action: START / STOP / RESET（重启）/ SOFTRESET（软重启）。"""
    action = action.upper()
    if action not in {"START", "STOP", "RESET", "SOFTRESET"}:
        raise ValueError(f"不支持的实例动作：{action}")
    resp = clients().compute.instance_action(instance_id, action)
    return to_dict(resp.data) if getattr(resp, "data", None) else {"instance_id": instance_id, "action": action}


def start(instance_id: str):
    return instance_action(instance_id, "START")


def stop(instance_id: str):
    return instance_action(instance_id, "STOP")


def reboot(instance_id: str):
    return instance_action(instance_id, "RESET")


def terminate(instance_id: str, confirm: bool = False, preserve_boot_volume: bool = False):
    require_confirm(confirm, f"终止实例 {instance_id}")
    clients().compute.terminate_instance(
        instance_id, preserve_boot_volume=preserve_boot_volume
    )
    return {"instance_id": instance_id, "terminated": True}


def update_shape(instance_id: str, shape: str, ocpus: float | None = None, memory_in_gbs: float | None = None):
    """升降配。注意：OCI 要求实例先关机再改 Shape，改完再开机。"""
    import oci  # type: ignore

    details_kwargs = {"shape": shape}
    if ocpus is not None or memory_in_gbs is not None:
        details_kwargs["shape_config"] = oci.core.models.UpdateInstanceShapeConfigDetails(
            ocpus=ocpus, memory_in_gbs=memory_in_gbs
        )
    details = oci.core.models.UpdateInstanceDetails(**details_kwargs)
    return to_dict(clients().compute.update_instance(instance_id, details).data)


def launch_instance(
    compartment_id=None,
    availability_domain: str = "",
    shape: str = "VM.Standard.A1.Flex",
    ocpus: float = 1,
    memory_in_gbs: float = 6,
    image_id: str = "",
    subnet_id: str = "",
    display_name: str = "oci-manager-instance",
    assign_public_ip: bool = True,
    ssh_authorized_keys: str = "",
    boot_volume_size_in_gbs: int | None = None,
    preset: str | None = None,
    root_password: str | None = None,
):
    """创建实例。传 preset 可一键套用快捷预设（含 arm_a1_2c12g）；
    传 root_password 则通过 cloud-init 开启 root 密码登录（见
    build_root_password_user_data，密码只算哈希、不存明文）。"""
    import oci  # type: ignore

    if preset and preset in PRESETS:
        p = PRESETS[preset]
        shape, ocpus, memory_in_gbs = p["shape"], p["ocpus"], p["memory_in_gbs"]
    if not all([availability_domain, image_id, subnet_id]):
        raise ValueError("创建实例需要 availability_domain、image_id、subnet_id")

    source = oci.core.models.InstanceSourceViaImageDetails(
        source_type="image", image_id=image_id,
        **({"boot_volume_size_in_gbs": boot_volume_size_in_gbs} if boot_volume_size_in_gbs else {}),
    )
    vnic = oci.core.models.CreateVnicDetails(
        subnet_id=subnet_id, assign_public_ip=assign_public_ip
    )
    metadata = {}
    if ssh_authorized_keys:
        metadata["ssh_authorized_keys"] = ssh_authorized_keys
    if root_password:
        metadata["user_data"] = build_root_password_user_data(root_password)
    details = oci.core.models.LaunchInstanceDetails(
        compartment_id=clients().compartment(compartment_id),
        availability_domain=availability_domain,
        shape=shape,
        display_name=display_name,
        source_details=source,
        create_vnic_details=vnic,
        shape_config=oci.core.models.LaunchInstanceShapeConfigDetails(
            ocpus=ocpus, memory_in_gbs=memory_in_gbs
        ),
        metadata=metadata,
    )
    return to_dict(clients().compute.launch_instance(details).data)


def instance_vnics(instance_id: str, compartment_id=None):
    """实例关联的 VNIC（含公网 IP），用于“云主机同步到 SSH 列表”和换 IP。"""
    c = clients()
    attachments = paginate(
        c.compute.list_vnic_attachments,
        compartment_id=c.compartment(compartment_id),
        instance_id=instance_id,
    )
    out = []
    for att in attachments:
        vnic_id = att.vnic_id if hasattr(att, "vnic_id") else att.get("vnic_id")
        vnic = c.network.get_vnic(vnic_id).data
        out.append(to_dict(vnic))
    return out


def a1_free_tier_check(compartment_id=None):
    """A1 配置体检：汇总所有运行中 A1 Flex 实例的 OCPU/内存，
    超出免费额度（4 OCPU / 24GB）时列出超标实例；本函数不自动删机。"""
    instances = list_instances(compartment_id, lifecycle_state="RUNNING")
    total_ocpu = total_mem = 0.0
    a1_instances = []
    for inst in instances:
        if inst.get("shape") == "VM.Standard.A1.Flex":
            cfg = inst.get("shape_config") or {}
            ocpu = float(cfg.get("ocpus") or 0)
            mem = float(cfg.get("memory_in_gbs") or 0)
            total_ocpu += ocpu
            total_mem += mem
            a1_instances.append(inst)
    return {
        "a1_instances": a1_instances,
        "total_ocpus": total_ocpu,
        "total_memory_in_gbs": total_mem,
        "free_tier_ocpus": 4,
        "free_tier_memory_in_gbs": 24,
        "over_ocpu": total_ocpu > 4,
        "over_memory": total_mem > 24,
    }


def create_serial_console(instance_id: str, public_key: str):
    """串行控制台：SSH 连不上时的救援入口（需提供 SSH 公钥）。"""
    import oci  # type: ignore

    details = oci.core.models.CreateInstanceConsoleConnectionDetails(
        instance_id=instance_id, public_key=public_key
    )
    return to_dict(clients().compute.create_instance_console_connection(details).data)
