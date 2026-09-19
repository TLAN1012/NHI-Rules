#!/usr/bin/env python3
"""把 fetch_topics.py 抓下的專區頁面整理成資料集，並比對出「這次變動了什麼」。

輸入：cache/topics/（fetch_topics.py 的輸出）
輸出：docs/data/topics.json、docs/data/topic_changes.json

用法：
    python scraper/build_topics.py cache/topics --out docs/data

變動偵測做到附件層級：每個項目以其附件清單（類型＋網址＋大小）算一組指紋，
健保署換新版檔案時 dl- 網址會跟著換，指紋因此改變。只比對項目標題會漏掉
「同一場會議補上會議紀錄」「同一個方案換了新版計畫書」這類最該被看到的更新。
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from parse_nhi import (  # noqa: E402
    content_page_key,
    parse_content_page,
    parse_download_sections,
    parse_table_items,
    roc_date_to_iso,
)
from topics_config import TOPICS  # noqa: E402
from dataclasses import asdict  # noqa: E402

NAME_RE = re.compile(r"^topic-(?P<topic>[a-z]+)__(?P<path>.+?)(?:\.html?)?$")
MAX_CHANGES = 500


def fingerprint(files: list[dict]) -> str:
    """附件指紋：對 (類型, 網址, 大小) 排序後雜湊，與附件在頁面上的順序無關。"""
    payload = sorted((f.get("file_type", ""), f.get("url", ""), f.get("size", "")) for f in files)
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def file_label(f: dict) -> str:
    return f.get("title") or f"{f.get('file_type', '檔案')}（{f.get('size', '')}）".strip("（）")


def collect(cache_dir: pathlib.Path) -> dict[str, dict[str, dict]]:
    """掃描快取目錄，回傳 {topic: {item_key: item}}。"""
    topics: dict[str, dict[str, dict]] = {t: {} for t in TOPICS}

    for path in sorted(cache_dir.glob("*.htm*")):
        m = NAME_RE.match(path.stem)
        if not m or m.group("topic") not in topics:
            continue
        topic, page = m.group("topic"), m.group("path")
        html = path.read_text(encoding="utf-8", errors="replace")
        items = topics[topic]

        if page.startswith("lp-") or page.startswith("np-"):
            # hub 頁只提供標題與日期，附件在子頁上；先建殼，子頁再補內容
            for row in parse_table_items(html):
                key = content_page_key(row["url"])
                items.setdefault(key, {"key": key, "title": "", "url": row["url"],
                                       "date": None, "files": []})
                items[key]["title"] = items[key]["title"] or row["title"]
                items[key]["date"] = items[key]["date"] or row["date"]
            continue

        # cp- 內容頁：標題與附件的權威來源
        page_url = f"https://www.nhi.gov.tw/ch/{page}.html"
        key = content_page_key(page_url)
        parsed = parse_content_page(html)
        files = [f for d in parsed["downloads"] for f in d["files"]]
        if not files:
            files = [asdict(f) for d in parse_download_sections(html) for f in d.files]
        item = items.setdefault(key, {"key": key, "title": "", "url": page_url,
                                      "date": None, "files": []})
        item["title"] = parsed["title"] or item["title"]
        item["url"] = page_url
        item["files"] = files
        for label in ("更新日期", "發布日期"):
            value = parsed["meta"].get(label)
            if value:
                item["date"] = roc_date_to_iso(value) or item["date"]
                break

    for topic_items in topics.values():
        for item in topic_items.values():
            item["fingerprint"] = fingerprint(item["files"])
    return topics


def diff_topic(topic: str, old_items: list[dict], new_items: list[dict],
               clean_fetch: bool) -> tuple[list[dict], list[dict]]:
    """比對新舊項目，回傳 (變動清單, 要寫入的項目清單)。

    抓取不完整時不判定「移除」，並把缺席的舊項目原樣保留：一次 Cloudflare
    擋下就把整批項目報成下架、資料跟著消失，是比漏報更糟的失敗模式。
    """
    old = {i["key"]: i for i in old_items}
    new = {i["key"]: i for i in new_items}
    changes: list[dict] = []
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    for key, item in new.items():
        prev = old.get(key)
        if prev is None:
            changes.append({"detected_at": now, "topic": topic, "type": "added",
                            "item_key": key, "title": item["title"], "url": item["url"],
                            "date": item["date"],
                            "detail": {"files": [file_label(f) for f in item["files"]]}})
            continue
        if prev.get("fingerprint") != item["fingerprint"]:
            prev_urls = {f.get("url") for f in prev.get("files", [])}
            new_urls = {f.get("url") for f in item["files"]}
            changes.append({"detected_at": now, "topic": topic, "type": "files_changed",
                            "item_key": key, "title": item["title"], "url": item["url"],
                            "date": item["date"],
                            "detail": {
                                "added": [file_label(f) for f in item["files"]
                                          if f.get("url") not in prev_urls],
                                "removed": [file_label(f) for f in prev.get("files", [])
                                            if f.get("url") not in new_urls],
                            }})

    merged = list(new.values())
    for key, prev in old.items():
        if key in new:
            continue
        if clean_fetch:
            changes.append({"detected_at": now, "topic": topic, "type": "removed",
                            "item_key": key, "title": prev.get("title", ""),
                            "url": prev.get("url", ""), "date": prev.get("date"),
                            "detail": {}})
        else:
            merged.append({**prev, "carried": True})
    return changes, merged


def sort_items(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: (i.get("date") or "", i.get("title") or ""), reverse=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cache_dir", help="fetch_topics.py 的輸出目錄")
    ap.add_argument("--out", default="docs/data", help="JSON 輸出目錄")
    args = ap.parse_args()

    cache_dir = pathlib.Path(args.cache_dir)
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        report = json.loads((cache_dir / "_fetch_report.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        report = {}

    topics_path = out / "topics.json"
    try:
        previous = json.loads(topics_path.read_text(encoding="utf-8"))
        baseline = False
    except (OSError, json.JSONDecodeError):
        previous = {"topics": []}
        baseline = True
    prev_by_key = {t["key"]: t.get("items", []) for t in previous.get("topics", [])}

    collected = collect(cache_dir)
    all_changes: list[dict] = []
    topics_out: list[dict] = []

    for key, spec in TOPICS.items():
        stat = report.get(key, {})
        clean = bool(stat) and stat.get("hub_pages", 0) > 0 and stat.get("failed", 0) == 0
        new_items = list(collected.get(key, {}).values())
        prev_items = prev_by_key.get(key, [])

        if not new_items and prev_items:
            # 本次完全沒抓到：保留既有資料，不當成全部下架
            print(f"{key}：本次未取得任何項目，沿用既有 {len(prev_items)} 筆")
            topics_out.append({"key": key, "name": spec["name"], "url": spec["url"],
                               "items": sort_items(prev_items), "stale": True})
            continue

        changes, merged = diff_topic(key, prev_items, new_items, clean)
        if not baseline:
            all_changes.extend(changes)
        topics_out.append({"key": key, "name": spec["name"], "url": spec["url"],
                           "items": sort_items(merged), "stale": not clean})
        print(f"{key}（{spec['name']}）：{len(merged)} 筆項目，"
              f"{'建立基準線' if baseline else f'{len(changes)} 項變動'}"
              f"{'（抓取不完整）' if not clean else ''}")

    topics_path.write_text(
        json.dumps({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "topics": topics_out,
        }, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    changes_path = out / "topic_changes.json"
    try:
        log = json.loads(changes_path.read_text(encoding="utf-8")).get("changes", [])
    except (OSError, json.JSONDecodeError):
        log = []
    log = (all_changes + log)[:MAX_CHANGES]
    changes_path.write_text(
        json.dumps({"changes": log}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"本次新增 {len(all_changes)} 筆變動紀錄（保留最近 {len(log)} 筆）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
