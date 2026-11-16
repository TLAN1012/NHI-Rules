#!/usr/bin/env python3
"""產生投遞回執 incoming/LAST_RUN.json，並在處理結果明顯不對時以非零碼結束。

用法：
    python scraper/drop_report.py [--incoming incoming] [--cache cache/topics]
                                  [--data docs/data] [--out incoming/LAST_RUN.json]

這份檔案是供應端與本專案之間的信箱：供應端下次投遞前先讀它，就知道上一批
收到幾份、用了幾份、哪些沒被歸入、還缺什麼。訊息跟著資料放在同一個 repo，
不另開管道——Actions 的 log 看完就沉了，別處的訊息檔沒人會主動去讀。

回報而非臆測：本腳本只陳述這次實際發生的事，推斷性的建議一律放在 notes，
不混進數字裡。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

TEXT_SUFFIXES = {".html", ".htm"}
SKIP_NAMES = {".gitkeep", "README.md", "LAST_RUN.json"}


def scan_drop(incoming: pathlib.Path) -> dict:
    """統計投遞區收到什麼。"""
    out: dict[str, dict] = {}
    for sub in ("topics", "drug"):
        path = incoming / sub
        if not path.is_dir():
            continue
        html, other, size = 0, [], 0
        for f in path.rglob("*"):
            if not f.is_file() or f.name in SKIP_NAMES:
                continue
            size += f.stat().st_size
            if f.suffix.lower() in TEXT_SUFFIXES:
                html += 1
            else:
                other.append(str(f))
        out[sub] = {"html": html, "non_html": sorted(other), "bytes": size}
    return out


def load(path: pathlib.Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--incoming", default="incoming")
    ap.add_argument("--cache", default="cache/topics")
    ap.add_argument("--data", default="docs/data")
    ap.add_argument("--out", default=None, help="預設寫到 <incoming>/LAST_RUN.json")
    args = ap.parse_args()

    incoming = pathlib.Path(args.incoming)
    out_path = pathlib.Path(args.out) if args.out else incoming / "LAST_RUN.json"

    received = scan_drop(incoming)
    ingest = load(pathlib.Path(args.cache) / "_fetch_report.json", {})
    topics = load(pathlib.Path(args.data) / "topics.json", {"topics": []})
    items_by_key = {t["key"]: len(t.get("items", [])) for t in topics.get("topics", [])}
    # 附件數是版型是否對得上的真訊號：項目標題可以從 hub 表格取得，
    # 但附件只能從子頁的「檔案下載」區解析，選擇器一旦對不上就會全數為 0。
    files_by_key = {
        t["key"]: sum(len(i.get("files", [])) for i in t.get("items", []))
        for t in topics.get("topics", [])
    }

    used: dict[str, dict] = {}
    for key, stat in ingest.items():
        if key.startswith("_"):
            continue
        used[key] = {
            "hub_pages": stat.get("hub_pages", 0),
            "child_pages": stat.get("children", 0),
            "items": items_by_key.get(key, 0),
            "attachments": files_by_key.get(key, 0),
        }

    meta = ingest.get("_ingest", {})
    unassigned = meta.get("unassigned", [])
    unreadable = meta.get("unreadable", [])

    problems: list[str] = []
    notes: list[str] = []

    topics_html = received.get("topics", {}).get("html", 0)
    # 用實際歸入的頁數判斷，不能看 used 是否為空：沒有任何一頁被歸入時，
    # used 仍會帶著每個專區的全零統計，看 key 數量會漏報。
    assigned_pages = sum(s["hub_pages"] + s["child_pages"] for s in used.values())
    if topics_html and not assigned_pages:
        problems.append(
            f"topics/ 收到 {topics_html} 份 HTML，但沒有任何一頁被歸入專區。"
            "最可能的原因是沒附上 hub 頁（lp-2771-1.html／np-2823-1.html）——"
            "專區歸屬是從 hub 沿連結走出來的，沒有 hub 就無從判斷。"
        )
    for key, stat in used.items():
        if stat["hub_pages"] and stat["child_pages"] and not stat["items"]:
            problems.append(
                f"{key}：收到 hub {stat['hub_pages']} 頁、子頁 {stat['child_pages']} 頁，"
                "卻解析出 0 筆項目。可能是官網版型與解析器的假設不符，需要人工看一次 HTML。"
            )
        elif stat["child_pages"] and not stat["attachments"]:
            problems.append(
                f"{key}：收到子頁 {stat['child_pages']} 頁、解析出 {stat['items']} 筆項目，"
                "但附件一個都沒有。項目標題可從 hub 表格取得，附件只能從子頁的"
                "「檔案下載」區解析——附件全為 0 通常代表子頁版型與解析器的假設不符，"
                "或投遞的子頁其實是列表頁而非內容頁。"
            )
        elif stat["hub_pages"] and not stat["child_pages"] and unassigned:
            # 有 hub、零子頁、卻有一堆未歸入 ⇒ 投的子頁不屬於投的 hub。
            # 只記 note 會讓該次 run 成功、投遞區被清空，證據跟著消失；
            # 實際發生過一次（投了 lp-2771 第 2 頁，子頁卻都在第 1 頁底下）。
            problems.append(
                f"{key}：收到 hub {stat['hub_pages']} 頁，但沒有任何子頁被歸入，"
                f"同時有 {len(unassigned)} 頁未歸入。代表投遞的子頁並不屬於投遞的 hub"
                "——多半是 hub 分頁投錯頁，或缺了中間層的年度／子分類節點頁。"
            )
        elif stat["hub_pages"] and not stat["child_pages"]:
            notes.append(
                f"{key}：只收到 hub 頁、沒有子頁。附件掛在子頁上，"
                "請一併投遞 hub 連到的 cp- 內容頁。"
            )

    if unassigned:
        notes.append(
            f"有 {len(unassigned)} 頁沒被任何 hub 連到，已略過："
            f"{', '.join(unassigned[:10])}{' …' if len(unassigned) > 10 else ''}。"
            "若它們應該被收錄，代表缺了中間層的 hub／子分類頁。"
        )
    if unreadable:
        notes.append(
            f"有 {len(unreadable)} 個檔案判斷不出是官網哪一頁，已略過："
            f"{', '.join(unreadable[:5])}{' …' if len(unreadable) > 5 else ''}。"
            "原始 HTML 通常帶 <link rel=canonical>；若來源已去除，請讓檔名含頁面代號。"
        )
    for sub, stat in received.items():
        if stat["non_html"]:
            notes.append(
                f"{sub}/ 含 {len(stat['non_html'])} 個非 HTML 檔案，未處理："
                f"{', '.join(stat['non_html'][:5])}{' …' if len(stat['non_html']) > 5 else ''}。"
                "資料集只記錄附件連結、不轉存附件；git 歷史無法回收，請勿推送附件。"
            )

    report = {
        "run_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "run_url": os.environ.get("GITHUB_RUN_URL", ""),
        "received": received,
        "used": used,
        "unassigned": unassigned,
        "unreadable": unreadable,
        "problems": problems,
        "notes": notes,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    for line in problems:
        print(f"::error::{line}")
    for line in notes:
        print(f"::warning::{line}")
    print(f"回執已寫入 {out_path}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
