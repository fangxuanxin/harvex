"""传统 HTTP 采集插件（骨架铺垫）。

定位：最基础、最常用的采集方式——直接 HTTP 请求拿 JSON / HTML。
复用框架注入的 ``ctx.http``（HttpClient，自带超时/指数退避重试/统一 UA）。

⚠️ 这是铺垫骨架：``acquire()`` 暂未实现，故意留给后续 AI 服务按目标接口补全。
下面文档串写清了「该怎么实现」，AI 照此填即可。
"""

from __future__ import annotations

from harvex.acquire.base import Acquirer, AcquireResult


class HttpAcquirer(Acquirer):
    """通过 HTTP 直接获取原始数据。

    实现指引（供 AI 补全 acquire）：
      1. 从 ``self.ctx.url`` 取目标地址，``self.ctx.config`` 取 method/headers/params/json 等。
      2. GET JSON：``data = self.ctx.http.get_json(url)``；
         GET 文本/HTML：``resp = self.ctx.http.get(url); raw = resp.text``；
         POST：``self.ctx.http.post(url, json=...)``。
      3. 返回 ``AcquireResult(raw=..., content_type="json"|"html", url=url,
         meta={"status": resp.status_code})``。
      4. 失败让 HttpClient 抛 FetchError 即可（已带重试），无需自己 try。
    """

    kind = "http"

    def acquire(self) -> AcquireResult:
        raise NotImplementedError(
            "HttpAcquirer.acquire 尚未实现——这是预留给 AI 服务按目标接口补全的铺垫。"
            "参见类文档串的实现指引。"
        )


__all__ = ["HttpAcquirer"]
