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
import random
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


def fetch(session: requests.Session, path: str, retries: int = 5) -> str:
    """抓單一頁面。遇 Cloudflare 挑戰頁以指數退避加抖動重試。

    2026-08-20 實測：同一台機器前一日可正常抓取，隔日整批 403——挑戰強度
    會隨時間浮動，原本 3 次（5/10/15 秒）不足以等到放行，故加長為
    5 次（約 8/16/32/64 秒，含抖動），總等待上限約 2 分鐘。
    """
    url = BASE + path
    status = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=HEADERS, timeout=30)
            resp.encoding = "utf-8"  # 必須在讀 .text 前設定（curl_cffi 之後設會報錯）
            if not is_challenge(resp):
                resp.raise_for_status()
                return resp.text
            status = resp.status_code
        except Exception as e:  # 連線層錯誤同樣重試
            status = type(e).__name__
        if attempt < retries - 1:
            time.sleep(min(8 * (2 ** attempt), 60) + random.uniform(0, 3))
    raise CloudflareBlocked(
        f"{url} 連續 {retries} 次未通過（{status}）。"
        "可能為 Cloudflare 挑戰強度提高；稍後重試或改用 fetch_wayback.py。"
    )


def warm_up(session: requests.Session) -> None:
    """先訪問首頁取得 __cf_bm cookie，降低後續請求觸發挑戰的機率。"""
    try:
        resp = session.get("https://www.nhi.gov.tw/ch/index.html", headers=HEADERS, timeout=30)
        resp.encoding = "utf-8"
        print(f"warm-up: HTTP {resp.status_code}" + ("（挑戰頁）" if is_challenge(resp) else "（正常）"))
        time.sleep(2)
    except Exception as e:
        print(f"warm-up 失敗（不影響後續）：{type(e).__name__}")


def safe_name(path: str) -> str:
    return path.replace("?", "_").replace("&", "_").replace("=", "-")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="cache/live", help="HTML 快取輸出目錄")
    ap.add_argument("--pages", type=int, default=15, help="法規公告列表最多抓幾頁（每頁60筆）")
    ap.add_argument("--delay", type=float, default=1.0, help="每次請求間隔秒數")
    ap.add_argument("--max-failures", type=int, default=3,
                    help="累計失敗幾頁後中止（避免整體被擋時空轉）")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session(**_SESSION_KWARGS)
    warm_up(session)

    targets = list(NODE_PAGES) + [f"{LIST_PAGE}?pi={p}&ps=60" for p in range(1, args.pages + 1)]
    ok, failed = [], []

    # 單頁失敗不中止整批：公告列表分頁彼此獨立，抓到幾頁就能建置幾頁的資料
    for path in targets:
        try:
            html = fetch(session, path)
        except CloudflareBlocked as e:
            failed.append(path)
            print(f"fail {path}：{e}", file=sys.stderr)
            # 連續失敗代表整體被擋，再試下去只是拖時間
            if len(failed) >= args.max_failures:
                print(f"連續失敗達 {args.max_failures} 頁，中止本次抓取。", file=sys.stderr)
                break
            continue
        (out / safe_name(path)).write_text(html, encoding="utf-8")
        ok.append(path)
        print(f"ok  {path} ({len(html)} bytes)")
        time.sleep(args.delay)

    print(f"完成：成功 {len(ok)} 頁、失敗 {len(failed)} 頁，HTML 存於 {out}/")
    if not ok:
        print("全部頁面皆未取得，請改用 fetch_wayback.py。", file=sys.stderr)
        return 2
    if failed:
        print(f"部分頁面未取得（{len(failed)} 頁），仍以已取得資料建置。", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
