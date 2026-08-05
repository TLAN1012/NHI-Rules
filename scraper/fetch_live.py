#!/usr/bin/env python3
"""從健保署官網抓取藥品給付規定相關頁面，存成 HTML 快取。

用法：
    python scraper/fetch_live.py [--out cache/live] [--pages N]

抓取內容：
- lp-3258-1.html（法規公告／修正規定列表，分頁抓取）
- np-2505-1.html 及其子頁（np-2506、np-2508、np-3397、np-2509、np-3420）
- 各章節/歷史檔內容頁（cp-*）

注意：www.nhi.gov.tw 前有 Cloudflare 防護，且會檢測 TLS 指紋——即使住宅／機構
IP，plain requests/curl（假 Chrome UA）也會被挑戰頁擋下（2026-08 實測）。
因此優先使用 curl_cffi 以 Chrome TLS 指紋連線（同一線路實測可過）；
curl_cffi 不可用時退回 requests。資料中心 IP 連 TLS 指紋正確也會被擋，
CI 雲端環境請改用 fetch_wayback.py 以 Wayback Machine 存檔補資料。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

try:
    from curl_cffi import requests

    _SESSION_KWARGS = {"impersonate": "chrome"}
    HEADERS = {"Accept-Language": "zh-TW,zh;q=0.9"}  # UA 交給 impersonate，避免指紋不一致
except ImportError:
    import requests

    _SESSION_KWARGS = {}
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "zh-TW,zh;q=0.9",
    }

BASE = "https://www.nhi.gov.tw/ch/"

NODE_PAGES = [
    "np-2505-1.html",  # 藥品給付規定（總覽）
    "np-2506-1.html",  # 藥品給付規定內容
    "np-2508-1.html",  # 最新版藥品給付規定內容(整份帶走)
    "np-3397-1.html",  # 最新版藥品給付規定內容(分章節)
    "np-2509-1.html",  # 全民健康保險藥品給付規定歷史檔
    "np-3420-1.html",  # 健保用藥給付問答集
]

LIST_PAGE = "lp-3258-1.html"  # 法規公告（修正規定，自103年4月3日以後生效之公告）


class CloudflareBlocked(RuntimeError):
    pass


def is_challenge(resp: requests.Response) -> bool:
    if resp.status_code in (403, 503) and "cloudflare" in resp.text.lower():
        return True
    return "<title>Just a moment...</title>" in resp.text


def fetch(session: requests.Session, path: str, retries: int = 3) -> str:
    url = BASE + path
    status = None
    for attempt in range(retries):
        resp = session.get(url, headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"  # 必須在讀 .text 前設定（curl_cffi 之後設會報錯）
        if not is_challenge(resp):
            resp.raise_for_status()
            return resp.text
        # 挑戰頁偶發出現在新連線的前幾個請求；帶著 __cf_bm cookie 稍候重試常可通過
        status = resp.status_code
        time.sleep(5 * (attempt + 1))
    raise CloudflareBlocked(
        f"{url} 連續 {retries} 次回應 Cloudflare 挑戰頁（HTTP {status}）。"
        "請改在一般網路環境執行，或改用 fetch_wayback.py。"
    )


def safe_name(path: str) -> str:
    return path.replace("?", "_").replace("&", "_").replace("=", "-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="cache/live", help="HTML 快取輸出目錄")
    ap.add_argument("--pages", type=int, default=15, help="法規公告列表最多抓幾頁（每頁60筆）")
    ap.add_argument("--delay", type=float, default=1.0, help="每次請求間隔秒數")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session(**_SESSION_KWARGS)

    try:
        for path in NODE_PAGES:
            html = fetch(session, path)
            (out / safe_name(path)).write_text(html, encoding="utf-8")
            print(f"ok  {path} ({len(html)} bytes)")
            time.sleep(args.delay)

        for page in range(1, args.pages + 1):
            path = f"{LIST_PAGE}?pi={page}&ps=60"
            html = fetch(session, path)
            (out / safe_name(path)).write_text(html, encoding="utf-8")
            print(f"ok  {path} ({len(html)} bytes)")
            if "共<em>" in html and f"第<em>{page}/" not in html.replace(" ", ""):
                pass  # 頁碼資訊由 build_dataset 統一解析
            time.sleep(args.delay)
    except CloudflareBlocked as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2

    print(f"完成，HTML 存於 {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
