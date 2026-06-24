"""生成 crontab 行（Linux / 通用场景；macOS 推荐用 launchd）。"""

from __future__ import annotations

from pathlib import Path


def generate_cron_line(
    *,
    project_dir: str | Path,
    times: list[str] | None = None,
    harvex_bin: str = "harvex",
    args: list[str] | None = None,
) -> str:
    """生成一条或多条 crontab 行。

    times 形如 ['10:00','17:00'] → 合并成一个 `分 时,时` 的 cron 表达式（若分钟相同）。
    分钟不同则分行输出。
    """
    times = times or ["10:00", "17:00"]
    args = args or ["run", "--all"]
    project_dir = Path(project_dir).resolve()
    cmd = f"cd {project_dir} && {harvex_bin} {' '.join(args)} >> {project_dir / 'logs' / 'cron.log'} 2>&1"

    by_minute: dict[int, list[int]] = {}
    for t in times:
        hour, _, minute = t.partition(":")
        by_minute.setdefault(int(minute or 0), []).append(int(hour))

    lines = []
    for minute, hours in sorted(by_minute.items()):
        hour_expr = ",".join(str(h) for h in sorted(hours))
        lines.append(f"{minute} {hour_expr} * * * {cmd}")
    return "\n".join(lines)


__all__ = ["generate_cron_line"]
