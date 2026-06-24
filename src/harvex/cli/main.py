"""harvex 命令行入口。

把配置、源发现、各层组装成可运行的应用，并暴露子命令：

    harvex list                 列出已发现的数据源
    harvex run --all            跑一轮全部启用的源
    harvex run icbc apple       跑指定源
    harvex health               数据健康检查（归零/骤降）
    harvex gen-launchd          生成 macOS launchd plist
    harvex gen-cron             生成 crontab 行
    harvex web                  启动只读浏览 UI（需 [web]）
    harvex tui                  启动本地控制面板（需 [tui]）

约定：在下游项目根目录（含 config.toml / sources/）运行，或用 --project 指定。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from ..config.settings import Settings, load_settings
from ..core.pipeline import Pipeline
from ..core.record import HarvestRecord
from ..core.registry import SourceRegistry
from ..core.runner import run_sources
from ..meta.health import scan_health
from ..meta.metadata_db import MetadataDatabase
from ..net.http_client import HttpClient
from ..net.retry import RetryPolicy
from ..notify.webhook import WebhookNotifier
from ..obs.logging import get_logger, setup_logging
from ..storage.sqlite_sink import SQLiteSink


@dataclass
class App:
    """组装好的运行期应用：配置 + 注册表 + 各层 + pipeline。"""

    settings: Settings
    registry: SourceRegistry
    pipeline: Pipeline
    sink: SQLiteSink
    meta: MetadataDatabase
    http: HttpClient

    def close(self) -> None:
        for closer in (self.http, self.meta, self.sink):
            try:
                closer.close()
            except Exception:  # noqa: BLE001 关闭尽力而为
                pass


def _resolve_record_model(registry: SourceRegistry) -> type[HarvestRecord]:
    """从已发现的源里取业务记录模型（本项目所有源共用一个业务表/模型）。"""
    models = {cls.record_model for cls in registry.all()}
    if not models:
        return HarvestRecord
    if len(models) > 1:
        get_logger().warning("发现多个记录模型，使用首个：%s", sorted(m.__name__ for m in models))
    return registry.all()[0].record_model


def build_app(project_dir: str | Path) -> App:
    """从项目目录组装应用：加载配置 → 发现源 → 构建各层 → pipeline。"""
    project_dir = Path(project_dir).resolve()
    settings = load_settings(project_dir)
    setup_logging(settings.log_dir)

    registry = SourceRegistry()
    sources_dir = project_dir / "sources"
    if sources_dir.is_dir():
        registry.discover_dir(sources_dir)

    record_model = _resolve_record_model(registry)
    http = HttpClient(
        timeout=settings.http.timeout,
        user_agent=settings.http.user_agent,
        retry=RetryPolicy(attempts=settings.http.retry_attempts),
    )
    # 写库的轮级备份由 runner 统一触发，故 sink 自身关掉每写即备份
    sink = SQLiteSink(
        settings.storage.db_path, record_model,
        table=settings.storage.table, backup=False, backup_keep=settings.storage.backup_keep,
    )
    meta = MetadataDatabase(settings.storage.meta_db_path)
    notifier = WebhookNotifier.from_config({"url": settings.notify.url, "kind": settings.notify.kind})
    source_config = {slug: dict(sc.options, **{"schedule": sc.schedule, "channel": sc.channel})
                     for slug, sc in settings.sources.items()}
    pipeline = Pipeline(
        sink=sink, meta=meta, http=http,
        drop_ratio=settings.drop_ratio, notifier=notifier, source_config=source_config,
    )
    return App(settings=settings, registry=registry, pipeline=pipeline, sink=sink, meta=meta, http=http)


def _select_sources(app: App, slugs: list[str], run_all: bool):
    """根据命令行参数挑选要跑的源（兼顾 config 的 enabled 软开关）。"""
    settings = app.settings
    if run_all or not slugs:
        chosen = []
        for cls in app.registry.enabled():
            sc = settings.sources.get(cls.profile.slug)
            if sc is not None and not sc.enabled:
                continue  # config 显式禁用
            chosen.append(cls)
        return chosen
    return [app.registry.get(s) for s in slugs]


# ---------------- 子命令 ----------------

def cmd_list(app: App, args) -> int:
    if not app.registry.all():
        print("（未发现任何数据源；确认 sources/ 目录存在且含 BaseSource 子类）")
        return 0
    print(f"已发现 {len(app.registry.all())} 个数据源：")
    for cls in app.registry.all():
        p = cls.profile
        sc = app.settings.sources.get(p.slug)
        enabled = (sc.enabled if sc else p.enabled)
        flag = "✓" if enabled else "✗"
        print(f"  [{flag}] {p.slug:<16} {p.name}  (channel={p.channel or '-'}, schedule={p.schedule or '-'})")
    return 0


def cmd_run(app: App, args) -> int:
    sources = _select_sources(app, args.slugs, args.all)
    if not sources:
        print("没有可运行的源。")
        return 1
    report = run_sources(sources, app.pipeline, max_workers=args.workers)
    print("\n" + report.summary_line())
    for r in report.results:
        mark = {"success": "✓", "anomaly": "!", "failed": "✗"}.get(r.status, "?")
        extra = r.error or (r.health.reason if r.health else "")
        print(f"  [{mark}] {r.slug:<16} 收到{r.received} 新增{r.inserted} 更新{r.updated} 总{r.total_after} {extra}")
    return 0 if not report.failed else 2


def cmd_health(app: App, args) -> int:
    statuses = scan_health(app.meta, drop_ratio=app.settings.drop_ratio)
    if not statuses:
        print("（暂无抓取历史可供体检）")
        return 0
    anomalies = [s for s in statuses if s.status == "anomaly"]
    for s in statuses:
        mark = "!" if s.status == "anomaly" else "✓"
        print(f"  [{mark}] {s.source_slug:<16} 当前{s.current} 上轮{s.previous} {s.reason}")
    return 0 if not anomalies else 2


def cmd_gen_launchd(app: App, args) -> int:
    from ..scheduling.launchd import generate_launchd_plist, install_hint
    times = args.at.split(",") if args.at else ["10:00", "17:00"]
    label = args.label or "com.harvex"
    print(generate_launchd_plist(label=label, project_dir=app.settings.project_dir, times=times))
    print("\n" + install_hint(label), file=sys.stderr)
    return 0


def cmd_gen_cron(app: App, args) -> int:
    from ..scheduling.cron import generate_cron_line
    times = args.at.split(",") if args.at else ["10:00", "17:00"]
    print(generate_cron_line(project_dir=app.settings.project_dir, times=times))
    return 0


def cmd_web(app: App, args) -> int:
    try:
        from ..extras.web.service import serve
    except ImportError as error:
        print(f"Web 扩展不可用：{error}", file=sys.stderr)
        return 1
    serve(app, host=args.host, port=args.port)
    return 0


def cmd_tui(app: App, args) -> int:
    try:
        from ..extras.tui.panel import run_panel
    except ImportError as error:
        print(f"TUI 扩展不可用：{error}", file=sys.stderr)
        return 1
    run_panel(app)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="harvex", description="本地数据采集框架 CLI")
    parser.add_argument("--project", default=".", help="项目目录（默认当前目录）")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出数据源")

    p_run = sub.add_parser("run", help="跑一轮抓取")
    p_run.add_argument("slugs", nargs="*", help="指定源 slug；省略则跑全部")
    p_run.add_argument("--all", action="store_true", help="跑全部启用的源")
    p_run.add_argument("--workers", type=int, default=4, help="并发数")

    sub.add_parser("health", help="数据健康检查")

    p_ld = sub.add_parser("gen-launchd", help="生成 launchd plist")
    p_ld.add_argument("--at", help="触发时间点，逗号分隔，如 10:00,17:00")
    p_ld.add_argument("--label", help="launchd Label")

    p_cron = sub.add_parser("gen-cron", help="生成 crontab 行")
    p_cron.add_argument("--at", help="触发时间点，逗号分隔")

    p_web = sub.add_parser("web", help="启动只读浏览 UI")
    p_web.add_argument("--host", default="127.0.0.1")
    p_web.add_argument("--port", type=int, default=8765)

    sub.add_parser("tui", help="启动本地控制面板")
    return parser


_HANDLERS = {
    "list": cmd_list, "run": cmd_run, "health": cmd_health,
    "gen-launchd": cmd_gen_launchd, "gen-cron": cmd_gen_cron,
    "web": cmd_web, "tui": cmd_tui,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    app = build_app(args.project)
    try:
        return _HANDLERS[args.command](app, args)
    finally:
        app.close()


if __name__ == "__main__":
    raise SystemExit(main())
