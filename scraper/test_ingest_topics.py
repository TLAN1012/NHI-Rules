#!/usr/bin/env python3
"""ingest_topics.py 的匯入測試。

執行：python scraper/test_ingest_topics.py

重點在「歸屬要對、漏掉的要講」：改善方案底下還分子分類，子分類頁的子頁帶的是
子分類代號，用網址規則歸屬會整批歸錯；而沒被任何 hub 連到的檔案若靜靜消失，
會變成「資料少了但沒人知道」。
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

failures: list[str] = []


def check(label: str, got, want) -> None:
    if got != want:
        failures.append(f"{label}：預期 {want}，實得 {got}")


def page(canonical: str, body: str) -> str:
    return f"""<html><head><link rel="canonical" href="https://www.nhi.gov.tw/ch/{canonical}">
</head><body>{body}</body></html>"""


def links(*paths: str) -> str:
    items = "".join(f'<a href="/ch/{p}">{p}</a>' for p in paths)
    return f'<nav><a href="/ch/np-9999-1.html">關於健保署</a></nav><div class="contentbox">{items}</div>'


def table(rows: list[tuple[str, str, str]]) -> str:
    body = "".join(
        f'<tr><td>{i+1}</td><td><a href="/ch/{p}">{t}</a></td><td>{d}</td></tr>'
        for i, (t, p, d) in enumerate(rows)
    )
    return ('<table><thead><tr><th>項次</th><th>會議名稱</th><th>會議日期</th></tr></thead>'
            f'<tbody>{body}</tbody></table>')


def attach(title: str, dl: str) -> str:
    return (f'<div class="pageHeader"><h2>{title}</h2></div>'
            '<section class="fileDownload"><ul><li>'
            f'<span class="fileName">{title}</span><ol class="downloadFiles"><li>'
            f'<span class="fileType">pdf</span><div class="fileSize">2 MB</div>'
            f'<a href="/ch/dl-{dl}-aaa-1.pdf" title="{title}.pdf">下載</a>'
            '</li></ol></li></ul></section><article class="cpArticle">內容</article>')


def multi_hub_case() -> None:
    """舊頁停更、內容搬家時，新舊 hub 並列仍應合成同一份資料。

    健保署已把共擬會議從 lp-2771 移走（舊頁自 114-03-28 起不再更新）。
    換頁期間兩邊都要走得到，且同一場會議不能因為兩頁都連到而變成兩筆。
    直接在行程內替換設定，不經子行程——設定是模組層常數，子行程改不到。
    """
    sys.path.insert(0, str(ROOT / "scraper"))
    import ingest_topics

    original = ingest_topics.TOPICS
    ingest_topics.TOPICS = {
        **original,
        "meetings": {**original["meetings"],
                     "hubs": ["lp-2771-1.html", "lp-8888-1.html"]},
    }
    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp = pathlib.Path(tmp)
            src, out = tmp / "src", tmp / "cache"
            src.mkdir()
            shared = "cp-2009-aa-2771-1.html"   # 兩個 hub 都連到的同一場會議
            moved = "cp-3001-bb-8888-1.html"    # 只出現在新頁
            files = {
                "old.html": page("lp-2771-1.html", table([("115年第9次會議", shared, "115-09-10")])),
                "new.html": page("lp-8888-1.html", table([
                    ("115年第9次會議", shared, "115-09-10"),
                    ("115年第11次會議", moved, "115-11-05"),
                ])),
                "a.html": page(shared, attach("115年第9次會議", "900")),
                "b.html": page(moved, attach("115年第11次會議", "901")),
            }
            for name, html in files.items():
                (src / name).write_text(html, encoding="utf-8")

            argv = sys.argv
            sys.argv = ["ingest_topics.py", str(src), "--out", str(out)]
            try:
                code = ingest_topics.main()
            finally:
                sys.argv = argv
            check("多 hub：結束碼", code, 0)

            report = json.loads((out / "_fetch_report.json").read_text(encoding="utf-8"))
            check("多 hub：兩個 hub 都算到", report["meetings"]["hub_pages"], 2)
            check("多 hub：子頁去重後 2 頁", report["meetings"]["children"], 2)
            check("多 hub：無未歸入頁面", report["_ingest"]["unassigned"], [])
            written = sorted(p.name for p in out.glob("topic-meetings__*"))
            check("多 hub：共用子頁只寫出一次",
                  written.count(f"topic-meetings__{shared}"), 1)
            print(f"  新舊 hub 並列：hub {report['meetings']['hub_pages']} 頁、"
                  f"子頁 {report['meetings']['children']} 頁（共用的那場會議未重複）")
    finally:
        ingest_topics.TOPICS = original


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        src, out, data = tmp / "src", tmp / "cache", tmp / "data"
        src.mkdir()
        data.mkdir()

        # 檔名刻意雜亂：匯入要靠檔案內容判斷頁面，不靠命名規則
        files = {
            "共擬會議列表.html": page("lp-2771-1.html",
                                 table([("115年第9次共同擬訂會議", "cp-2001-aa111-2771-1.html", "115-09-10")])),
            "meeting_9.html": page("cp-2001-aa111-2771-1.html", attach("115年第9次共同擬訂會議", "900")),
            # 改善方案 hub → 子分類（np-2824）→ 方案頁（帶 2824 而非 2823）
            "改善方案.html": page("np-2823-1.html", links("np-2824-1.html")),
            "疾病管理.html": page("np-2824-1.html", links("cp-4001-dm111-2824-1.html")),
            "糖尿病方案.html": page("cp-4001-dm111-2824-1.html",
                                attach("全民健康保險糖尿病醫療給付改善方案", "950")),
            # 沒被任何 hub 連到：必須被報出來，不能靜靜消失
            "孤兒頁.html": page("cp-8888-zz999-9999-1.html", attach("某個沒人連到的頁", "999")),
        }
        for name, html in files.items():
            (src / name).write_text(html, encoding="utf-8")
        # 非 HTML（例如 bot 順手存的 Markdown）應被略過，不造成噪音
        (src / "說明.md").write_text("# 這不是 HTML", encoding="utf-8")

        proc = subprocess.run([sys.executable, str(INGEST), str(src), "--out", str(out)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout, proc.stderr)
            raise AssertionError("ingest_topics 失敗")
        print(proc.stdout.strip())

        report = json.loads((out / "_fetch_report.json").read_text(encoding="utf-8"))
        check("共擬會議 hub 頁數", report["meetings"]["hub_pages"], 1)
        check("共擬會議子頁數", report["meetings"]["children"], 1)
        check("改善方案 hub 頁數（含子分類）", report["programs"]["hub_pages"], 2)
        check("改善方案子頁數", report["programs"]["children"], 1)
        check("孤兒頁應列入 unassigned",
              report["_ingest"]["unassigned"], ["cp-8888-zz999-9999-1.html"])
        check("Markdown 不應被當成無法辨識", report["_ingest"]["unreadable"], [])

        names = sorted(p.name for p in out.glob("topic-*"))
        check("寫出的檔名", names, [
            "topic-meetings__cp-2001-aa111-2771-1.html",
            "topic-meetings__lp-2771-1.html",
            "topic-programs__cp-4001-dm111-2824-1.html",
            "topic-programs__np-2823-1.html",
            "topic-programs__np-2824-1.html",
        ])

        # 匯入的結果要能直接餵進 build_topics
        proc = subprocess.run([sys.executable, str(BUILD), str(out), "--out", str(data)],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout, proc.stderr)
            raise AssertionError("build_topics 失敗")
        topics = json.loads((data / "topics.json").read_text(encoding="utf-8"))
        by_key = {t["key"]: t for t in topics["topics"]}
        check("共擬會議項目數", len(by_key["meetings"]["items"]), 1)
        check("改善方案項目數", len(by_key["programs"]["items"]), 1)
        check("改善方案項目標題", by_key["programs"]["items"][0]["title"],
              "全民健康保險糖尿病醫療給付改善方案")
        check("附件有被解析出來", len(by_key["programs"]["items"][0]["files"]), 1)
        check("匯入視為完整抓取", by_key["programs"]["stale"], False)
        print(f"  串接 build_topics：共擬會議 {len(by_key['meetings']['items'])} 筆、"
              f"改善方案 {len(by_key['programs']['items'])} 筆（含附件）")

    multi_hub_case()

    print()
    if failures:
        for f in failures:
            print(f"FAIL  {f}")
        return 1
    print("全部通過 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
