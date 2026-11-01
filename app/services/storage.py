"""对象存储：对齐 R-Bot Web 面板里的 Bucket / 文件管理。"""
from __future__ import annotations

from ..oci_factory import clients
from ..utils import require_confirm, to_dict


def namespace() -> str:
    return clients().object_storage.get_namespace().data


def list_buckets(compartment_id=None):
    c = clients()
    ns = namespace()
    resp = c.object_storage.list_buckets(ns, c.compartment(compartment_id))
    return [to_dict(x) for x in resp.data]


def create_bucket(compartment_id=None, name: str = "", public_access_type: str = "NoPublicAccess"):
    import oci  # type: ignore

    if not name:
        raise ValueError("创建 Bucket 需要 name")
    details = oci.object_storage.models.CreateBucketDetails(
        name=name, compartment_id=clients().compartment(compartment_id),
        public_access_type=public_access_type, storage_tier="Standard",
    )
    return to_dict(clients().object_storage.create_bucket(namespace(), details).data)


def delete_bucket(bucket_name: str, confirm: bool = False):
    require_confirm(confirm, f"删除 Bucket {bucket_name}")
    clients().object_storage.delete_bucket(namespace(), bucket_name)
    return {"bucket_name": bucket_name, "deleted": True}


def list_objects(bucket_name: str, prefix: str = ""):
    resp = clients().object_storage.list_objects(namespace(), bucket_name, prefix=prefix or None)
    return [to_dict(x) for x in resp.data.objects]


def upload_object(bucket_name: str, object_name: str, data: bytes):
    return to_dict(
        clients().object_storage.put_object(namespace(), bucket_name, object_name, data).data
    )


def download_object(bucket_name: str, object_name: str) -> bytes:
    resp = clients().object_storage.get_object(namespace(), bucket_name, object_name)
    return resp.data.content


def delete_object(bucket_name: str, object_name: str, confirm: bool = False):
    require_confirm(confirm, f"删除对象 {bucket_name}/{object_name}")
    clients().object_storage.delete_object(namespace(), bucket_name, object_name)
    return {"bucket_name": bucket_name, "object_name": object_name, "deleted": True}
