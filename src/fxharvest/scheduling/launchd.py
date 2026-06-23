"""生成 macOS launchd plist —— 把定时抓取交给系统，与 Web 进程解耦。

相比把调度寄生在 Web 服务的守护线程里（Web 一关就停、崩了不自拉起），
launchd 由系统托管：开机自启、崩溃自拉起、零额外依赖。
"""

from __future__ import annotations

from pathlib import Path


def _calendar_intervals(times: list[str]) -> str:
    """把 ['10:00','17:00'] 转成多个 <dict> 的 StartCalendarInterval 片段。"""
    blocks = []
    for t in times:
        hour, _, minute = t.partition(":")
        blocks.append(
            "        <dict>\n"
            f"            <key>Hour</key><integer>{int(hour)}</integer>\n"
            f"            <key>Minute</key><integer>{int(minute or 0)}</integer>\n"
            "        </dict>"
        )
    return "\n".join(blocks)


def generate_launchd_plist(
    *,
    label: str,
    project_dir: str | Path,
    times: list[str] | None = None,
    fxharvest_bin: str = "fxharvest",
    args: list[str] | None = None,
) -> str:
    """生成 launchd plist 文本。

    label：唯一标识，如 com.fxbox.harvest.recruit
    project_dir：下游项目目录（作为 WorkingDirectory）
    times：触发时间点列表，如 ['10:00','17:00']
    args：fxharvest 子命令参数，默认 ['run','--all']
    """
    times = times or ["10:00", "17:00"]
    args = args or ["run", "--all"]
    project_dir = Path(project_dir).resolve()
    program_args = "\n".join(
        f"        <string>{a}</string>" for a in [fxharvest_bin, *args]
    )
    log_out = project_dir / "logs" / "launchd.out.log"
    log_err = project_dir / "logs" / "launchd.err.log"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{label}</string>
    <key>ProgramArguments</key>
    <array>
{program_args}
    </array>
    <key>WorkingDirectory</key>
    <string>{project_dir}</string>
    <key>StartCalendarInterval</key>
    <array>
{_calendar_intervals(times)}
    </array>
    <key>StandardOutPath</key>
    <string>{log_out}</string>
    <key>StandardErrorPath</key>
    <string>{log_err}</string>
    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
"""


def install_hint(label: str) -> str:
    """返回安装提示文本。"""
    plist = f"~/Library/LaunchAgents/{label}.plist"
    return (
        f"# 把上面内容保存到 {plist}\n"
        f"launchctl load {plist}    # 加载\n"
        f"launchctl list | grep {label}  # 确认\n"
        f"launchctl unload {plist}  # 卸载"
    )


__all__ = ["generate_launchd_plist", "install_hint"]
