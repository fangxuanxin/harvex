"""harvex 配置层：强类型设置对象与加载逻辑。

== config.toml 结构契约 ==

下游项目根目录放置 config.toml，结构示例：

    [http]
    timeout = 15.0
    retry_attempts = 3

    [storage]
    backup_keep = 10
    table = "records"

    [notify]
    kind = "feishu"
    url = "https://..."        # 也可写 "${FEISHU_URL}" 从 .env.local 取

    [sources.icbc]
    enabled = true
    schedule = "10:00,17:00"
    channel = "bank"
    location = "上海"          # 源特有选项，进 options

.env.local 存放敏感密钥，格式为标准 KEY=VALUE（每行一条，# 开头为注释）：

    FEISHU_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
    OPENAI_API_KEY=sk-...

config.toml 中可用 ${ENV_VAR} 占位符引用 .env.local 里的变量。

== 加载顺序 ==
1. 解析 .env.local → 注入 os.environ
2. 读取 config.toml（tomllib）
3. 展开所有字符串中的 ${VAR} 占位符
4. 构造 Settings 对象；路径字段解析为绝对路径
5. 类型/值校验失败 → 抛 ConfigError
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, field_validator, model_validator

from harvex.core.errors import ConfigError
from harvex.config.defaults import (
    DEFAULT_BACKUP_KEEP,
    DEFAULT_DATABASE_DIR,
    DEFAULT_DB_FILENAME,
    DEFAULT_DROP_RATIO,
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_LOG_DIR,
    DEFAULT_META_DB_FILENAME,
    DEFAULT_RETRY_ATTEMPTS,
    DEFAULT_TABLE,
    DEFAULT_USER_AGENT,
)

# ── 占位符替换正则 ────────────────────────────────────────
_ENV_PLACEHOLDER = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    """将字符串中的 ${VAR} 替换为当前环境变量值。

    若环境变量不存在则保留原始占位符（不静默失败，
    调用者可在后续校验中决定是否抛错）。
    """
    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    return _ENV_PLACEHOLDER.sub(_replace, value)


def _expand_dict(obj: Any) -> Any:
    """递归展开字典/列表中所有字符串值的 ${VAR} 占位符。"""
    if isinstance(obj, str):
        return _expand_env(obj)
    if isinstance(obj, dict):
        return {k: _expand_dict(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_dict(item) for item in obj]
    return obj


def _load_env_local(env_path: Path) -> None:
    """解析 .env.local 并将 KEY=VALUE 注入 os.environ。

    - 忽略空行和 # 开头的注释行。
    - 已有环境变量不被覆盖（.env.local 优先级低于真实环境）。
    """
    if not env_path.exists():
        return

    with env_path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            line = line.strip()
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                # 格式错误行：静默跳过（不影响主流程）
                continue
            key, _, raw_value = line.partition("=")
            key = key.strip()
            value = raw_value.strip()
            # 去除可选的引号包裹（单引号或双引号）
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            # 不覆盖已有的真实环境变量
            if key and key not in os.environ:
                os.environ[key] = value


# ── 子配置模型 ────────────────────────────────────────────

class SourceConfig(BaseModel):
    """单个数据源的配置。

    源特有的任意扩展字段（如 location、page_size 等）
    统一收入 options 字典，不污染顶层字段。
    """

    model_config = {"extra": "ignore"}  # 额外字段通过 model_validator 手动收集

    slug: str
    enabled: bool = True
    schedule: str | None = None
    channel: str | None = None
    # 源特有扩展选项，由 model_validator 在构造后填充
    options: dict[str, Any] = {}

    @model_validator(mode="before")
    @classmethod
    def _collect_options(cls, data: Any) -> Any:
        """将除已知字段之外的所有键收入 options。"""
        if not isinstance(data, dict):
            return data
        known = {"slug", "enabled", "schedule", "channel", "options"}
        options: dict[str, Any] = dict(data.get("options", {}))
        extras = {k: v for k, v in data.items() if k not in known}
        options.update(extras)
        result = {k: v for k, v in data.items() if k in known}
        result["options"] = options
        return result


class NotifyConfig(BaseModel):
    """通知渠道配置。"""

    url: str | None = None
    kind: str = "bark"


class HttpConfig(BaseModel):
    """HTTP 客户端基础配置。"""

    timeout: float = DEFAULT_HTTP_TIMEOUT
    retry_attempts: int = DEFAULT_RETRY_ATTEMPTS
    user_agent: str | None = DEFAULT_USER_AGENT

    @field_validator("timeout")
    @classmethod
    def _timeout_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"timeout 必须为正数，收到 {v}")
        return v

    @field_validator("retry_attempts")
    @classmethod
    def _retry_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"retry_attempts 不能为负数，收到 {v}")
        return v


class StorageConfig(BaseModel):
    """存储路径与行为配置。"""

    db_path: str
    meta_db_path: str
    backup_keep: int = DEFAULT_BACKUP_KEEP
    table: str = DEFAULT_TABLE

    @field_validator("backup_keep")
    @classmethod
    def _backup_keep_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"backup_keep 至少为 1，收到 {v}")
        return v


class Settings(BaseModel):
    """顶层配置聚合对象，由 load_settings() 构造后直接使用。"""

    # 项目根目录（绝对路径字符串）
    project_dir: str
    # 日志目录（绝对路径）
    log_dir: str
    # HTTP 配置
    http: HttpConfig = HttpConfig()
    # 存储配置
    storage: StorageConfig
    # 通知配置
    notify: NotifyConfig = NotifyConfig()
    # 各数据源配置，key 为 slug
    sources: dict[str, SourceConfig] = {}
    # 空字段丢弃比例阈值
    drop_ratio: float = DEFAULT_DROP_RATIO

    @field_validator("drop_ratio")
    @classmethod
    def _drop_ratio_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError(f"drop_ratio 须在 [0, 1] 范围内，收到 {v}")
        return v


# ── 主加载函数 ────────────────────────────────────────────

def load_settings(project_dir: str | os.PathLike[str]) -> Settings:
    """从 project_dir 加载并返回强类型 Settings 对象。

    参数
    ----
    project_dir : 项目根目录路径（绝对或相对均可，内部统一转为绝对路径）。

    返回
    ----
    Settings — 已完成路径解析和环境变量替换的配置对象。

    异常
    ----
    ConfigError — 配置文件格式非法、必填字段缺失或类型错误时抛出。
    """
    root = Path(project_dir).resolve()

    # 1. 加载 .env.local（注入 os.environ，供后续 ${VAR} 替换使用）
    _load_env_local(root / ".env.local")

    # 2. 读取 config.toml（不存在时使用空字典，走默认值）
    toml_path = root / "config.toml"
    raw: dict[str, Any] = {}
    if toml_path.exists():
        try:
            with toml_path.open("rb") as fh:
                raw = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"config.toml 解析失败：{exc}") from exc

    # 3. 递归展开所有 ${VAR} 占位符
    raw = _expand_dict(raw)

    # 4. 构造各子配置
    try:
        # ── HTTP ──
        http_cfg = HttpConfig(**raw.get("http", {}))

        # ── Storage ──
        db_dir = root / DEFAULT_DATABASE_DIR
        storage_raw = raw.get("storage", {})
        # db_path / meta_db_path 支持相对路径（相对 project_dir），默认落在 database/ 下
        db_path_raw = storage_raw.pop("db_path", DEFAULT_DB_FILENAME)
        meta_db_path_raw = storage_raw.pop("meta_db_path", DEFAULT_META_DB_FILENAME)

        db_path = _resolve_path(root, db_dir, db_path_raw)
        meta_db_path = _resolve_path(root, db_dir, meta_db_path_raw)

        storage_cfg = StorageConfig(
            db_path=str(db_path),
            meta_db_path=str(meta_db_path),
            **storage_raw,
        )

        # ── Notify ──
        notify_cfg = NotifyConfig(**raw.get("notify", {}))

        # ── Sources ──
        sources_raw: dict[str, Any] = raw.get("sources", {})
        sources: dict[str, SourceConfig] = {}
        for slug, src_data in sources_raw.items():
            if not isinstance(src_data, dict):
                raise ConfigError(f"sources.{slug} 必须是一个表（dict），收到 {type(src_data).__name__}")
            src_data = dict(src_data)
            src_data.setdefault("slug", slug)
            sources[slug] = SourceConfig(**src_data)

        # ── Log dir ──
        log_dir_raw = raw.get("log_dir", DEFAULT_LOG_DIR)
        log_dir = _resolve_path(root, root, log_dir_raw)

        # ── 顶层 Settings ──
        settings = Settings(
            project_dir=str(root),
            log_dir=str(log_dir),
            http=http_cfg,
            storage=storage_cfg,
            notify=notify_cfg,
            sources=sources,
            drop_ratio=raw.get("drop_ratio", DEFAULT_DROP_RATIO),
        )

    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError(f"配置构造失败：{exc}") from exc

    return settings


def source_enabled(settings: Settings, slug: str) -> bool:
    """判断某个数据源是否启用。

    若 slug 不在 sources 中则视为「未配置」，默认返回 True（不主动禁用）。
    """
    src = settings.sources.get(slug)
    if src is None:
        return True
    return src.enabled


# ── 工具函数 ──────────────────────────────────────────────

def _resolve_path(project_dir: Path, default_dir: Path, raw: str) -> Path:
    """将路径字符串解析为绝对路径。

    - 绝对路径原样返回。
    - 相对路径：若只含文件名（无目录分隔符），拼到 default_dir；
      否则相对于 project_dir 解析。
    """
    p = Path(raw)
    if p.is_absolute():
        return p
    # 只是一个文件名（无目录层级）：放入默认目录
    if p.parent == Path("."):
        return default_dir / p
    # 有相对层级：相对 project_dir
    return (project_dir / p).resolve()


__all__ = [
    "SourceConfig",
    "NotifyConfig",
    "HttpConfig",
    "StorageConfig",
    "Settings",
    "load_settings",
    "source_enabled",
]
