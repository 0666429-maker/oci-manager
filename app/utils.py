"""把 OCI SDK 模型对象转成 JSON 友好 dict 的小工具。

关键点：OCI SDK 模型把真实字段存在 `_display_name`、`_shape` 这类
带下划线前缀的属性里，同时在 `swagger_types` 里列出公开字段名。
旧版 to_dict 跳过所有下划线属性，结果只剩 `swagger_types` /
`attribute_map` 两张元数据表，实例名、Shape、状态、OCID 全丢了，
前端列表就会出现“有几行、每格都空”的现象。本版先按
`swagger_types` 取公开属性，拿不到时再剥掉下划线前缀兜底。
"""
from __future__ import annotations

import datetime
from typing import Any, Iterable


def to_dict(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime.datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_dict(v) for v in obj]
    # OCI SDK 模型：按 swagger_types 列出的公开字段名取值。
    swagger_types = getattr(obj, "swagger_types", None)
    if isinstance(swagger_types, dict) and swagger_types:
        data = {}
        for attr in swagger_types:
            try:
                value = getattr(obj, attr, None)
            except Exception:
                continue
            data[attr] = to_dict(value)
        return data
    # 普通对象：剥掉 _ 前缀，跳过 SDK 元数据表本身。
    if hasattr(obj, "__dict__"):
        data = {}
        for key, value in vars(obj).items():
            if key in ("swagger_types", "attribute_map"):
                continue
            clean = key[1:] if key.startswith("_") else key
            data[clean] = to_dict(value)
        return data
    return str(obj)


def paginate(call, **kwargs) -> list:
    """用 OCI SDK 的分页工具把全部页拉回来；SDK 不可用时退化为单页调用。"""
    try:
        import oci  # type: ignore

        return list(oci.pagination.list_call_get_all_results(call, **kwargs).data)
    except Exception:
        resp = call(**kwargs)
        data = getattr(resp, "data", resp)
        return list(data) if isinstance(data, Iterable) else [data]


def require_confirm(confirm: bool, what: str) -> None:
    if not confirm:
        raise ValueError(f"危险操作未确认：{what}，请传 confirm=true 再次调用")
