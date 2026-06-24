"""config 层测试：load_settings 读取、环境变量替换、缺省与非法处理。"""

from __future__ import annotations

import pytest

from harvex.core.errors import ConfigError
from harvex.config.settings import load_settings

_CONFIG = """\
[http]
timeout = 20.0
retry_attempts = 5

[storage]
backup_keep = 7
table = "jobs"

[notify]
kind = "feishu"
url = "${FEISHU_URL}"

[sources.icbc]
enabled = true
schedule = "10:00,17:00"
channel = "bank"
location = "上海"
"""


def test_load_full_config(tmp_path):
    (tmp_path / "config.toml").write_text(_CONFIG, encoding="utf-8")
    (tmp_path / ".env.local").write_text("FEISHU_URL=https://hook.example\n", encoding="utf-8")

    s = load_settings(tmp_path)
    assert s.http.timeout == 20.0 and s.http.retry_attempts == 5
    assert s.storage.table == "jobs" and s.storage.backup_keep == 7
    assert s.notify.url == "https://hook.example"        # ${FEISHU_URL} 被替换
    src = s.sources["icbc"]
    assert src.enabled and src.schedule == "10:00,17:00" and src.channel == "bank"
    assert src.options.get("location") == "上海"          # 源特有键进 options
    # 路径基于 project_dir 解析为绝对
    assert s.storage.db_path.startswith(str(tmp_path))


def test_missing_config_uses_defaults(tmp_path):
    s = load_settings(tmp_path)        # 无 config.toml
    assert s.http.timeout > 0
    assert s.sources == {}


def test_invalid_type_raises(tmp_path):
    (tmp_path / "config.toml").write_text(
        '[http]\ntimeout = "not-a-number"\n', encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        load_settings(tmp_path)
