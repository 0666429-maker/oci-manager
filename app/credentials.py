"""网页上传的多 OCI 密钥统一管理。

设计原则（安全底线不变）：
- 私钥文件只存在部署本程序的机器上，永不进 Git（.gitignore 已排除
  data/、*.pem），永不通过接口回传、下载或在前端展示。
- 每个密钥是一条 profile：名字 + user / tenancy / fingerprint /
  region / 可选 compartment + 一份独立的 .pem 文件。
- 同一时刻只有一条 profile 是“当前生效”的；面板所有 OCI 调用都走
  当前 profile。切换后立即生效，不需要重启服务。
- 没有任何 profile 被激活时，行为和以前完全一样：走 .env /
  ~/.oci/config，保证旧部署不被破坏。
"""
from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
KEYS_DIR = DATA_DIR / "keys"
PROFILES_FILE = DATA_DIR / "profiles.json"

MAX_KEY_BYTES = 65536
_FINGERPRINT_RE = re.compile(r"^([0-9a-fA-F]{2}:){15}[0-9a-fA-F]{2}$")


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    KEYS_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        DATA_DIR.chmod(0o700)
        KEYS_DIR.chmod(0o700)
    except OSError:
        pass


def _load() -> dict:
    _ensure_dirs()
    if not PROFILES_FILE.exists():
        return {"active_id": None, "profiles": []}
    try:
        data = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"active_id": None, "profiles": []}
    if not isinstance(data, dict):
        return {"active_id": None, "profiles": []}
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        profiles = []
    return {"active_id": data.get("active_id"), "profiles": profiles}


def _save(data: dict) -> None:
    _ensure_dirs()
    tmp = PROFILES_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(PROFILES_FILE)
    try:
        PROFILES_FILE.chmod(0o600)
    except OSError:
        pass


def mask_ocid(value: str) -> str:
    """OCID 只露头尾：ocid1.user.oc1..****abcd，面板上够认出是哪一个就行。"""
    value = (value or "").strip()
    if len(value) <= 8:
        return "****"
    if ".." in value:
        head = value.split("..", 1)[0] + ".."
    else:
        head = value[:12]
    return f"{head}****{value[-4:]}"


def public_profile(profile: dict, active_id: str | None) -> dict:
    return {
        "id": profile["id"],
        "name": profile["name"],
        "region": profile["region"],
        "fingerprint": profile["fingerprint"],
        "user_ocid": mask_ocid(profile["user_ocid"]),
        "tenancy_ocid": mask_ocid(profile["tenancy_ocid"]),
        "compartment_ocid": mask_ocid(profile["compartment_ocid"])
        if profile.get("compartment_ocid")
        else "",
        "has_key": Path(profile["key_file"]).exists(),
        "created_at": profile.get("created_at", ""),
        "is_active": profile["id"] == active_id,
    }


def list_profiles() -> dict:
    data = _load()
    return {
        "active_id": data["active_id"],
        "profiles": [public_profile(p, data["active_id"]) for p in data["profiles"]],
    }


def get_profile(profile_id: str) -> dict | None:
    for profile in _load()["profiles"]:
        if profile["id"] == profile_id:
            return profile
    return None


def get_active_profile() -> dict | None:
    data = _load()
    active_id = data.get("active_id")
    if not active_id:
        return None
    for profile in data["profiles"]:
        if profile["id"] == active_id:
            return profile
    return None


def active_oci_config() -> dict:
    """当前 profile 转成 SDK config；没有激活的 profile 时返回空 dict。"""
    profile = get_active_profile()
    if not profile:
        return {}
    key_file = profile["key_file"]
    if not Path(key_file).exists():
        return {}
    return {
        "user": profile["user_ocid"],
        "tenancy": profile["tenancy_ocid"],
        "fingerprint": profile["fingerprint"],
        "key_file": key_file,
        "region": profile["region"],
    }


def active_compartment_id() -> str:
    profile = get_active_profile()
    return (profile or {}).get("compartment_ocid", "") or ""


def _validate_fields(name: str, user_ocid: str, tenancy_ocid: str,
                     fingerprint: str, region: str) -> None:
    if not name.strip():
        raise ValueError("请给这条密钥起个名字，例如：主号、小号1")
    if not user_ocid.startswith("ocid1.") or len(user_ocid) < 20:
        raise ValueError("用户 OCID 格式不对，应以 ocid1. 开头")
    if not tenancy_ocid.startswith("ocid1.") or len(tenancy_ocid) < 20:
        raise ValueError("租户 OCID 格式不对，应以 ocid1. 开头")
    if not _FINGERPRINT_RE.match(fingerprint.strip()):
        raise ValueError("指纹格式不对，应是 16 组十六进制、冒号分隔，如 aa:bb:…:ff")
    if not region.strip():
        raise ValueError("请填写区域，例如 ap-singapore-1")


def create_profile(name: str, user_ocid: str, tenancy_ocid: str,
                   fingerprint: str, region: str, compartment_ocid: str,
                   key_bytes: bytes) -> dict:
    name = name.strip()
    user_ocid = user_ocid.strip()
    tenancy_ocid = tenancy_ocid.strip()
    fingerprint = fingerprint.strip()
    region = region.strip()
    compartment_ocid = (compartment_ocid or "").strip()
    _validate_fields(name, user_ocid, tenancy_ocid, fingerprint, region)
    if compartment_ocid and (not compartment_ocid.startswith("ocid1.")
                             or len(compartment_ocid) < 20):
        raise ValueError("Compartment OCID 格式不对，应以 ocid1. 开头")
    if not key_bytes or len(key_bytes) > MAX_KEY_BYTES:
        raise ValueError("私钥文件为空或过大（上限 64KB）")
    try:
        key_text = key_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("私钥文件不是文本格式") from exc
    if "PRIVATE KEY" not in key_text or "-----BEGIN" not in key_text:
        raise ValueError("上传的文件不是私钥（里面应有 -----BEGIN PRIVATE KEY-----）")

    data = _load()
    if any(p["name"] == name for p in data["profiles"]):
        raise ValueError(f"名字“{name}”已经用过了，换个名字再保存")
    profile_id = secrets.token_hex(8)
    _ensure_dirs()
    key_path = KEYS_DIR / f"{profile_id}.pem"
    key_path.write_bytes(key_bytes)
    key_path.chmod(0o600)

    profile = {
        "id": profile_id,
        "name": name,
        "user_ocid": user_ocid,
        "tenancy_ocid": tenancy_ocid,
        "fingerprint": fingerprint,
        "region": region,
        "compartment_ocid": compartment_ocid,
        "key_file": str(key_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["profiles"].append(profile)
    if not data.get("active_id"):
        # 第一条就是当前生效的，上传完直接能用，不用再点一次激活。
        data["active_id"] = profile_id
    _save(data)
    return public_profile(profile, data["active_id"])


def set_active(profile_id: str) -> dict:
    data = _load()
    if not any(p["id"] == profile_id for p in data["profiles"]):
        raise ValueError("找不到这条密钥")
    data["active_id"] = profile_id
    _save(data)
    profile = get_profile(profile_id)
    assert profile is not None
    return public_profile(profile, profile_id)


def delete_profile(profile_id: str) -> None:
    data = _load()
    kept = []
    found = False
    for profile in data["profiles"]:
        if profile["id"] == profile_id:
            found = True
            try:
                Path(profile["key_file"]).unlink(missing_ok=True)
            except OSError:
                pass
        else:
            kept.append(profile)
    if not found:
        raise ValueError("找不到这条密钥")
    data["profiles"] = kept
    if data.get("active_id") == profile_id:
        data["active_id"] = None
    _save(data)


def test_profile(profile_id: str) -> dict:
    """只校验配置 + 探一次 OCI 接口，不返回任何密钥内容。

    403 不等于密钥错：很多只读受限的用户读不到 get_user，但密钥本身
    是有效的，所以把 403 单独标出来，不直接判失败。
    """
    profile = get_profile(profile_id)
    if not profile:
        raise ValueError("找不到这条密钥")
    config = active_oci_config_for(profile)
    try:
        import oci  # type: ignore

        oci.config.validate_config(config)
    except Exception as exc:  # noqa: BLE001 - 校验失败要原样告诉用户
        return {"ok": False, "probe": "config_error", "detail": str(exc)}
    try:
        import oci  # type: ignore

        client = oci.identity.IdentityClient(config)
        client.get_user(profile["user_ocid"])
        return {"ok": True, "probe": "success", "detail": "密钥有效，且能读到该用户"}
    except Exception as exc:  # noqa: BLE001 - 按状态码区分，见上文注释
        status = getattr(exc, "status", None)
        if status == 403:
            return {"ok": True, "probe": "forbidden",
                    "detail": "密钥本身有效，但该用户无权读取 get_user 接口；"
                              "换个有实例读取权限的接口（例如列出实例）再确认一次"}
        if status in (401, 404):
            return {"ok": False, "probe": "auth_failed",
                    "detail": f"OCI 拒绝了这条密钥（{status}）：请核对指纹、"
                              "私钥文件是否和控制台上那把配对"}
        return {"ok": False, "probe": "error", "detail": str(exc)}


def active_oci_config_for(profile: dict) -> dict:
    return {
        "user": profile["user_ocid"],
        "tenancy": profile["tenancy_ocid"],
        "fingerprint": profile["fingerprint"],
        "key_file": profile["key_file"],
        "region": profile["region"],
    }
