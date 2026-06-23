"""extras/web/service.py：只读 Web 浏览服务，基于标准库 http.server。

设计原则：
- 零第三方依赖：只用 http.server / json / pathlib / urllib.parse 等标准库。
- 只读：拒绝所有非 GET 请求（405）。
- 路由简洁：手工字符串匹配，不引入任何路由框架。
- 线程安全：ThreadingHTTPServer 多线程接收，app 对象只读使用（SQLite WAL 模式可并发读）。
"""

from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlparse

if TYPE_CHECKING:
    from ...cli.main import App

# 静态资源目录：extras/web/assets/
_ASSETS_DIR = Path(__file__).parent / "assets"

# /api/record/<id> 路由正则
_RE_RECORD_DETAIL = re.compile(r'^/api/record/(\d+)$')


def _json_response(handler: BaseHTTPRequestHandler, data, *, status: int = 200) -> None:
    """序列化 data 为 JSON 并写入响应。"""
    body = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    # 本地只读服务，允许 fetch 跨源（供开发调试）
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, body: bytes, *, status: int = 200) -> None:
    """写入 HTML 响应。"""
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _static_response(handler: BaseHTTPRequestHandler, file_path: Path) -> None:
    """返回静态文件；不存在则 404。"""
    if not file_path.exists() or not file_path.is_file():
        _json_response(handler, {"error": "not found"}, status=404)
        return

    mime, _ = mimetypes.guess_type(str(file_path))
    mime = mime or "application/octet-stream"

    body = file_path.read_bytes()
    handler.send_response(200)
    handler.send_header("Content-Type", mime)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _make_handler(app: "App"):
    """工厂：返回绑定了 app 的 Handler 类（闭包传递 app，避免全局变量）。"""

    class Handler(BaseHTTPRequestHandler):
        """只读 HTTP 请求处理器，路由手工匹配。"""

        # 关闭默认的 access log（可按需开启）
        def log_message(self, fmt, *args):
            pass  # 静默；如需调试可改为 print(fmt % args)

        def do_GET(self):  # noqa: N802
            """处理 GET 请求，分发到各路由。"""
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query, keep_blank_values=False)

            # ── GET / → index.html ──────────────────────────────────
            if path == "/" or path == "/index.html":
                index_file = _ASSETS_DIR / "index.html"
                if not index_file.exists():
                    _html_response(self, b"<h1>index.html not found</h1>", status=404)
                    return
                _html_response(self, index_file.read_bytes())
                return

            # ── GET /api/records ────────────────────────────────────
            if path == "/api/records":
                self._handle_records(qs)
                return

            # ── GET /api/record/<id> ────────────────────────────────
            m = _RE_RECORD_DETAIL.match(path)
            if m:
                self._handle_record_detail(int(m.group(1)))
                return

            # ── GET /api/health ─────────────────────────────────────
            if path == "/api/health":
                self._handle_health()
                return

            # ── GET /static/<file> ──────────────────────────────────
            if path.startswith("/static/"):
                # 防路径穿越：只允许 assets 目录下的一级文件
                filename = path[len("/static/"):]
                # 不允许目录分隔符
                if "/" in filename or "\\" in filename or filename.startswith("."):
                    _json_response(self, {"error": "forbidden"}, status=403)
                    return
                _static_response(self, _ASSETS_DIR / filename)
                return

            # ── 其余 → 404 ──────────────────────────────────────────
            _json_response(self, {"error": "not found"}, status=404)

        def do_POST(self):  # noqa: N802
            """拒绝写操作。"""
            _json_response(self, {"error": "read-only"}, status=405)

        def do_PUT(self):  # noqa: N802
            _json_response(self, {"error": "read-only"}, status=405)

        def do_DELETE(self):  # noqa: N802
            _json_response(self, {"error": "read-only"}, status=405)

        def do_PATCH(self):  # noqa: N802
            _json_response(self, {"error": "read-only"}, status=405)

        # ── 私有路由处理方法 ────────────────────────────────────────

        def _handle_records(self, qs: dict) -> None:
            """GET /api/records?q=&limit=&offset= → 分页列表 JSON。"""
            from .queries import list_records

            q = (qs.get("q") or [None])[0]
            try:
                limit = int((qs.get("limit") or ["100"])[0])
            except (ValueError, IndexError):
                limit = 100
            try:
                offset = int((qs.get("offset") or ["0"])[0])
            except (ValueError, IndexError):
                offset = 0

            try:
                records, total = list_records(app, q=q, limit=limit, offset=offset)
                _json_response(self, {
                    "records": records,
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                })
            except Exception as exc:  # noqa: BLE001
                _json_response(self, {"error": str(exc)}, status=500)

        def _handle_record_detail(self, row_id: int) -> None:
            """GET /api/record/<id> → 单条详情 JSON。"""
            from .queries import record_detail

            try:
                row = record_detail(app, row_id)
                if row is None:
                    _json_response(self, {"error": "not found"}, status=404)
                else:
                    _json_response(self, row)
            except Exception as exc:  # noqa: BLE001
                _json_response(self, {"error": str(exc)}, status=500)

        def _handle_health(self) -> None:
            """GET /api/health → 数据健康 JSON（summaries + recent_runs）。"""
            try:
                summaries = app.meta.summaries()
                recent = app.meta.recent_runs(limit=50)
                # 业务库总数走每请求只读连接（sink 写连接绑定在主线程，不能跨线程用）
                conn = app.sink.db.readonly_connect()
                try:
                    table = app.sink.spec.table
                    total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                finally:
                    conn.close()
                _json_response(self, {
                    "summaries": summaries,
                    "recent_runs": recent,
                    "total_records": total,
                })
            except Exception as exc:  # noqa: BLE001
                _json_response(self, {"error": str(exc)}, status=500)

    return Handler


def serve(app: "App", *, host: str = "127.0.0.1", port: int = 8765) -> None:
    """启动只读 Web 浏览服务，Ctrl-C 优雅退出。

    使用 ThreadingHTTPServer 支持并发请求（SQLite WAL 模式可多线程读）。

    Args:
        app:  已组装的 App 实例（sink / meta / settings）。
        host: 监听地址，默认 127.0.0.1（仅本机访问）。
        port: 监听端口，默认 8765。
    """
    handler_class = _make_handler(app)
    # allow_reuse_address=True 防止重启时 "Address already in use"
    ThreadingHTTPServer.allow_reuse_address = True
    server = ThreadingHTTPServer((host, port), handler_class)

    url = f"http://{host}:{port}"
    print(f"fxharvest Web UI 已启动：{url}")
    print(f"  记录浏览：{url}/")
    print(f"  数据健康：{url}/#health")
    print("  按 Ctrl-C 退出")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("\nWeb UI 已关闭。")


__all__ = ["serve"]
