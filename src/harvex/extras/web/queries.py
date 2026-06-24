"""extras/web/queries.py：Web UI 只读查询层。

所有查询均经由 _query(app, ) 走参数化 SQL，列名白名单防注入。
不做任何写操作，不引入任何第三方依赖。
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # 仅类型检查时引入，运行时通过 app 对象访问
    from ...cli.main import App

# 安全列名正则：只允许字母、数字、中文、下划线（防止列名注入）
_SAFE_COL_RE = re.compile(r'^[\w一-鿿]+$')


def _query(app: "App", sql: str, params: tuple = ()) -> list:
    """每次调用开一个独立只读连接执行查询。

    Web 服务用 ThreadingHTTPServer，每个请求在独立线程；而 sink 的写连接绑定在
    主线程（sqlite check_same_thread）。只读浏览须用 readonly_connect 在当前线程
    新建连接，既线程安全又保证只读语义（不持写锁，WAL 下可并发读）。
    """
    conn = app.sink.db.readonly_connect()
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        conn.close()


def _safe_columns(columns: list[str]) -> list[str]:
    """过滤出安全的列名（白名单校验），排除 id（框架内部主键）。

    Args:
        columns: SchemaSpec.columns 的全量列名列表。

    Returns:
        通过白名单校验、且排除 id 的列名列表。
    """
    return [c for c in columns if c != "id" and _SAFE_COL_RE.match(c)]


def list_records(
    app: "App",
    *,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """分页查询业务表，支持全列模糊搜索。

    设计要点：
    - 表名来自 app.sink.spec.table（框架控制，非用户输入）。
    - 列名经白名单 _safe_columns() 过滤，不拼接用户输入的列名。
    - 搜索关键词 q 只作为 LIKE 参数绑定，不拼入 SQL 字符串。
    - limit / offset 强制转 int 后作为参数绑定。

    Args:
        app:    已组装的 App 实例（含 sink、settings）。
        q:      搜索关键词（None 或空串 = 不过滤）。
        limit:  每页条数，默认 100，最大 500。
        offset: 偏移量，默认 0。

    Returns:
        (行列表, 总数) —— 行列表中每条为 dict，总数是满足条件的全量计数。
    """
    # 强制数值范围，防止异常输入
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))

    spec = app.sink.spec
    table = spec.table                        # 框架控制，非用户输入
    safe_cols = _safe_columns(spec.columns)   # 白名单过滤后的列名

    if not safe_cols:
        return [], 0

    # 构造 SELECT 列表（id 也一并返回，方便详情链接）
    select_cols = ", ".join(f'"{c}"' for c in spec.columns)

    if q and q.strip():
        # 对所有业务列做 LIKE 模糊搜索（OR 连接）
        like_clauses = " OR ".join(f'"{c}" LIKE ?' for c in safe_cols)
        like_param = f"%{q.strip()}%"
        like_params = tuple(like_param for _ in safe_cols)

        count_sql = f'SELECT COUNT(*) FROM "{table}" WHERE {like_clauses}'
        data_sql = (
            f'SELECT {select_cols} FROM "{table}" '
            f'WHERE {like_clauses} '
            f'ORDER BY "id" DESC LIMIT ? OFFSET ?'
        )
        count_rows = _query(app, count_sql, like_params)
        total = count_rows[0][0] if count_rows else 0

        data_rows = _query(app, data_sql, like_params + (limit, offset))
    else:
        count_sql = f'SELECT COUNT(*) FROM "{table}"'
        data_sql = (
            f'SELECT {select_cols} FROM "{table}" '
            f'ORDER BY "id" DESC LIMIT ? OFFSET ?'
        )
        count_rows = _query(app, count_sql)
        total = count_rows[0][0] if count_rows else 0

        data_rows = _query(app, data_sql, (limit, offset))

    # sqlite3.Row → dict（方便 JSON 序列化）
    records = [dict(row) for row in data_rows]
    return records, int(total)


def record_detail(app: "App", row_id: int) -> dict | None:
    """按主键 id 查询单条记录详情。

    Args:
        app:    已组装的 App 实例。
        row_id: 记录 id（INTEGER PRIMARY KEY）。

    Returns:
        对应行的 dict，不存在时返回 None。
    """
    row_id = int(row_id)
    spec = app.sink.spec
    table = spec.table
    select_cols = ", ".join(f'"{c}"' for c in spec.columns)

    rows = _query(app, 
        f'SELECT {select_cols} FROM "{table}" WHERE "id" = ?',
        (row_id,),
    )
    return dict(rows[0]) if rows else None


__all__ = ["list_records", "record_detail"]
