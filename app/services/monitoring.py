"""监控与配额：实例 CPU 指标、告警、服务限额。

注意：OCI Monitoring 的指标查询需要 namespace + MQL 查询语句，
这里用最常用的 oci_computeagent / CpuUtilization；内存指标需要
实例上装了 Management Agent 才会上报，没有 Agent 时会返回空数据，
这是 OCI 本身的限制，不是本程序的 bug。
"""
from __future__ import annotations

import datetime

from ..oci_factory import clients
from ..utils import to_dict


def _window(minutes: int = 60):
    end = datetime.datetime.now(datetime.timezone.utc)
    start = end - datetime.timedelta(minutes=minutes)
    return start, end


def cpu_utilization(compartment_id=None, instance_id: str | None = None, minutes: int = 60):
    import oci  # type: ignore

    c = clients()
    start, end = _window(minutes)
    query = "CpuUtilization[1m].mean()"
    if instance_id:
        query = f'CpuUtilization[1m]{{resourceId="{instance_id}"}}.mean()'
    details = oci.monitoring.models.SummarizeMetricsDataDetails(
        namespace="oci_computeagent", query=query, start_time=start, end_time=end
    )
    resp = c.monitoring.summarize_metrics_data(c.compartment(compartment_id), details)
    return [to_dict(x) for x in resp.data]


def list_alarms(compartment_id=None):
    c = clients()
    resp = c.monitoring.list_alarms(compartment_id=c.compartment(compartment_id))
    return [to_dict(x) for x in resp.data]


def create_cpu_alarm(compartment_id=None, instance_id: str = "", threshold: float = 90.0,
                     display_name: str = "oci-manager-cpu-alarm"):
    """CPU 超阈值告警（OCI 原生 Alarm，需配合通知主题使用才有推送）。"""
    import oci  # type: ignore

    if not instance_id:
        raise ValueError("创建告警需要 instance_id")
    c = clients()
    details = oci.monitoring.models.CreateAlarmDetails(
        display_name=display_name,
        compartment_id=c.compartment(compartment_id),
        metric_compartment_id=c.compartment(compartment_id),
        namespace="oci_computeagent",
        query=f'CpuUtilization[1m]{{resourceId="{instance_id}"}}.mean() > {threshold}',
        severity="CRITICAL",
        is_enabled=True,
    )
    return to_dict(c.monitoring.create_alarm(details).data)


def list_services(compartment_id=None):
    c = clients()
    resp = c.limits.list_services(compartment_id=c.compartment(compartment_id))
    return [to_dict(x) for x in resp.data]


def resource_availability(compartment_id=None, service_name: str = "", limit_name: str = "",
                          availability_domain: str | None = None):
    c = clients()
    kwargs = {}
    if availability_domain:
        kwargs["availability_domain"] = availability_domain
    resp = c.limits.get_resource_availability(
        service_name, limit_name, c.compartment(compartment_id), **kwargs
    )
    return to_dict(resp.data)
