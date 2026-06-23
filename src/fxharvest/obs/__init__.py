"""fxharvest 可观测层（obs）。

公开接口：
- setup_logging：配置根 logger（幂等）。
- get_logger：返回携带 run_id / source 标签的 LoggerAdapter。
"""

from fxharvest.obs.logging import get_logger, setup_logging

__all__ = ["setup_logging", "get_logger"]
