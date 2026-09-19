#!/usr/bin/env python3
"""抓取「共同擬訂會議」與「醫療給付改善方案」兩個專區的頁面。

用法：
    python scraper/fetch_topics.py [--out cache/topics] [--pages N]

與 fetch_live.py 共用連線設定（curl_cffi 以 Chrome TLS 指紋過 Cloudflare），
只是換一組目標頁。抓下來的 HTML 另存 cache/topics/，**不要**餵給
build_dataset.py——那支專門處理藥品給付規定，本專區的列表頁餵進去會被
classify_page 誤判成法規公告而污染 announcements.json。

流程：先抓各專區的 hub 頁，從中取出子頁（cp-）連結，再逐頁抓內容頁，
因為附件（會議紀錄、計畫書、問答集）都掛在內容頁的「檔案下載」區。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from fetch_live import (  # noqa: E402
    _SESSION_KWARGS,
    CloudflareBlocked,
    fetch,
    requests,
    warm_up,
)
from bs4 import BeautifulSoup  # noqa: E402

from parse_nhi import parse_node_page, parse_table_items  # noqa: E402
from topics_config import TOPICS  # noqa: E402

CHILD_RE = re.compile(r"/ch/((?:cp|np)-[\w-]+\.html)")


def child_paths(html: str, kind: str) -> list[str]:
    """從頁面取出子頁路徑（去重、保序）。

    列表頁走表格、節點頁走連結列表；兩者都取不到時，退回只掃內文區塊的連結
    （刻意不掃全頁，否則會把頁首頁尾的全站導覽也當成子頁一路爬下去）。
    """
    if kind == "list":
        urls = [item["url"] for item in parse_table_items(html)]
    else:
        urls = [link["url"] for link in parse_node_page(html)]
    if not urls:
        soup = BeautifulSoup(html, "html.parser")
        urls = [
            a["href"]
            for scope in soup.select("main, .contentbox, article")
            for a in scope.select("a[href]")
        ]
    seen, paths = set(), []
    for url in urls:
        m = CHILD_RE.search(url)
        if not m or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        paths.append(m.group(1))
    return paths


def safe_name(topic: str, path: str) -> str:
    """檔名前綴帶 topic，供 build_topics.py 判斷該頁屬於哪個專區。"""
    return f"topic-{topic}__{path.replace('?', '_').replace('&', '_').replace('=', '-')}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="cache/topics", help="HTML 快取輸出目錄")
    ap.add_argument("--pages", type=int, default=5, help="列表型 hub 最多抓幾頁")
    ap.add_argument("--delay", type=float, default=1.0, help="每次請求間隔秒數")
    ap.add_argument("--max-children", type=int, default=200, help="每個專區最多抓幾個子頁")
    ap.add_argument("--depth", type=int, default=3, help="節點頁最多往下展開幾層")
    ap.add_argument("--topics", default=",".join(TOPICS), help="只抓指定專區（逗號分隔）")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    session = requests.Session(**_SESSION_KWARGS)
    warm_up(session)

    wanted = [t.strip() for t in args.topics.split(",") if t.strip() in TOPICS]
    report: dict[str, dict] = {}
    any_ok = False

    for topic in wanted:
        spec = TOPICS[topic]
        hubs = [spec["hub"]]
        if spec["kind"] == "list":
            hubs += [f"{spec['hub']}?pi={p}&ps=60" for p in range(1, args.pages + 1)]

        children: list[str] = []
        hub_ok = 0
        for hub in hubs:
            try:
                html = fetch(session, hub)
            except CloudflareBlocked as e:
                print(f"fail {hub}：{e}", file=sys.stderr)
                continue
            (out / safe_name(topic, hub)).write_text(html, encoding="utf-8")
            hub_ok += 1
            for path in child_paths(html, spec["kind"]):
                if path not in children:
                    children.append(path)
            time.sleep(args.delay)

        if hub_ok == 0:
            print(f"{topic}：hub 頁全數未取得，跳過子頁", file=sys.stderr)
            report[topic] = {"hub_pages": 0, "children": 0, "failed": 0}
            continue

        # 廣度優先走訪：改善方案專區的 hub 底下還分「疾病管理／婦幼／其他」等
        # 子分類（np-），真正帶附件的方案頁在再下一層，只抓一層會整批漏掉。
        child_ok, child_fail = 0, 0
        queue = [(path, 1) for path in children]
        visited = set(children)
        while queue and child_ok + child_fail < args.max_children:
            path, depth = queue.pop(0)
            try:
                html = fetch(session, path)
            except CloudflareBlocked as e:
                child_fail += 1
                print(f"fail {path}：{e}", file=sys.stderr)
                continue
            (out / safe_name(topic, path)).write_text(html, encoding="utf-8")
            child_ok += 1
            if path.startswith("np-") and depth < args.depth:
                for nxt in child_paths(html, "node"):
                    if nxt not in visited:
                        visited.add(nxt)
                        queue.append((nxt, depth + 1))
            time.sleep(args.delay)

        any_ok = any_ok or child_ok > 0 or hub_ok > 0
        report[topic] = {"hub_pages": hub_ok, "children": child_ok, "failed": child_fail}
        print(f"{topic}（{spec['name']}）：hub {hub_ok} 頁、子頁 {child_ok} 成功／{child_fail} 失敗")

    (out / "_fetch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    if not any_ok:
        print("所有專區皆未取得任何頁面。", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
