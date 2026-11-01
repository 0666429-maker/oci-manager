"""磁盘管理：数据卷 + 启动卷，对齐 R-Bot 的扩容、提 IO、分离/挂回、删除。"""
from __future__ import annotations

from ..oci_factory import clients
from ..utils import paginate, require_confirm, to_dict


def list_volumes(compartment_id=None):
    c = clients()
    return [to_dict(x) for x in paginate(c.blockstorage.list_volumes, compartment_id=c.compartment(compartment_id))]


def create_volume(compartment_id=None, availability_domain: str = "", size_in_gbs: int = 50,
                  display_name: str = "oci-manager-volume", vpus_per_gb: int | None = None):
    import oci  # type: ignore

    if not availability_domain:
        raise ValueError("创建数据卷需要 availability_domain")
    kwargs = {}
    if vpus_per_gb is not None:
        kwargs["vpus_per_gb"] = vpus_per_gb
    details = oci.core.models.CreateVolumeDetails(
        compartment_id=clients().compartment(compartment_id),
        availability_domain=availability_domain,
        size_in_gbs=size_in_gbs,
        display_name=display_name,
        **kwargs,
    )
    return to_dict(clients().blockstorage.create_volume(details).data)


def update_volume(volume_id: str, size_in_gbs: int | None = None, vpus_per_gb: int | None = None):
    """扩容只能增大不能缩小；vpus_per_gb 用于提升 IO 性能。"""
    import oci  # type: ignore

    details = oci.core.models.UpdateVolumeDetails(
        **({"size_in_gbs": size_in_gbs} if size_in_gbs else {}),
        **({"vpus_per_gb": vpus_per_gb} if vpus_per_gb is not None else {}),
    )
    return to_dict(clients().blockstorage.update_volume(volume_id, details).data)


def delete_volume(volume_id: str, confirm: bool = False):
    require_confirm(confirm, f"删除数据卷 {volume_id}")
    clients().blockstorage.delete_volume(volume_id)
    return {"volume_id": volume_id, "deleted": True}


def list_volume_attachments(compartment_id=None, instance_id: str | None = None):
    c = clients()
    kwargs = {"compartment_id": c.compartment(compartment_id)}
    if instance_id:
        kwargs["instance_id"] = instance_id
    return [to_dict(x) for x in paginate(c.compute.list_volume_attachments, **kwargs)]


def attach_volume(instance_id: str, volume_id: str, attachment_type: str = "paravirtualized"):
    import oci  # type: ignore

    if attachment_type == "iscsi":
        details = oci.core.models.AttachIScsiVolumeDetails(
            instance_id=instance_id, volume_id=volume_id, type="iscsi"
        )
    else:
        details = oci.core.models.AttachParavirtualizedVolumeDetails(
            instance_id=instance_id, volume_id=volume_id, type="paravirtualized"
        )
    return to_dict(clients().compute.attach_volume(details).data)


def detach_volume(volume_attachment_id: str, confirm: bool = False):
    require_confirm(confirm, f"分离磁盘挂载 {volume_attachment_id}")
    clients().compute.detach_volume(volume_attachment_id)
    return {"volume_attachment_id": volume_attachment_id, "detached": True}


def update_boot_volume(boot_volume_id: str, size_in_gbs: int):
    """启动卷扩容（只能增大）。启动卷 id 可从实例的启动卷挂载里取。"""
    import oci  # type: ignore

    details = oci.core.models.UpdateBootVolumeDetails(size_in_gbs=size_in_gbs)
    return to_dict(clients().blockstorage.update_boot_volume(boot_volume_id, details).data)
