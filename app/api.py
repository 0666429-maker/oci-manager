"""Web 面板 API（FastAPI）。

启动：python run.py  ->  http://你的IP:9527
面板账号见 .env 的 PANEL_USERNAME / PANEL_PASSWORD。
"""
from __future__ import annotations

import base64
import binascii
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import credentials as creds
from .config import settings
from .oci_factory import clients
from .services import identity as identity_svc
from .services import instances as inst
from .services import monitoring as mon
from .services import network as net
from .services import storage as store
from .services import volumes as vol

app = FastAPI(title="oci-manager", version="0.3.0")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


def _auth(request: Request):
    """面板鉴权：没设账号时放行；设了账号时要求 HTTP Basic 一致。"""
    if not settings.panel_username or not settings.panel_password:
        return True
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("basic "):
        raise HTTPException(status_code=401, detail="需要面板账号登录")
    try:
        decoded = base64.b64decode(header[6:]).decode()
        user, _, pwd = decoded.partition(":")
    except (binascii.Error, UnicodeDecodeError):
        raise HTTPException(status_code=401, detail="鉴权格式错误")
    if not (secrets.compare_digest(user, settings.panel_username)
            and secrets.compare_digest(pwd, settings.panel_password)):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    return True


@app.exception_handler(ValueError)
async def _value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def _generic_handler(request: Request, exc: Exception):
    # 不把 SDK 内部堆栈/密钥信息原样吐给前端
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.3.0", "panel_auth": bool(settings.panel_username)}


# ---------- 实例 ----------
class ActionBody(BaseModel):
    action: str


class TerminateBody(BaseModel):
    confirm: bool = False
    preserve_boot_volume: bool = False


class ShapeBody(BaseModel):
    shape: str
    ocpus: float | None = None
    memory_in_gbs: float | None = None


class LaunchBody(BaseModel):
    compartment_id: str | None = None
    availability_domain: str = ""
    shape: str = "VM.Standard.A1.Flex"
    ocpus: float = 1
    memory_in_gbs: float = 6
    image_id: str = ""
    subnet_id: str = ""
    display_name: str = "oci-manager-instance"
    assign_public_ip: bool = True
    ssh_authorized_keys: str = ""
    boot_volume_size_in_gbs: int | None = None
    preset: str | None = None
    root_password: str | None = None


@app.get("/api/instances", dependencies=[Depends(_auth)])
def api_list_instances(compartment_id: str | None = None, lifecycle_state: str | None = None):
    return inst.list_instances(compartment_id, lifecycle_state)


@app.get("/api/a1-check", dependencies=[Depends(_auth)])
def api_a1_check(compartment_id: str | None = None):
    return inst.a1_free_tier_check(compartment_id)


@app.get("/api/instances/{instance_id}", dependencies=[Depends(_auth)])
def api_get_instance(instance_id: str):
    return inst.get_instance(instance_id)


@app.post("/api/instances/{instance_id}/action", dependencies=[Depends(_auth)])
def api_instance_action(instance_id: str, body: ActionBody):
    return inst.instance_action(instance_id, body.action)


@app.post("/api/instances/{instance_id}/terminate", dependencies=[Depends(_auth)])
def api_terminate(instance_id: str, body: TerminateBody):
    return inst.terminate(instance_id, body.confirm, body.preserve_boot_volume)


@app.post("/api/instances/{instance_id}/shape", dependencies=[Depends(_auth)])
def api_shape(instance_id: str, body: ShapeBody):
    return inst.update_shape(instance_id, body.shape, body.ocpus, body.memory_in_gbs)


@app.post("/api/instances", dependencies=[Depends(_auth)])
def api_launch(body: LaunchBody):
    return inst.launch_instance(**body.model_dump())


@app.get("/api/instances/{instance_id}/vnics", dependencies=[Depends(_auth)])
def api_vnics(instance_id: str, compartment_id: str | None = None):
    return inst.instance_vnics(instance_id, compartment_id)


@app.post("/api/instances/{instance_id}/serial-console", dependencies=[Depends(_auth)])
def api_serial_console(instance_id: str, body: dict):
    return inst.create_serial_console(instance_id, body.get("public_key", ""))


# ---------- 云主机同步（给 Web SSH 用）----------
@app.get("/api/hosts/sync", dependencies=[Depends(_auth)])
def api_hosts_sync(compartment_id: str | None = None):
    """从 OCI 拉取运行中实例 + 公网 IP，生成 SSH 主机列表（不保存密钥）。"""
    hosts = []
    for item in inst.list_instances(compartment_id, lifecycle_state="RUNNING"):
        iid = item.get("id")
        try:
            vnics = inst.instance_vnics(iid, compartment_id)
        except Exception:
            vnics = []
        public_ip = next((v.get("public_ip") for v in vnics if v.get("public_ip")), "")
        hosts.append({
            "instance_id": iid,
            "display_name": item.get("display_name"),
            "shape": item.get("shape"),
            "public_ip": public_ip,
            "private_ip": vnics[0].get("private_ip") if vnics else "",
        })
    return hosts


# ---------- 网络 / IP ----------
@app.get("/api/public-ips", dependencies=[Depends(_auth)])
def api_public_ips(compartment_id: str | None = None, scope: str = "REGION", lifetime: str | None = None):
    return net.list_public_ips(compartment_id, scope, lifetime)


@app.post("/api/public-ips/change", dependencies=[Depends(_auth)])
def api_change_ip(body: dict):
    return net.change_public_ip(body["private_ip_id"], body.get("compartment_id"))


@app.post("/api/public-ips/reserved", dependencies=[Depends(_auth)])
def api_reserved(body: dict):
    return net.create_reserved_ip(body.get("compartment_id"), body.get("display_name", "oci-manager-reserved-ip"))


@app.post("/api/public-ips/{public_ip_id}/assign", dependencies=[Depends(_auth)])
def api_assign(public_ip_id: str, body: dict):
    return net.assign_reserved_ip(public_ip_id, body["private_ip_id"])


@app.post("/api/public-ips/{public_ip_id}/unassign", dependencies=[Depends(_auth)])
def api_unassign(public_ip_id: str, body: dict):
    return net.unassign_public_ip(public_ip_id, body.get("confirm", False))


@app.post("/api/public-ips/{public_ip_id}/delete", dependencies=[Depends(_auth)])
def api_delete_ip(public_ip_id: str, body: dict):
    return net.delete_public_ip(public_ip_id, body.get("confirm", False))


@app.get("/api/vcns", dependencies=[Depends(_auth)])
def api_vcns(compartment_id: str | None = None):
    return net.list_vcns(compartment_id)


@app.get("/api/subnets", dependencies=[Depends(_auth)])
def api_subnets(compartment_id: str | None = None, vcn_id: str | None = None):
    return net.list_subnets(compartment_id, vcn_id)


# ---------- 磁盘 ----------
@app.get("/api/volumes", dependencies=[Depends(_auth)])
def api_volumes(compartment_id: str | None = None):
    return vol.list_volumes(compartment_id)


@app.post("/api/volumes", dependencies=[Depends(_auth)])
def api_create_volume(body: dict):
    return vol.create_volume(
        body.get("compartment_id"), body.get("availability_domain", ""),
        int(body.get("size_in_gbs", 50)), body.get("display_name", "oci-manager-volume"),
        body.get("vpus_per_gb"),
    )


@app.post("/api/volumes/{volume_id}/update", dependencies=[Depends(_auth)])
def api_update_volume(volume_id: str, body: dict):
    return vol.update_volume(volume_id, body.get("size_in_gbs"), body.get("vpus_per_gb"))


@app.post("/api/volumes/{volume_id}/delete", dependencies=[Depends(_auth)])
def api_delete_volume(volume_id: str, body: dict):
    return vol.delete_volume(volume_id, body.get("confirm", False))


@app.post("/api/volumes/attach", dependencies=[Depends(_auth)])
def api_attach(body: dict):
    return vol.attach_volume(body["instance_id"], body["volume_id"], body.get("attachment_type", "paravirtualized"))


@app.post("/api/volumes/detach", dependencies=[Depends(_auth)])
def api_detach(body: dict):
    return vol.detach_volume(body["volume_attachment_id"], body.get("confirm", False))


@app.post("/api/boot-volumes/{boot_volume_id}/resize", dependencies=[Depends(_auth)])
def api_boot_resize(boot_volume_id: str, body: dict):
    return vol.update_boot_volume(boot_volume_id, int(body["size_in_gbs"]))


# ---------- 账号 / 配额 / 监控 ----------
@app.get("/api/compartments", dependencies=[Depends(_auth)])
def api_compartments(compartment_id: str | None = None):
    return identity_svc.list_compartments(compartment_id)


@app.get("/api/availability-domains", dependencies=[Depends(_auth)])
def api_ads(compartment_id: str | None = None):
    return identity_svc.list_availability_domains(compartment_id)


@app.get("/api/users", dependencies=[Depends(_auth)])
def api_users(compartment_id: str | None = None):
    return identity_svc.list_users(compartment_id)


@app.post("/api/users", dependencies=[Depends(_auth)])
def api_create_user(body: dict):
    return identity_svc.create_user(body.get("compartment_id"), body.get("name", ""),
                                    body.get("description", ""), body.get("email", ""))


@app.post("/api/users/{user_id}/delete", dependencies=[Depends(_auth)])
def api_delete_user(user_id: str, body: dict):
    return identity_svc.delete_user(user_id, body.get("confirm", False))


@app.get("/api/users/{user_id}/api-keys", dependencies=[Depends(_auth)])
def api_keys(user_id: str):
    return identity_svc.list_api_keys(user_id)


@app.post("/api/users/{user_id}/api-keys", dependencies=[Depends(_auth)])
def api_create_key(user_id: str, body: dict):
    return identity_svc.create_api_key(user_id, body["public_key"])


@app.get("/api/metrics/cpu", dependencies=[Depends(_auth)])
def api_cpu(compartment_id: str | None = None, instance_id: str | None = None, minutes: int = 60):
    return mon.cpu_utilization(compartment_id, instance_id, minutes)


@app.get("/api/alarms", dependencies=[Depends(_auth)])
def api_alarms(compartment_id: str | None = None):
    return mon.list_alarms(compartment_id)


@app.get("/api/limits/services", dependencies=[Depends(_auth)])
def api_services(compartment_id: str | None = None):
    return mon.list_services(compartment_id)


# ---------- 对象存储 ----------
@app.get("/api/buckets", dependencies=[Depends(_auth)])
def api_buckets(compartment_id: str | None = None):
    return store.list_buckets(compartment_id)


@app.post("/api/buckets", dependencies=[Depends(_auth)])
def api_create_bucket(body: dict):
    return store.create_bucket(body.get("compartment_id"), body.get("name", ""))


@app.post("/api/buckets/{bucket_name}/delete", dependencies=[Depends(_auth)])
def api_delete_bucket(bucket_name: str, body: dict):
    return store.delete_bucket(bucket_name, body.get("confirm", False))


@app.get("/api/buckets/{bucket_name}/objects", dependencies=[Depends(_auth)])
def api_objects(bucket_name: str, prefix: str = ""):
    return store.list_objects(bucket_name, prefix)


@app.post("/api/buckets/{bucket_name}/upload", dependencies=[Depends(_auth)])
async def api_upload(bucket_name: str, file: UploadFile = File(...)):
    data = await file.read()
    return store.upload_object(bucket_name, file.filename or "upload", data)


@app.get("/api/buckets/{bucket_name}/objects/{object_name}", dependencies=[Depends(_auth)])
def api_download(bucket_name: str, object_name: str):
    data = store.download_object(bucket_name, object_name)
    return Response(content=data, media_type="application/octet-stream")


# ---------- OCI 密钥管理（网页上传、多条统一管理）----------
# 私钥只落盘到 data/keys/（chmod 600），绝不经接口回传、下载或进 Git；
# 列表里只给 OCID 打码后的头尾。所有接口都走面板鉴权。
@app.get("/api/credentials", dependencies=[Depends(_auth)])
def api_list_credentials():
    result = creds.list_profiles()
    result["env_fallback"] = bool(settings.oci_config()) and not result["active_id"]
    return result


@app.post("/api/credentials", dependencies=[Depends(_auth)])
async def api_upload_credential(
    name: str = Form(...),
    user_ocid: str = Form(...),
    tenancy_ocid: str = Form(...),
    fingerprint: str = Form(...),
    region: str = Form(...),
    compartment_ocid: str = Form(""),
    key_file: UploadFile = File(...),
):
    data = await key_file.read()
    profile = creds.create_profile(
        name, user_ocid, tenancy_ocid, fingerprint, region,
        compartment_ocid, data,
    )
    if profile["is_active"]:
        clients().reset()
    return profile


@app.post("/api/credentials/{profile_id}/activate", dependencies=[Depends(_auth)])
def api_activate_credential(profile_id: str):
    profile = creds.set_active(profile_id)
    clients().reset()
    return profile


@app.post("/api/credentials/{profile_id}/test", dependencies=[Depends(_auth)])
def api_test_credential(profile_id: str):
    return creds.test_profile(profile_id)


@app.delete("/api/credentials/{profile_id}", dependencies=[Depends(_auth)])
def api_delete_credential(profile_id: str):
    was_active = (creds.list_profiles()["active_id"] == profile_id)
    creds.delete_profile(profile_id)
    if was_active:
        clients().reset()
    return {"ok": True}


# ---------- Web SSH（交互终端，见 ssh_terminal.py）----------
@app.websocket("/ws/ssh")
async def ws_ssh(websocket: WebSocket):
    from .ssh_terminal import handle_ssh_websocket

    await handle_ssh_websocket(websocket)


# ---------- 静态前端 ----------
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(str(WEB_DIR / "index.html"))
