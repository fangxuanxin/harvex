"""harvex 本地控制面板（TUI）。

基于 input() 的稳定菜单循环，不依赖 curses，兼容所有终端。
功能：列出数据源状态、触发抓取、查看数据健康、刷新列表、退出。

只用标准库，无第三方依赖。
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from .textwidth import display_width, ljust_display, truncate_display

if TYPE_CHECKING:
    # 类型提示仅在静态分析时引入，运行期不强依赖
    from ...cli.main import App

# 表头与各列宽度（显示宽度，非字节数）
_COL_SLUG = 16      # slug 列
_COL_NAME = 14      # 名称列
_COL_ENABLED = 4    # 启用列
_COL_STATUS = 6     # 最近状态列
_COL_COUNT = 6      # 最近数量列
_COL_TIME = 19      # 最近时间列（ISO 格式 YYYY-MM-DDTHH:MM:SSZ）


def _clear_screen() -> None:
    """清屏（跨平台）。"""
    os.system("cls" if os.name == "nt" else "clear")


def _status_display(status: str) -> str:
    """将状态字符串转换为带标记的显示文本。"""
    mapping = {
        "success": "成功",
        "failed":  "失败",
        "anomaly": "异常",
        "running": "运行中",
        "":        "-",
    }
    return mapping.get(status, status)


def _format_time(iso_time: str | None) -> str:
    """格式化 ISO 时间字符串，去掉毫秒和时区后缀，保留到秒。"""
    if not iso_time:
        return "-"
    # 兼容 "2025-01-01T12:00:00Z" 和 "2025-01-01T12:00:00+00:00"
    t = iso_time.replace("Z", "").split("+")[0].split(".")[0]
    return t


def render_source_table(app: "App") -> str:
    """渲染数据源状态表，返回可直接打印的字符串。

    此为纯函数：只读取 app 状态，不产生副作用，便于测试。

    Args:
        app: 已组装的 App 实例（含 registry / settings / meta）。

    Returns:
        多行字符串，包含表头分隔线和每个数据源的状态行。
    """
    # 从 meta 获取各源的最新汇总数据（slug -> summary_dict）
    summaries: dict[str, dict] = {}
    try:
        for row in app.meta.summaries():
            summaries[row["source_slug"]] = row
    except Exception:  # noqa: BLE001 数据库尚无数据时静默处理
        pass

    # 构建表头
    header_parts = [
        ljust_display("slug",     _COL_SLUG),
        ljust_display("名称",     _COL_NAME),
        ljust_display("启用", _COL_ENABLED),
        ljust_display("状态",     _COL_STATUS),
        ljust_display("最近数量", _COL_COUNT),
        ljust_display("最近时间", _COL_TIME),
    ]
    sep = "  "
    header = sep.join(header_parts)
    divider = "-" * display_width(header)

    lines: list[str] = [header, divider]

    all_sources = app.registry.all()
    if not all_sources:
        lines.append("（未发现任何数据源；确认 sources/ 目录存在且含 BaseSource 子类）")
        return "\n".join(lines)

    for cls in all_sources:
        p = cls.profile
        sc = app.settings.sources.get(p.slug)
        enabled = sc.enabled if sc else p.enabled

        # 从 summaries 取最新状态
        sm = summaries.get(p.slug, {})
        status_raw = sm.get("last_status", "")
        count_raw  = sm.get("last_job_count", 0)
        time_raw   = sm.get("last_run_at", "")

        # 各列内容（截断防止超宽）
        col_slug    = truncate_display(p.slug,                _COL_SLUG)
        col_name    = truncate_display(p.name,                _COL_NAME)
        col_enabled = ljust_display("是" if enabled else "否", _COL_ENABLED)
        col_status  = truncate_display(_status_display(status_raw), _COL_STATUS)
        col_count   = ljust_display(str(count_raw) if sm else "-", _COL_COUNT)
        col_time    = truncate_display(_format_time(time_raw), _COL_TIME)

        row_parts = [
            ljust_display(col_slug,    _COL_SLUG),
            ljust_display(col_name,    _COL_NAME),
            col_enabled,
            ljust_display(col_status,  _COL_STATUS),
            ljust_display(col_count,   _COL_COUNT),
            ljust_display(col_time,    _COL_TIME),
        ]
        lines.append(sep.join(row_parts))

    return "\n".join(lines)


def _print_header(app: "App") -> None:
    """打印面板标题和数据源表。"""
    project_dir = getattr(app.settings, "project_dir", "?")
    print(f"\nharvex 控制面板  ·  项目: {project_dir}")
    print("=" * 60)
    print(render_source_table(app))
    print()


def _print_menu() -> None:
    """打印操作菜单。"""
    print("操作：")
    print("  [r]         跑全部启用的源")
    print("  [数字/slug] 跑指定源（如：1 或 example）")
    print("  [h]         数据健康检查")
    print("  [l]         刷新列表")
    print("  [q]         退出")
    print()


def _run_all(app: "App") -> None:
    """触发全部启用的源进行抓取，打印摘要。"""
    from ...cli.main import _select_sources
    from ...core.runner import run_sources

    sources = _select_sources(app, [], run_all=True)
    if not sources:
        print("没有可运行的源。")
        return

    print(f"\n开始抓取 {len(sources)} 个源，请稍候…")
    try:
        report = run_sources(sources, app.pipeline)
        print("\n" + report.summary_line())
        for r in report.results:
            mark = {"success": "✓", "anomaly": "!", "failed": "✗"}.get(r.status, "?")
            extra = r.error or (r.health.reason if r.health else "")
            print(f"  [{mark}] {r.slug:<16} 收到 {r.received}  新增 {r.inserted}  更新 {r.updated}  总 {r.total_after}  {extra}")
    except Exception as exc:  # noqa: BLE001 运行异常不崩面板
        print(f"\n抓取异常：{exc}")


def _run_slug(app: "App", slug_or_index: str) -> None:
    """按 slug 或编号触发单个源抓取。"""
    from ...core.runner import run_sources

    all_sources = app.registry.all()

    # 尝试按编号匹配（用户输入 "1" 对应第 1 个源）
    target_cls = None
    if slug_or_index.isdigit():
        idx = int(slug_or_index) - 1
        if 0 <= idx < len(all_sources):
            target_cls = all_sources[idx]
        else:
            print(f"编号 {slug_or_index} 超出范围（共 {len(all_sources)} 个源）。")
            return
    else:
        try:
            target_cls = app.registry.get(slug_or_index)
        except Exception:
            print(f"未找到 slug='{slug_or_index}' 的数据源。")
            return

    print(f"\n开始抓取 [{target_cls.profile.slug}] {target_cls.profile.name}，请稍候…")
    try:
        report = run_sources([target_cls], app.pipeline)
        print("\n" + report.summary_line())
        for r in report.results:
            mark = {"success": "✓", "anomaly": "!", "failed": "✗"}.get(r.status, "?")
            extra = r.error or (r.health.reason if r.health else "")
            print(f"  [{mark}] {r.slug:<16} 收到 {r.received}  新增 {r.inserted}  更新 {r.updated}  总 {r.total_after}  {extra}")
    except Exception as exc:  # noqa: BLE001
        print(f"\n抓取异常：{exc}")


def _run_health(app: "App") -> None:
    """执行数据健康检查，打印结果。"""
    from ...meta.health import scan_health

    try:
        statuses = scan_health(app.meta, drop_ratio=app.settings.drop_ratio)
    except Exception as exc:  # noqa: BLE001
        print(f"\n健康检查异常：{exc}")
        return

    if not statuses:
        print("（暂无抓取历史可供体检）")
        return

    print("\n数据健康报告：")
    for s in statuses:
        mark = "!" if s.status == "anomaly" else "✓"
        print(f"  [{mark}] {s.source_slug:<16} 当前 {s.current}  上轮 {s.previous}  {s.reason}")


def run_panel(app: "App") -> None:
    """启动本地控制面板，进入交互菜单循环。

    使用 input() 而非 curses，确保终端兼容性最大化。
    捕获 Ctrl-C / EOF 优雅退出；单步异常打印后回到菜单，不崩溃。

    Args:
        app: 已组装的 App 实例。
    """
    try:
        _clear_screen()
        _print_header(app)
        _print_menu()

        while True:
            try:
                choice = input("请输入操作 > ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                # Ctrl-C 或 stdin 关闭（管道重定向时），优雅退出
                print("\n再见。")
                break

            if not choice:
                continue

            if choice == "q":
                print("再见。")
                break

            elif choice == "r":
                try:
                    _run_all(app)
                except Exception as exc:  # noqa: BLE001
                    print(f"执行异常：{exc}")

            elif choice == "h":
                try:
                    _run_health(app)
                except Exception as exc:  # noqa: BLE001
                    print(f"健康检查异常：{exc}")

            elif choice == "l":
                # 刷新列表：重新打印表格
                try:
                    _clear_screen()
                    _print_header(app)
                    _print_menu()
                    continue  # 跳过末尾的"按 Enter 继续"
                except Exception as exc:  # noqa: BLE001
                    print(f"刷新异常：{exc}")

            else:
                # 尝试当作 slug 或编号处理
                try:
                    _run_slug(app, choice)
                except Exception as exc:  # noqa: BLE001
                    print(f"执行异常：{exc}")

            # 操作完毕后暂停，让用户看清输出
            try:
                input("\n按 Enter 继续…")
            except (KeyboardInterrupt, EOFError):
                print("\n再见。")
                break

            # 刷新界面
            try:
                _clear_screen()
                _print_header(app)
                _print_menu()
            except Exception as exc:  # noqa: BLE001
                print(f"界面刷新异常：{exc}")

    except Exception as exc:  # noqa: BLE001 最外层兜底，绝不崩
        print(f"\n面板异常（已退出）：{exc}", file=sys.stderr)


__all__ = ["run_panel", "render_source_table"]
