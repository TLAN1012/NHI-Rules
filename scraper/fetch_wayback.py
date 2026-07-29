#!/usr/bin/env python3
"""從 Wayback Machine 抓取健保署藥品給付規定頁面的歷史存檔。

當官網被 Cloudflare 擋住（常見於雲端/CI 環境）時，用本腳本以
Internet Archive 的存檔補齊資料。

用法：
    python scraper/fetch_wayback.py [--out cache/wayback] [--url-prefix lp-3258-1.html]
"""

from __future__ import annotations

import argparse
import pathlib
import time
import urllib.parse

import requests

CDX = "https://web.archive.org/cdx/search/cdx"
SNAP = "https://web.archive.org/web/{ts}/{url}"
TARGET = "https://www.nhi.gov.tw/ch/"


def cdx_query(url: str, match_prefix: bool = False, limit: int = 500) -> list[tuple[str, str]]:
    """回傳 [(timestamp, original_url)]，每個 URL 只取最新一筆存檔。"""
    params = {
        "url": url,
        "output": "json",
        "filter": "statuscode:200",
        "collapse": "urlkey",
        "limit": str(limit),
    }
    if match_prefix:
        params["matchType"] = "prefix"
    resp = requests.get(CDX, params=params, timeout=60)
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return []
    header, *data = rows
    ts_i, url_i = header.index("timestamp"), header.index("original")
    # collapse=urlkey 回傳的是「最早」一筆；改為對每個 urlkey 取最新
    latest: dict[str, tuple[str, str]] = {}
    for row in data:
        key = row[header.index("urlkey")]
        if key not in latest or row[ts_i] > latest[key][0]:
            latest[key] = (row[ts_i], row[url_i])
    return list(latest.values())


def fetch_snapshot(ts: str, url: str) -> str:
    resp = requests.get(SNAP.format(ts=ts, url=url), timeout=120)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def safe_name(url: str, ts: str) -> str:
    path = urllib.parse.urlparse(url)
    name = path.path.rsplit("/", 1)[-1]
    if path.query:
        name += "_" + path.query.replace("&", "_").replace("=", "-")
    return f"{ts}__{name}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="cache/wayback")
    ap.add_argument(
        "--url-prefix",
        default="lp-3258-1.html",
        help="要查詢的 nhi.gov.tw/ch/ 下路徑前綴（prefix 比對，含分頁參數）",
    )
    ap.add_argument("--delay", type=float, default=1.5)
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    snapshots = cdx_query(TARGET + args.url_prefix, match_prefix=True)
    print(f"CDX 找到 {len(snapshots)} 個 URL 的存檔")
    for ts, url in snapshots:
        dest = out / safe_name(url, ts)
        if dest.exists():
            print(f"skip {dest.name}")
            continue
        try:
            html = fetch_snapshot(ts, url)
        except requests.RequestException as e:
            print(f"fail {url} @{ts}: {e}")
            continue
        dest.write_text(html, encoding="utf-8")
        print(f"ok   {dest.name} ({len(html)} bytes)")
        time.sleep(args.delay)

    print(f"完成，HTML 存於 {out}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
