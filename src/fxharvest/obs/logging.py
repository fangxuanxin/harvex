"""fxharvest 可观测层——日志配置与适配器。

提供两个公开函数：
- setup_logging：幂等地配置根 logger，支持控制台 + 按大小滚动的文件输出。
- get_logger：返回携带 run_id / source 标签的 LoggerAdapter，
  方便在日志行中快速定位是哪次运行、哪个数据源产生的日志。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Any, MutableMapping

# 内部标记：防止重复添加 handler
_SETUP_DONE_ATTR = "_fxharvest_setup_done"

# 日志格式：时间 | 级别 | logger 名称 | 消息
_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 单个滚动文件最大 10 MB，最多保留 5 个备份
_MAX_BYTES = 10 * 1024 * 1024
_BACKUP_COUNT = 5


def setup_logging(
    log_dir: str | os.PathLike | None = None,
    *,
    level: int = logging.INFO,
) -> None:
    """配置根 logger。幂等——重复调用不会重复添加 handler。

    Args:
        log_dir: 日志目录。若提供，则在该目录下创建 fxharvest.log 文件，
                 使用 RotatingFileHandler 按大小（10 MB）滚动，保留 5 个备份。
                 为 None 时只输出到控制台。
        level:   日志级别，默认 logging.INFO。
    """
    root_logger = logging.getLogger()

    # 幂等保护：已经配置过则直接返回
    if getattr(root_logger, _SETUP_DONE_ATTR, False):
        return

    root_logger.setLevel(level)
    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # ---- 控制台 handler ----
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # ---- 文件 handler（可选）----
    if log_dir is not None:
        log_dir_path = os.fspath(log_dir)
        os.makedirs(log_dir_path, exist_ok=True)
        log_file = os.path.join(log_dir_path, "fxharvest.log")

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 标记已完成配置
    setattr(root_logger, _SETUP_DONE_ATTR, True)


class _TaggedAdapter(logging.LoggerAdapter):
    """在每条日志消息末尾追加 [run=N source=X] 标签。

    若 run_id 或 source 为 None，则对应标签不出现。
    """

    def process(
        self,
        msg: object,
        kwargs: MutableMapping[str, Any],
    ) -> tuple[object, MutableMapping[str, Any]]:
        parts: list[str] = []
        run_id = self.extra.get("run_id")  # type: ignore[union-attr]
        source = self.extra.get("source")  # type: ignore[union-attr]

        if run_id is not None:
            parts.append(f"run={run_id}")
        if source is not None:
            parts.append(f"source={source}")

        if parts:
            tag = " ".join(parts)
            msg = f"{msg}  [{tag}]"

        return msg, kwargs


def get_logger(
    name: str = "fxharvest",
    *,
    run_id: int | None = None,
    source: str | None = None,
) -> logging.LoggerAdapter:
    """返回携带 run_id / source 标签的 LoggerAdapter。

    Args:
        name:   底层 logger 的名称，默认为 "fxharvest"。
        run_id: 当前采集流水的 ID，会以 [run=N] 形式出现在日志行。
        source: 数据源标识（如 "icbc"），会以 [source=X] 形式出现。

    Returns:
        logging.LoggerAdapter，与标准 logger 接口兼容。

    Example::

        setup_logging(log_dir="/tmp/logs")
        logger = get_logger(run_id=42, source="icbc")
        logger.info("开始抓取")
        # 输出：2024-01-01 12:00:00 | INFO     | fxharvest | 开始抓取  [run=42 source=icbc]
    """
    base_logger = logging.getLogger(name)
    extra: dict[str, Any] = {}
    if run_id is not None:
        extra["run_id"] = run_id
    if source is not None:
        extra["source"] = source
    return _TaggedAdapter(base_logger, extra)


__all__ = ["setup_logging", "get_logger"]
