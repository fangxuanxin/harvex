"""meta 子包：元数据流水层 + 数据健康检查。

公开接口：
- MetadataDatabase：抓取流水数据库（crawl_runs / source_summary）。
- HealthStatus：单次健康检查结果数据类。
- check_health：对单个源做实时健康检查。
- scan_health：对所有已知源批量离线体检。
"""

from .health import HealthStatus, check_health, scan_health
from .metadata_db import MetadataDatabase

__all__ = [
    "MetadataDatabase",
    "HealthStatus",
    "check_health",
    "scan_health",
]
