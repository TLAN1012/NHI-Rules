#!/usr/bin/env python3
"""從健保署官網抓取藥品給付規定相關頁面，存成 HTML 快取。

用法：
    python scraper/fetch_live.py [--out cache/live] [--pages N]

抓取內容：
- lp-3258-1.html（法規公告／修正規定列表，分頁抓取）
- np-2505-1.html 及其子頁（np-2506、np-2508、np-3397、np-2509、np-3420）
- 各章節/歷史檔內容頁（cp-*）

注意：www.nhi.gov.tw 前有 Cloudflare 防護。從資料中心 IP（雲端主機、CI）
存取時常會被擋（HTTP 403 / 挑戰頁）。此腳本偵測到挑戰頁時會明確報錯；
請改在一般網路環境執行，或改用 fetch_wayback.py 以 Wayback Machine 存檔補資料。
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time

import requests

BASE = "https://www.nhi.gov.tw/ch/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9",
}

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


def fetch(session: requests.Session, path: str) -> str:
    url = BASE + path
    resp = session.get(url, headers=HEADERS, timeout=30)
    if is_challenge(resp):
        raise CloudflareBlocked(
            f"{url} 回應 Cloudflare 挑戰頁（HTTP {resp.status_code}）。"
            "請改在一般網路環境執行，或改用 fetch_wayback.py。"
        )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


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
    session = requests.Session()

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
