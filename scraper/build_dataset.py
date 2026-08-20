#!/usr/bin/env python3
"""把抓下來的 HTML 快取解析、合併成前端用的 JSON 資料集。

輸入：一個或多個 HTML 快取目錄（fetch_live.py / fetch_wayback.py 的輸出）
輸出：docs/data/ 下的 announcements.json、chapters.json、history.json、meta.json

用法：
    python scraper/build_dataset.py cache/live cache/wayback --out docs/data
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from parse_nhi import (  # noqa: E402
    Announcement,
    is_drug_rule_announcement,
    parse_content_page,
    parse_download_sections,
    parse_list_page,
)
from dataclasses import asdict  # noqa: E402


def detect_source(path: pathlib.Path, html: str) -> str:
    m = re.match(r"^(\d{8,17})__", path.name)
    if m:
        return f"wayback:{m.group(1)}"
    if "web.archive.org" in html[:4000] or "/web/20" in html[:4000]:
        m = re.search(r"/web/(\d{8,17})", html)
        if m:
            return f"wayback:{m.group(1)}"
    return "live"


def classify_page(html: str) -> str:
    """依頁面特徵分類：list（公告列表）、chapters（分章節）、history（歷史檔）、other。"""
    if "section" in html and 'class="list"' in html and "發文字號" in html:
        return "list"
    if "最新版藥品給付規定內容(分章節)" in html and "fileDownload" in html:
        return "chapters"
    if "整份帶走" in html and "fileDownload" in html:
        return "fulldoc"
    if "藥品給付規定歷史檔" in html and "fileDownload" in html:
        return "history"
    return "other"


def merge_announcements(collected: dict[str, dict], anns: list[Announcement]) -> None:
    for a in anns:
        if not a.title:
            continue
        key = a.key()
        rec = asdict(a)
        rec["key"] = key
        rec["is_drug_rule"] = is_drug_rule_announcement(a.title)
        old = collected.get(key)
        if old is None:
            collected[key] = rec
            continue
        # 以較新的來源為準（live 優先，其次 wayback 時間戳較大者）
        def rank(source: str) -> tuple[int, str]:
            # live > wayback > existing（既有資料集）；同 key 由較優來源覆蓋，
            # 但任何來源都不會使既有公告消失
            if source == "live":
                return (2, "")
            if source == "existing":
                return (0, "")
            return (1, source.split(":", 1)[-1])

        if rank(rec["source"]) > rank(old["source"]):
            rec["is_drug_rule"] = rec["is_drug_rule"] or old["is_drug_rule"]
            collected[key] = rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cache_dirs", nargs="+", help="HTML 快取目錄")
    ap.add_argument("--out", default="docs/data", help="JSON 輸出目錄")
    ap.add_argument("--no-merge-existing", action="store_true",
                    help="忽略既有資料集、完全重建（預設為累加合併）")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    announcements: dict[str, dict] = {}

    # 先納入既有資料集當基底：公告是歷史事實，只應累加不應因來源缺漏而消失。
    # （雲端 runner 無 cache/live，若全量重建會把 self-hosted 抓到的新公告洗掉）
    existing_path = out / "announcements.json"
    if existing_path.exists() and not args.no_merge_existing:
        try:
            for rec in json.loads(existing_path.read_text(encoding="utf-8")):
                key = rec.get("key")
                if key:
                    announcements[key] = {**rec, "source": "existing"}
            print(f"載入既有公告 {len(announcements)} 筆作為合併基底")
        except (json.JSONDecodeError, OSError) as e:
            print(f"既有資料集無法讀取（{e}），改為全量重建")
    chapters: list[dict] = []
    chapters_source = ""
    history: list[dict] = []
    history_source = ""
    fulldoc: dict = {}
    fulldoc_source = ""
    stats = {"files": 0, "list_pages": 0}

    for cache_dir in args.cache_dirs:
        for path in sorted(pathlib.Path(cache_dir).glob("*.htm*")):
            html = path.read_text(encoding="utf-8", errors="replace")
            source = detect_source(path, html)
            kind = classify_page(html)
            stats["files"] += 1
            if kind == "list":
                anns, _ = parse_list_page(html, source=source)
                merge_announcements(announcements, anns)
                stats["list_pages"] += 1
            elif kind == "chapters":
                items = parse_download_sections(html)
                if items and (not chapters or source >= chapters_source):
                    page = parse_content_page(html)
                    chapters = page["downloads"]
                    chapters_source = source
            elif kind == "fulldoc":
                items = parse_download_sections(html)
                if items and (not fulldoc or source >= fulldoc_source):
                    page = parse_content_page(html)
                    fulldoc = {"title": page["title"], "downloads": page["downloads"]}
                    fulldoc_source = source
            elif kind == "history":
                items = parse_download_sections(html)
                if items and (not history or source >= history_source):
                    page = parse_content_page(html)
                    history = page["downloads"]
                    history_source = source

    ann_list = sorted(
        announcements.values(),
        key=lambda a: (a.get("issued_date") or "", a.get("published_date") or ""),
        reverse=True,
    )

    (out / "announcements.json").write_text(
        json.dumps(ann_list, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (out / "chapters.json").write_text(
        json.dumps({"source": chapters_source, "items": chapters}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out / "fulldoc.json").write_text(
        json.dumps({"source": fulldoc_source, **fulldoc}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    (out / "history.json").write_text(
        json.dumps({"source": history_source, "items": history}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    dates = [a["issued_date"] for a in ann_list if a.get("issued_date")]
    meta = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "announcement_count": len(ann_list),
        "drug_rule_count": sum(1 for a in ann_list if a["is_drug_rule"]),
        "date_range": [min(dates), max(dates)] if dates else None,
        "chapters_count": len(chapters),
        "chapters_source": chapters_source,
        "history_count": len(history),
        "history_source": history_source,
        "fulldoc_title": fulldoc.get("title", ""),
        "fulldoc_source": fulldoc_source,
        "stats": stats,
        "source_site": "https://www.nhi.gov.tw/ch/np-2505-1.html",
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
