#!/usr/bin/env python3
"""家庭醫師整合性照護計畫（家醫計畫）文件解析。

輸入兩份 PDF：
1. 問答集（三欄表格：問題／回答／備註，依主題分類）→ fm_qa.json
2. 計畫本文（壹、貳、參…章節＋附件）→ fm_plan.json

家醫計畫屬公告查詢性質、不需定期追蹤；有新版文件時重跑本腳本即可。

用法：
    python3 scraper/extract_fm.py --qa-pdf 問答集.pdf --plan-pdf 計畫本文.pdf \
        --out docs/data
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re

import fitz

# 問答集表格欄位 x 邊界（pt）：問題 < 200 ≦ 回答 < 505 ≦ 備註
# （回答欄的 (一)(二) 子項起始約 x=244，問題欄至多 x≈60，取 200 安全分界）
Q_COL_MAX = 200
A_COL_MAX = 505

CAT_RE = re.compile(r"^[一二三四五六七八九十]+、")
QNUM_RE = re.compile(r"^\([一二三四五六七八九十]+\)")
SEC_RE = re.compile(r"^(壹|貳|參|肆|伍|陸|柒|捌|玖|拾[壹貳參肆伍陸柒]?)、")


def page_lines(page) -> list[tuple[float, float, str]]:
    """回傳 (y, x0, 文字) 的行列表，依 y 排序。"""
    lines: dict[tuple[int, int], list] = {}
    for x0, y0, x1, y1, word, bno, lno, wno in page.get_text("words"):
        key = (bno, lno)
        lines.setdefault(key, []).append((x0, y0, word))
    out = []
    for words in lines.values():
        words.sort(key=lambda w: w[0])
        x0 = words[0][0]
        y0 = min(w[1] for w in words)
        text = "".join(w[2] for w in words)
        out.append((y0, x0, text))
    out.sort(key=lambda t: (round(t[0], 1), t[1]))
    return out


def parse_qa(pdf_path: pathlib.Path) -> dict:
    doc = fitz.open(pdf_path)
    title, version = "", ""
    entries: list[dict] = []
    category = ""
    current: dict | None = None

    for pno, page in enumerate(doc):
        for y, x0, text in page_lines(page):
            t = text.strip()
            if not t or re.fullmatch(r"\d{1,3}", t):  # 頁碼
                continue
            if pno == 0 and not category:
                if "問答集" in t and not title:
                    title = t
                    continue
                m = re.fullmatch(r"115\.\d{2}\.?[〇0-9]*", t)
                if m and not version:
                    version = t
                    continue
            if x0 < Q_COL_MAX:
                if CAT_RE.match(t) and len(t) > 2:
                    if current:
                        entries.append(current)
                        current = None
                    # 分類標題可能帶新舊兩層編號（如「六、 七、糖心腎…」），全部剝除
                    category = re.sub(r"^(?:[一二三四五六七八九十]+、\s*)+", "", t)
                    continue
                if QNUM_RE.match(t):
                    if current:
                        entries.append(current)
                    current = {"category": category, "question": t, "answer": "", "note": ""}
                elif current is not None:
                    current["question"] += t
            elif current is not None:
                if x0 < A_COL_MAX:
                    current["answer"] += t + "\n"
                else:
                    current["note"] += t
    if current:
        entries.append(current)

    for e in entries:
        e["question"] = re.sub(r"^\([一二三四五六七八九十]+\)\s*", "", e["question"]).strip()
        e["answer"] = e["answer"].strip()
        e["note"] = e["note"].strip()
    return {"title": title, "version": version, "entries": entries}


def parse_plan(pdf_path: pathlib.Path) -> dict:
    doc = fitz.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)
    # 頁碼行（如 "- 1 -"）
    text = re.sub(r"^\s*-\s*\d+\s*-\s*$", "", text, flags=re.M)

    title_m = re.search(r"全民健康保險家庭醫師整合性照護計畫", text)
    title = title_m.group(0) if title_m else pdf_path.name

    # 修正沿革（開頭的歷次公告）
    revisions = re.findall(r"^[^\n]*第\s*\d+\s*號公告(?:修正)?[^\n]*$", text[:3000], re.M)

    # 主體章節：壹、～拾柒、；之後的重複中文序號屬附件表單
    marks = []
    seen = set()
    for m in re.finditer(r"^(壹|貳|參|肆|伍|陸|柒|捌|玖|拾[壹貳參肆伍陸柒]?)、", text, re.M):
        if m.group(1) in seen:
            break
        seen.add(m.group(1))
        marks.append((m.start(), m.group(1)))
    sections = []
    for i, (pos, num) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        seg = text[pos:end]
        first_line, _, rest = seg.partition("\n")
        sections.append({
            "id": num,
            "title": re.sub(r"^[壹貳參肆伍陸柒捌玖拾]+、\s*", "", first_line).strip(),
            "text": rest.strip(),
        })
    return {"title": title, "revisions": revisions, "sections": sections}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--qa-pdf", help="問答集 PDF")
    ap.add_argument("--plan-pdf", help="計畫本文 PDF")
    ap.add_argument("--qa-file", default="", help="問答集 PDF 於網站上的檔名（docs/files/ 下）")
    ap.add_argument("--plan-file", default="", help="計畫本文 PDF 於網站上的檔名")
    ap.add_argument("--out", default="docs/data")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    if args.qa_pdf:
        qa = parse_qa(pathlib.Path(args.qa_pdf))
        qa["generated_at"] = now
        qa["file"] = args.qa_file
        (out / "fm_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8")
        cats = list(dict.fromkeys(e["category"] for e in qa["entries"]))
        print(f"問答集：{len(qa['entries'])} 題，{len(cats)} 個分類")
        for c in cats:
            n = sum(1 for e in qa["entries"] if e["category"] == c)
            print(f"  {c}: {n} 題")

    if args.plan_pdf:
        plan = parse_plan(pathlib.Path(args.plan_pdf))
        plan["generated_at"] = now
        plan["file"] = args.plan_file
        (out / "fm_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"計畫本文：{len(plan['sections'])} 章、沿革 {len(plan['revisions'])} 筆")
        for s in plan["sections"]:
            print(f"  {s['id']}、{s['title'][:30]} ({len(s['text'])} 字)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
