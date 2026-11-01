"""把 OCI SDK 模型对象转成 JSON 友好 dict 的小工具。"""
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
    # OCI SDK 模型对象：用它自带的 __dict__ / swagger_types
    if hasattr(obj, "__dict__"):
        data = {}
        for key, value in vars(obj).items():
            if key.startswith("_"):
                continue
            data[key] = to_dict(value)
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
