#!/usr/bin/env python3
"""居家失能個案家庭醫師照護方案（長照司）：解析方案本文與修正問答集。

本方案與健保署「居家醫療照護整合計畫」（居整計畫）是兩個不同的計畫——
主管機關、財源、申報系統、給付標準均不同——但自 115.06.30 修正後
兩者緊密綁定：照管專員僅得就居整計畫收案且同一團隊照顧之個案派案。
因此本站將兩案並列於同一頁，並另備對照表（scraper/dis_vs_hh.json）
逐項標明差異，避免混用。

用法：
    python3 scraper/extract_dis.py --plan-pdf 方案.pdf --qa-pdf 問答集.pdf \
        --plan-file <docs/files 檔名> --qa-file <docs/files 檔名> --out docs/data
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re

import fitz

# 問答集四欄 x 邊界（pt）：編號／類型／問題(Q)／回應內容(A)
COL_NO, COL_TYPE, COL_Q = 78, 122, 195

# 方案本文以大寫數字分章
BIG_NUM = ["壹", "貳", "參", "肆", "伍", "陸", "柒", "捌", "玖", "拾",
           "拾壹", "拾貳", "拾參", "拾肆", "拾伍"]
SEC_RE = re.compile(r"^\s*(拾[壹貳參肆伍]?|[壹貳參肆伍陸柒捌玖])、\s*(.{2,30})\s*$", re.M)

QA_HEADER_RE = re.compile(r"(編號|類型|問題\(Q\)|回應內容\(A\))+")


def reflow(text: str) -> str:
    """合併 PDF 硬換行，保留條列結構。"""
    mark = re.compile(r"^(\(\d{1,2}\)|（[一二三四五六七八九十]{1,3}）|\([一二三四五六七八九十]{1,3}\)|"
                      r"[一二三四五六七八九十]{1,3}、|\d{1,2}[.、]|[□■]|附表|附件|備註|註[：:])")
    out: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        prev = out[-1] if out else None
        if prev is None or mark.match(line) or re.search(r"[。！？：]$", prev):
            out.append(line)
        else:
            sep = " " if re.search(r"[A-Za-z0-9)%,;]$", prev) and re.match(r"^[A-Za-z0-9(]", line) else ""
            out[-1] = prev + sep + line
    return "\n".join(out)


def parse_plan(path: pathlib.Path, version: str, doc_no: str) -> dict:
    doc = fitz.open(path)
    text = "\n".join(p.get_text() for p in doc)
    text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.M)  # 頁碼

    marks = []
    for m in SEC_RE.finditer(text):
        idx = BIG_NUM.index(m.group(1)) + 1 if m.group(1) in BIG_NUM else None
        if idx is None or any(x[1] == idx for x in marks):
            continue
        marks.append((m.start(), idx, m.group(2).strip()))

    # 附件自「長期照護醫師意見書」起，不屬本文章節
    body_end = text.find("長期照護醫師意見書", marks[-1][0] if marks else 0)
    if body_end < 0:
        body_end = len(text)

    sections = []
    for i, (pos, n, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else body_end
        chunk = text[pos:min(end, body_end)]
        body = chunk.split("\n", 1)[1] if "\n" in chunk else ""
        sections.append({"no": n, "id": BIG_NUM[n - 1], "title": title, "text": reflow(body)})

    # 附件：醫師意見書表單／ICD 對照表／個案管理申報紀錄
    icd_at = text.find("與失能相關特定疾病ICD-10", body_end)
    rec_at = text.find("個案管理申報紀錄", icd_at if icd_at > 0 else body_end)
    if rec_at > 0:  # 標題含前一行「居家失能個案家庭醫師照顧方案」
        rec_at = text.rfind("居家失能個案家庭醫師照顧方案", body_end, rec_at)
    bounds = [b for b in (body_end, icd_at, rec_at, len(text)) if b > 0]
    names = ["附件1　長期照護醫師意見書（表單）", "與失能相關特定疾病 ICD-10 碼",
             "附件2　個案管理申報紀錄（表單）"]
    attachments = []
    for i, name in enumerate(names):
        if i + 1 >= len(bounds):
            break
        attachments.append({"no": 100 + i, "id": f"附{i + 1}", "title": name,
                            "text": reflow(text[bounds[i]:bounds[i + 1]])})

    # 意見書表單自身的公告沿革
    form_revs = []
    for m in re.finditer(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*衛部[顧照]字第?\s*(\d+)\s*號公告(修訂)?",
                         attachments[0]["text"] if attachments else ""):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        form_revs.append({"date": f"{y + 1911:04d}-{mo:02d}-{d:02d}",
                          "date_roc": f"{y}.{mo:02d}.{d:02d}",
                          "doc_no": f"衛部{'顧' if '顧' in m.group(0) else '照'}字第{m.group(4)}號",
                          "kind": m.group(5) or "訂定"})

    period = ""
    for s in sections:
        if s["title"] == "期程":
            pm = re.search(r"執行期間為自(.+?)止", s["text"])
            period = pm.group(1).strip() + "止" if pm else s["text"]
    return {
        "title": "居家失能個案家庭醫師照護方案",
        "agency": "衛生福利部長期照顧司",
        "version": version,
        "doc_no": doc_no,
        "period": period,
        "sections": sections,
        "attachments": attachments,
        "form_revisions": form_revs,
    }


def h_rules(page) -> list[float]:
    ys = set()
    for dr in page.get_drawings():
        for it in dr["items"]:
            if it[0] == "re":
                r = it[1]
                if abs(r.y1 - r.y0) < 2 and (r.x1 - r.x0) > 20:
                    ys.add(round((r.y0 + r.y1) / 2, 1))
            elif it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 2 and abs(a.x - b.x) > 20:
                    ys.add(round((a.y + b.y) / 2, 1))
    out: list[float] = []
    for y in sorted(ys):
        if not out or y - out[-1] > 2:
            out.append(y)
    return out


def band_columns(words: list) -> tuple[str, str, str, str]:
    rows: dict[float, list[tuple[float, str]]] = {}
    for x0, y0, x1, y1, w, *_ in words:
        key = min(rows, key=lambda k: abs(k - y0), default=None)
        if key is None or abs(key - y0) > 4:
            key = round(y0, 1)
        rows.setdefault(key, []).append((x0, w))
    cols = ["", "", "", ""]
    for y in sorted(rows):
        for x, w in sorted(rows[y]):
            i = 0 if x < COL_NO else 1 if x < COL_TYPE else 2 if x < COL_Q else 3
            cols[i] += w
    return tuple(cols)  # type: ignore[return-value]


def parse_qa(path: pathlib.Path, img_dir: pathlib.Path, img_prefix: str) -> dict:
    doc = fitz.open(path)
    version, version_date = "", ""
    m = re.search(r"更新時間：\s*(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", doc[0].get_text())
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        version = f"{y}.{mo:02d}.{d:02d}"
        version_date = f"{y + 1911:04d}-{mo:02d}-{d:02d}"

    entries: list[dict] = []
    current: dict | None = None
    for pno, page in enumerate(doc):
        rules = h_rules(page)
        words = page.get_text("words")
        # 內嵌圖片（例：照管系統查詢路徑截圖）依所在 y 歸給該題
        images = []
        for xref, *_ in page.get_images(full=True):
            for r in page.get_image_rects(xref):
                name = f"{img_prefix}-p{pno + 1}-{xref}.png"
                pix = fitz.Pixmap(doc, xref)
                if pix.n - pix.alpha >= 4:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img_dir.mkdir(parents=True, exist_ok=True)
                pix.save(img_dir / name)
                images.append((r.y0, name))

        for top, bot in zip(rules, rules[1:]):
            band = [w for w in words if top <= w[1] < bot]
            no_txt, kind, ques, ans = band_columns(band)
            joined = (no_txt + kind + ques + ans).strip()
            if not joined or QA_HEADER_RE.fullmatch(joined):
                continue
            m_no = re.fullmatch(r"\d{1,3}", no_txt.strip())
            if m_no:
                if current:
                    entries.append(current)
                current = {"no": int(m_no.group(0)), "category": kind,
                           "question": ques, "answer": ans, "images": []}
            elif current is not None:
                current["category"] += kind
                current["question"] += ques
                current["answer"] += ans
            if current is not None:
                current["images"] += [n for y, n in images if top <= y < bot]
    if current:
        entries.append(current)

    for e in entries:
        e["question"] = reflow(e["question"]).strip()
        e["answer"] = reflow(e["answer"]).strip()
        e["category"] = e["category"].strip()
    return {"title": "居家失能個案家庭醫師照護方案修正問答集",
            "version": version, "version_date": version_date, "entries": entries}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan-pdf", required=True)
    ap.add_argument("--qa-pdf", required=True)
    ap.add_argument("--plan-file", default="")
    ap.add_argument("--qa-file", default="")
    ap.add_argument("--plan-version", default="115.06.30")
    ap.add_argument("--plan-doc-no", default="衛部顧字第1151961986號")
    ap.add_argument("--out", default="docs/data")
    ap.add_argument("--img-out", default="docs/img")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plan = parse_plan(pathlib.Path(args.plan_pdf), args.plan_version, args.plan_doc_no)
    qa = parse_qa(pathlib.Path(args.qa_pdf), pathlib.Path(args.img_out), "dis-qa")

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    plan["generated_at"], plan["file"] = now, args.plan_file
    qa["generated_at"], qa["file"] = now, args.qa_file

    (out / "dis_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "dis_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8")

    # 兩案對照表為人工比對之靜態資料，隨解析一併同步到 docs/data，避免兩處版本不一致
    cmp_src = pathlib.Path(__file__).parent / "dis_vs_hh.json"
    if cmp_src.exists():
        (out / "dis_vs_hh.json").write_text(cmp_src.read_text(encoding="utf-8"), encoding="utf-8")

    print(f"方案本文：{len(plan['sections'])} 章、附件 {len(plan['attachments'])} 份、"
          f"版本 {plan['version']} {plan['doc_no']}")
    for s in plan["sections"]:
        print(f"  {s['id']}、{s['title']} ({len(s['text'])} 字)")
    for a in plan["attachments"]:
        print(f"  [{a['id']}] {a['title']} ({len(a['text'])} 字)")
    print(f"  期程：{plan['period']}")
    print(f"  意見書表單沿革：{len(plan['form_revisions'])} 筆")
    print(f"\n問答集：{len(qa['entries'])} 題、更新時間 {qa['version']}")
    for e in qa["entries"]:
        print(f"  {e['no']}. [{e['category']}] {e['question'][:26]}"
              + (f"　（含圖 {len(e['images'])}）" if e["images"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
