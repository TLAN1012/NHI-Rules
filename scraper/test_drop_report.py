#!/usr/bin/env python3
"""drop_report.py 的回執測試。

執行：python scraper/test_drop_report.py

回執是供應端唯一會讀到的回饋，所以兩個方向都要測：該報問題時不能沉默
（否則對方以為成功、下次照錯的方式再投一次），沒問題時不能亂報
（否則整個 run 失敗、資料也不會發布）。
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
INGEST = ROOT / "scraper" / "ingest_topics.py"
BUILD = ROOT / "scraper" / "build_topics.py"
REPORT = ROOT / "scraper" / "drop_report.py"

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}：預期 {want}，實得 {got}")


def page(canon: str, body: str) -> str:
    return (f'<html><head><link rel="canonical" href="https://www.nhi.gov.tw/ch/{canon}">'
            f"</head><body>{body}</body></html>")


def hub(rows: list[tuple[str, str]]) -> str:
    body = "".join(f'<tr><td>{i+1}</td><td><a href="/ch/{p}">{t}</a></td><td>115-09-10</td></tr>'
                   for i, (t, p) in enumerate(rows))
    return ('<table><thead><tr><th>項次</th><th>會議名稱</th><th>會議日期</th></tr></thead>'
            f"<tbody>{body}</tbody></table>")


def child(title: str, with_files: bool = True) -> str:
    files = ('<section class="fileDownload"><ul><li>'
             f'<span class="fileName">{title}</span><ol class="downloadFiles"><li>'
             '<span class="fileType">pdf</span><div class="fileSize">2 MB</div>'
             f'<a href="/ch/dl-700-aaa-1.pdf" title="{title}.pdf">下載</a>'
             "</li></ol></li></ul></section>") if with_files else ""
    return f'<div class="pageHeader"><h2>{title}</h2></div>{files}<article class="cpArticle">x</article>'


def run_pipeline(root: pathlib.Path, files: dict[str, str],
                 blobs: dict[str, bytes] | None = None) -> tuple[int, dict]:
    """建投遞區 → ingest → build → report，回傳 (回執結束碼, 回執內容)。"""
    incoming, cache, data = root / "incoming", root / "cache", root / "data"
    for d in (incoming / "topics", incoming / "drug", data):
        d.mkdir(parents=True, exist_ok=True)
    for f in (incoming / "topics").glob("*"):
        f.unlink()
    for name, html in files.items():
        (incoming / "topics" / name).write_text(html, encoding="utf-8")
    for name, blob in (blobs or {}).items():
        (incoming / "topics" / name).write_bytes(blob)

    if files:
        subprocess.run([sys.executable, str(INGEST), str(incoming / "topics"),
                        "--out", str(cache)], capture_output=True, text=True)
        subprocess.run([sys.executable, str(BUILD), str(cache), "--out", str(data)],
                       capture_output=True, text=True)
    proc = subprocess.run(
        [sys.executable, str(REPORT), "--incoming", str(incoming),
         "--cache", str(cache), "--data", str(data)],
        capture_output=True, text=True,
    )
    report = json.loads((incoming / "LAST_RUN.json").read_text(encoding="utf-8"))
    return proc.returncode, report


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # 1. 正常投遞：不該報問題，否則整個 run 失敗、資料也不會發布
        root = base / "ok"
        code, rep = run_pipeline(root, {
            "a.html": page("lp-2771-1.html", hub([("115年第9次會議", "cp-2009-aa-2771-1.html")])),
            "b.html": page("cp-2009-aa-2771-1.html", child("115年第9次會議")),
        })
        check("正常投遞：結束碼", code, 0)
        check("正常投遞：無 problems", rep["problems"], [])
        check("正常投遞：項目數", rep["used"]["meetings"]["items"], 1)
        check("正常投遞：附件數", rep["used"]["meetings"]["attachments"], 1)
        print(f"  正常投遞：exit {code}，meetings {rep['used']['meetings']}")

        # 2. 忘了附 hub 頁：沒有 hub 就無從判斷歸屬，必須講清楚原因
        root = base / "nohub"
        code, rep = run_pipeline(root, {
            "b.html": page("cp-2009-aa-2771-1.html", child("115年第9次會議")),
        })
        check("缺 hub：結束碼", code, 1)
        check("缺 hub：有 problems", len(rep["problems"]), 1)
        check("缺 hub：點出 hub 頁", "hub" in rep["problems"][0], True)
        print(f"  缺 hub 頁：exit {code}，{rep['problems'][0][:46]}…")

        # 3. 版型對不上：hub 與子頁都收到，卻解析出 0 筆——這正是目前
        #    共擬會議解析器尚未對真實頁面驗證過的風險，必須報出來
        root = base / "layout"
        code, rep = run_pipeline(root, {
            "a.html": page("lp-2771-1.html", hub([("115年第9次會議", "cp-2009-aa-2771-1.html")])),
            "b.html": page("cp-2009-aa-2771-1.html", "<div>版型不同，沒有 fileDownload 區</div>"),
        })
        check("版型不符：結束碼", code, 1)
        check("版型不符：有 problems", len(rep["problems"]) >= 1, True)
        check("版型不符：點名 meetings", "meetings" in rep["problems"][0], True)
        check("版型不符：指向附件為 0", "附件" in rep["problems"][0], True)
        check("版型不符：附件計數", rep["used"]["meetings"]["attachments"], 0)
        print(f"  版型對不上：exit {code}，{rep['problems'][0][:46]}…")

        # 4. 雜訊：附件與孤兒頁只該進 notes，不該讓整個 run 失敗
        root = base / "noise"
        code, rep = run_pipeline(root, {
            "a.html": page("lp-2771-1.html", hub([("115年第9次會議", "cp-2009-aa-2771-1.html")])),
            "b.html": page("cp-2009-aa-2771-1.html", child("115年第9次會議")),
            "c.html": page("cp-8888-zz-9999-1.html", child("沒人連到的頁")),
        }, blobs={"會議紀錄.pdf": b"%PDF-1.4" + b"x" * 4096})
        check("雜訊：結束碼仍為 0", code, 0)
        check("雜訊：無 problems", rep["problems"], [])
        check("雜訊：孤兒頁與附件都進 notes", len(rep["notes"]), 2)
        check("雜訊：非 HTML 有列出",
              [p.rsplit("/", 1)[-1] for p in rep["received"]["topics"]["non_html"]],
              ["會議紀錄.pdf"])
        print(f"  附件與孤兒頁：exit {code}，notes {len(rep['notes'])} 則（不致失敗）")

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("全部通過 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
