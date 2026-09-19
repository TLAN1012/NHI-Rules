#!/usr/bin/env python3
"""把別處抓好的原始 HTML 匯入成 build_topics.py 吃得下的快取。

用法：
    python scraper/ingest_topics.py <來源目錄> [--out cache/topics]

用途：健保署官網對資料中心 IP 一律出 Cloudflare 挑戰頁，CI／雲端環境抓不到。
若已有人（或會開瀏覽器的 bot）把頁面原始碼存下來，用本腳本匯入即可，
不必在受限環境裡跟 Cloudflare 周旋。

來源目錄丟原始 HTML 即可，**檔名不拘**：本腳本自己從每份檔案裡判斷它是哪一頁
（`<link rel=canonical>` → `og:url` → 檔名裡的 lp-／np-／cp- 代號）。

歸屬到哪個專區不靠網址規則，而是**從 hub 頁沿著連結走**：改善方案底下還分
「疾病管理／婦幼／其他」等子分類，子分類頁的子頁帶的是子分類代號而非 hub 代號，
用網址比對會整批歸錯。走連結才對得準。

沒被任何 hub 走到的檔案會列在報告的 unassigned，不會靜靜吞掉。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from bs4 import BeautifulSoup  # noqa: E402

from topics_config import TOPICS  # noqa: E402

PAGE_RE = re.compile(r"((?:lp|np|cp)-[\w-]+?)(?:\.html?)?$")
URL_PAGE_RE = re.compile(r"/ch/((?:lp|np|cp)-[\w-]+)\.html")
# fetch_topics.py 存檔時把 ?pi=1&ps=60 轉成 _pi-1_ps-60，匯入時要還原回頁面代號
SUFFIX_RE = re.compile(r"_p[is]-[\w-]+$")


def page_id(path: pathlib.Path, html: str) -> str | None:
    """判斷這份 HTML 是官網的哪一頁，回傳如 lp-2771-1.html 的頁面代號。"""
    soup = BeautifulSoup(html, "html.parser")
    for el, attr in (
        (soup.select_one('link[rel="canonical"]'), "href"),
        (soup.select_one('meta[property="og:url"]'), "content"),
    ):
        if el and el.get(attr):
            m = URL_PAGE_RE.search(el[attr])
            if m:
                return m.group(1) + ".html"

    stem = SUFFIX_RE.sub("", path.stem)
    m = PAGE_RE.search(stem)
    return m.group(1) + ".html" if m else None


def child_links(html: str) -> list[str]:
    """取出頁面內文區塊裡指向其他 lp-／np-／cp- 頁的連結。

    刻意不掃全頁：頁首頁尾的全站導覽也是 np-／cp- 連結，掃進來會讓歸屬
    一路擴散到整個官網。
    """
    soup = BeautifulSoup(html, "html.parser")
    scopes = soup.select("main, .contentbox, article, table") or [soup]
    out, seen = [], set()
    for scope in scopes:
        for a in scope.select("a[href]"):
            m = URL_PAGE_RE.search(a["href"])
            if m and m.group(1) not in seen:
                seen.add(m.group(1))
                out.append(m.group(1) + ".html")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="存放原始 HTML 的目錄（會遞迴尋找）")
    ap.add_argument("--out", default="cache/topics", help="輸出目錄")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.is_dir():
        print(f"來源目錄不存在：{src}", file=sys.stderr)
        return 2
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # 1. 先認出每份檔案是哪一頁
    pages: dict[str, tuple[pathlib.Path, str]] = {}
    unreadable: list[str] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".html", ".htm"):
            continue
        html = path.read_text(encoding="utf-8", errors="replace")
        pid = page_id(path, html)
        if pid is None:
            unreadable.append(str(path.relative_to(src)))
            continue
        pages.setdefault(pid, (path, html))

    if not pages:
        print(f"{src} 下找不到任何可辨識的官網頁面（需要原始 HTML，不是轉好的 Markdown）",
              file=sys.stderr)
        return 2

    # 2. 從各專區 hub 沿連結走，決定每頁屬於哪個專區
    assigned: dict[str, str] = {}
    report: dict[str, dict] = {}
    for topic, spec in TOPICS.items():
        hub = spec["hub"]
        if hub not in pages:
            print(f"{topic}（{spec['name']}）：來源中沒有 hub 頁 {hub}，略過", file=sys.stderr)
            report[topic] = {"hub_pages": 0, "children": 0, "failed": 0}
            continue

        queue, seen = [hub], {hub}
        members: list[str] = []
        while queue:
            pid = queue.pop(0)
            if pid not in pages:
                continue
            # 一頁只歸一個專區；先走到的先得，避免兩區共用頁面時重複計算
            if pid in assigned:
                continue
            assigned[pid] = topic
            members.append(pid)
            for nxt in child_links(pages[pid][1]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)

        hub_pages = sum(1 for p in members if p.startswith(("lp-", "np-")))
        children = len(members) - hub_pages
        for pid in members:
            dest = out / f"topic-{topic}__{pid}"
            dest.write_text(pages[pid][1], encoding="utf-8")
        # 匯入的資料視為完整：來源是別處抓好的整批頁面，沒有「抓到一半被擋」
        # 這種狀態；真有缺漏會反映在 unassigned 與 hub 頁缺失上。
        report[topic] = {"hub_pages": hub_pages, "children": children, "failed": 0}
        print(f"{topic}（{spec['name']}）：hub {hub_pages} 頁、子頁 {children} 頁")

    unassigned = sorted(p for p in pages if p not in assigned)
    report["_ingest"] = {
        "source": str(src),
        "pages_found": len(pages),
        "unassigned": unassigned,
        "unreadable": unreadable,
    }
    (out / "_fetch_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    if unreadable:
        print(f"\n無法辨識頁面代號（{len(unreadable)} 個檔案）："
              f"{', '.join(unreadable[:5])}{' …' if len(unreadable) > 5 else ''}", file=sys.stderr)
    if unassigned:
        print(f"\n未歸入任何專區（{len(unassigned)} 頁，可能是沒被 hub 連到）："
              f"{', '.join(unassigned[:8])}{' …' if len(unassigned) > 8 else ''}", file=sys.stderr)
    print(f"\n匯入完成，共 {len(assigned)} 頁寫入 {out}/")
    print(f"接著執行：python scraper/build_topics.py {out} --out docs/data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
