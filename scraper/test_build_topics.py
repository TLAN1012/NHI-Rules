#!/usr/bin/env python3
"""build_topics.py 的變動偵測測試。

執行：python scraper/test_build_topics.py

重點在「該報的要報、不該報的絕不能報」：抓取失敗時把整批項目誤判成下架，
比漏報一次更新嚴重得多（資料會跟著消失）。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "scraper" / "build_topics.py"


def hub_html(rows: list[tuple[str, str, str]]) -> str:
    """rows: [(標題, cp- 路徑, 民國日期)]"""
    body = "".join(
        f'<tr><td>{i+1}</td><td><a href="/ch/{path}.html">{title}</a></td><td>{date}</td></tr>'
        for i, (title, path, date) in enumerate(rows)
    )
    return f"""<html><body><table>
<thead><tr><th>項次</th><th>會議名稱</th><th>會議日期</th></tr></thead>
<tbody>{body}</tbody></table></body></html>"""


def child_html(title: str, files: list[tuple[str, str, str]]) -> str:
    """files: [(類型, dl- 識別碼, 大小)]"""
    lis = "".join(
        f'<li><span class="fileType">{ft}</span><div class="fileSize">{size}</div>'
        f'<a href="/ch/dl-{dl}-aaa-1.{ft}" title="{title}.{ft}">下載</a></li>'
        for ft, dl, size in files
    )
    return f"""<html><body>
<div class="pageHeader"><h2>{title}</h2></div>
<section class="fileDownload"><ul><li>
  <span class="fileName">{title}</span><ol class="downloadFiles">{lis}</ol>
</li></ul></section>
<article class="cpArticle">內容</article></body></html>"""


def write_cache(cache: pathlib.Path, pages: dict[str, str], report: dict) -> None:
    cache.mkdir(parents=True, exist_ok=True)
    for f in cache.glob("*"):
        f.unlink()
    for name, html in pages.items():
        (cache / name).write_text(html, encoding="utf-8")
    (cache / "_fetch_report.json").write_text(json.dumps(report), encoding="utf-8")


def run(cache: pathlib.Path, out: pathlib.Path) -> tuple[dict, dict]:
    proc = subprocess.run(
        [sys.executable, str(BUILD), str(cache), "--out", str(out)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(f"build_topics 失敗：{proc.stderr}")
    return (
        json.loads((out / "topics.json").read_text(encoding="utf-8")),
        json.loads((out / "topic_changes.json").read_text(encoding="utf-8")),
    )


P1, P2 = "cp-1001-aaaaa-2771-1", "cp-1002-bbbbb-2771-1"
CLEAN = {"meetings": {"hub_pages": 1, "children": 2, "failed": 0}}
PARTIAL = {"meetings": {"hub_pages": 1, "children": 1, "failed": 1}}

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}：預期 {want}，實得 {got}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cache, out = tmp / "cache", tmp / "out"
        out.mkdir()

        # 1. 首次建置只建基準線，不該把既有項目全部報成「新增」
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([("115年第8次會議", P1, "115-08-20")]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
        }, CLEAN)
        topics, changes = run(cache, out)
        meetings = next(t for t in topics["topics"] if t["key"] == "meetings")
        check("基準線：項目數", len(meetings["items"]), 1)
        check("基準線：不產生變動紀錄", len(changes["changes"]), 0)
        print(f"  基準線：{len(meetings['items'])} 筆項目、{len(changes['changes'])} 筆變動")

        # 2. 新增一場會議
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([
                ("115年第9次會議", P2, "115-09-10"),
                ("115年第8次會議", P1, "115-08-20"),
            ]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
            f"topic-meetings__{P2}.html": child_html("115年第9次會議", [("pdf", "800", "3 MB")]),
        }, CLEAN)
        topics, changes = run(cache, out)
        latest = changes["changes"][0]
        check("新增：變動筆數", len(changes["changes"]), 1)
        check("新增：類型", latest["type"], "added")
        check("新增：項目", latest["item_key"], P2)
        check("新增：排序（新的在前）",
              next(t for t in topics["topics"] if t["key"] == "meetings")["items"][0]["key"], P2)
        print(f"  新增一場會議：{latest['type']} / {latest['title']}")

        # 3. 同一場會議補上會議紀錄（標題不變，只有附件變）——只比標題會完全漏掉
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([
                ("115年第9次會議", P2, "115-09-10"),
                ("115年第8次會議", P1, "115-08-20"),
            ]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
            f"topic-meetings__{P2}.html": child_html(
                "115年第9次會議", [("pdf", "800", "3 MB"), ("pdf", "801", "1 MB")]),
        }, CLEAN)
        topics, changes = run(cache, out)
        latest = changes["changes"][0]
        check("附件變動：類型", latest["type"], "files_changed")
        check("附件變動：新增附件數", len(latest["detail"]["added"]), 1)
        check("附件變動：移除附件數", len(latest["detail"]["removed"]), 0)
        print(f"  補上會議紀錄：{latest['type']}，新增附件 {latest['detail']['added']}")

        # 4. 換新版檔案（dl- 網址改變）：一增一減
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([
                ("115年第9次會議", P2, "115-09-10"),
                ("115年第8次會議", P1, "115-08-20"),
            ]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
            f"topic-meetings__{P2}.html": child_html(
                "115年第9次會議", [("pdf", "800", "3 MB"), ("pdf", "899", "1 MB")]),
        }, CLEAN)
        topics, changes = run(cache, out)
        latest = changes["changes"][0]
        check("換版：類型", latest["type"], "files_changed")
        check("換版：新增附件數", len(latest["detail"]["added"]), 1)
        check("換版：移除附件數", len(latest["detail"]["removed"]), 1)
        print(f"  換新版檔案：+{len(latest['detail']['added'])} / -{len(latest['detail']['removed'])}")

        # 5. 抓取不完整時，缺席的項目不得判定為下架
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([("115年第8次會議", P1, "115-08-20")]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
        }, PARTIAL)
        topics, changes = run(cache, out)
        meetings = next(t for t in topics["topics"] if t["key"] == "meetings")
        check("抓取不完整：不報下架",
              [c for c in changes["changes"] if c["type"] == "removed"], [])
        check("抓取不完整：保留缺席項目", sorted(i["key"] for i in meetings["items"]), sorted([P1, P2]))
        check("抓取不完整：標記 stale", meetings["stale"], True)
        print("  抓取不完整：缺席項目原樣保留、未誤報下架")

        # 6. 抓取完整時，真正下架才報 removed
        write_cache(cache, {
            f"topic-meetings__lp-2771-1.html": hub_html([("115年第8次會議", P1, "115-08-20")]),
            f"topic-meetings__{P1}.html": child_html("115年第8次會議", [("pdf", "700", "2 MB")]),
        }, CLEAN)
        topics, changes = run(cache, out)
        removed = [c for c in changes["changes"] if c["type"] == "removed"]
        meetings = next(t for t in topics["topics"] if t["key"] == "meetings")
        check("下架：報一筆 removed", len(removed), 1)
        check("下架：項目正確", removed[0]["item_key"], P2)
        check("下架：項目已移除", [i["key"] for i in meetings["items"]], [P1])
        print(f"  真正下架：{removed[0]['type']} / {removed[0]['title']}")

        # 7. 完全抓不到時沿用既有資料，不清空
        write_cache(cache, {}, {"meetings": {"hub_pages": 0, "children": 0, "failed": 0}})
        topics, changes = run(cache, out)
        meetings = next(t for t in topics["topics"] if t["key"] == "meetings")
        check("全失敗：沿用既有項目", [i["key"] for i in meetings["items"]], [P1])
        check("全失敗：標記 stale", meetings["stale"], True)
        print("  完全抓不到：沿用既有資料、未清空")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("全部通過 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
