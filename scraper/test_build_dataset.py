#!/usr/bin/env python3
"""build_dataset.py 的來源優先序測試。

執行：python scraper/test_build_dataset.py

這裡只測「哪個來源該勝出」。整份帶走／分章節／歷史檔三個區塊每次只留一份結果，
選錯來源不會報錯、只會安靜地寫入舊資料——曾使整份給付規定停在 114.08.22 的
Wayback 快照達一年無人察覺，故以測試釘住。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "scraper" / "build_dataset.py"


def fulldoc_html(title: str, dl_id: str, wayback_ts: str = "") -> str:
    """產生一頁「整份帶走」內容頁；給 wayback_ts 則模擬 Wayback 存檔頁。"""
    href = f"/ch/dl-{dl_id}-abc123-1.pdf"
    if wayback_ts:
        href = f"https://web.archive.org/web/{wayback_ts}/https://www.nhi.gov.tw{href}"
    banner = f'<script src="/web/{wayback_ts}/x.js"></script>' if wayback_ts else ""
    return f"""<html><head>{banner}</head><body>
<div class="pageHeader"><h2>{title}</h2></div>
<section class="fileDownload"><ul><li>
  <span class="fileName">{title}</span>
  <ol class="downloadFiles"><li>
    <span class="fileType">pdf</span><div class="fileSize">6 MB</div>
    <a href="{href}" title="{title}.pdf">下載</a>
  </li></ol>
</li></ul></section>
<article class="cpArticle">整份帶走</article></body></html>"""


def run_build(cache_dirs: list[pathlib.Path], out: pathlib.Path) -> dict:
    cmd = [sys.executable, str(BUILD), *map(str, cache_dirs), "--out", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError(f"build_dataset 失敗：{proc.stderr}")
    return json.loads((out / "fulldoc.json").read_text(encoding="utf-8"))


def case(name: str, pages: dict[str, str], existing: dict | None = None) -> dict:
    """在暫存目錄跑一次建置。pages 為 {檔名: HTML}，existing 為預先放好的 fulldoc.json。"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        cache, out = tmp / "cache", tmp / "out"
        cache.mkdir()
        out.mkdir()
        if existing is not None:
            (out / "fulldoc.json").write_text(
                json.dumps(existing, ensure_ascii=False), encoding="utf-8"
            )
        for fname, html in pages.items():
            (cache / fname).write_text(html, encoding="utf-8")
        result = run_build([cache], out)
    print(f"  {name}: {result['source']} / {result['title']}")
    return result


def main() -> int:
    live = fulldoc_html("最新版藥品給付規定內容(整份帶走)-115.8.21更新", "100717")
    old_wb = fulldoc_html(
        "最新版藥品給付規定內容(整份帶走)-114.08.22更新", "61741", "20250910111349"
    )
    new_wb = fulldoc_html(
        "最新版藥品給付規定內容(整份帶走)-115.8.21更新", "100717", "20260915000000"
    )
    failures = []

    def check(label: str, got: str, want: str) -> None:
        if got != want:
            failures.append(f"{label}：預期 {want}，實得 {got}")

    print("來源優先序：")

    # 直接比字串時「wayback:...」> 「live」，Wayback 會永遠勝出；掃描順序不該影響結果
    r = case("live 與 wayback 同時存在（wayback 檔名在後）", {"a-live.html": live, "z-wb.html": old_wb})
    check("live 應勝過 wayback", r["source"], "live")

    r = case("live 與 wayback 同時存在（live 檔名在後）", {"a-wb.html": old_wb, "z-live.html": live})
    check("掃描順序不應影響結果", r["source"], "live")

    # 雲端 runner 只有 Wayback 快取：不得把 self-hosted 抓到的最新版洗回舊存檔
    existing_live = {
        "source": "live",
        "title": "最新版藥品給付規定內容(整份帶走)-115.8.21更新",
        "downloads": [{"name": "x", "files": [{"file_type": "pdf", "url": "u", "title": "", "size": ""}]}],
    }
    r = case("既有為 live、本次只有 wayback", {"wb.html": old_wb}, existing=existing_live)
    check("既有 live 不應被 wayback 覆蓋", r["source"], "live")
    check("既有 live 標題應保留", r["title"], existing_live["title"])

    # 兩份存檔之間仍應取較新者
    r = case("兩份 wayback 存檔", {"a-old.html": old_wb, "b-new.html": new_wb})
    check("wayback 應取時間戳較新者", r["source"], "wayback:20260915000000")

    # 既有較舊的存檔應可被新抓到的存檔更新
    existing_old_wb = {
        "source": "wayback:20250910111349",
        "title": "最新版藥品給付規定內容(整份帶走)-114.08.22更新",
        "downloads": [{"name": "x", "files": [{"file_type": "pdf", "url": "u", "title": "", "size": ""}]}],
    }
    r = case("既有為舊 wayback、本次為新 wayback", {"new.html": new_wb}, existing=existing_old_wb)
    check("較新的 wayback 應更新既有資料", r["source"], "wayback:20260915000000")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("全部通過 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
