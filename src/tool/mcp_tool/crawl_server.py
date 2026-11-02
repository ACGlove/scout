"""本地 MCP 服务器：网页抓取（fetch）+ 站内爬取（crawl），stdio 传输。

由 src/tool/mcp_tool/mcp_manager.py 以 `python crawl_server.py` 启动，
和 MCP 工具包统一放在 mcp_tool 目录下。依赖：mcp、httpx、beautifulsoup4（均已安装）。
"""
from __future__ import annotations

import json
import sys
from collections import deque
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("crawl")

UA = "Mozilla/5.0 (compatible; scout-crawler/1.0)"
TIMEOUT = 15


def _get(url: str) -> tuple[str, str]:
    """返回 (重定向后的最终 url, 响应文本)。"""
    resp = httpx.get(
        url, headers={"User-Agent": UA}, timeout=TIMEOUT, follow_redirects=True
    )
    resp.raise_for_status()
    return str(resp.url), resp.text


def _parse(html: str) -> tuple[str, str, list[str]]:
    """返回 (标题, 正文纯文本, 链接列表)。"""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = (soup.title.string or "").strip() if soup.title else ""
    text = " ".join(soup.get_text(" ").split())
    links = [a["href"] for a in soup.find_all("a", href=True)]
    return title, text, links


def _norm(url: str) -> str:
    """去重用：忽略 #fragment 和根路径上的结尾斜杠（https://a.com/ 与 https://a.com 视为同一页）。"""
    parsed = urlparse(url)
    path = "" if parsed.path in ("", "/") else parsed.path.rstrip("/")
    return parsed._replace(fragment="", path=path).geturl()


@mcp.tool()
def fetch(url: str, max_chars: int = 8000) -> str:
    """抓取单个网页，返回标题和正文纯文本。"""
    final, html = _get(url)
    title, text, _ = _parse(html)
    return f"# {title}\nURL: {final}\n\n{text[:max_chars]}"


@mcp.tool()
def crawl(url: str, max_pages: int = 5) -> str:
    """从 url 出发，在同一站点内广度优先爬取，返回 JSON：每页的 url/title/text 摘要。"""
    start = urlparse(url)
    seen, queue, pages = {_norm(url)}, deque([url]), []
    while queue and len(pages) < max_pages:
        current = queue.popleft()
        try:
            final, html = _get(current)
        except Exception as exc:  # 单页失败不影响整体爬取
            pages.append({"url": current, "error": str(exc)})
            continue
        title, text, links = _parse(html)
        pages.append({"url": str(final), "title": title, "text": text[:500]})
        for href in links:
            nxt = urljoin(str(final), href).split("#")[0]
            parsed = urlparse(nxt)
            key = _norm(nxt)
            if parsed.scheme in ("http", "https") and parsed.netloc == start.netloc and key not in seen:
                seen.add(key)
                queue.append(nxt)
    return json.dumps(pages, ensure_ascii=False, indent=2)


def _selftest() -> None:
    title, text, links = _parse(
        "<html><head><title>T</title></head><body><a href='/x'>x</a><p>hi</p></body></html>"
    )
    assert title == "T" and "hi" in text and "/x" in links, (title, text, links)
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        mcp.run()
