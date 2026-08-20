#!/usr/bin/env python3
"""居家醫療照護整合計畫：解析計畫本文與問答集，並標示兩者版本落差。

問答集（109.09.28 第五版）與現行計畫本文（115.03.18）相距約 5 年半，
其間計畫歷經多次公告修訂，部分問答內容可能已不符現行規定。本腳本：

1. 解析計畫本文章節與完整修訂沿革
2. 解析問答集（五欄表格：題號／提問單位／問題／說明／修訂說明）
3. 版本落差處理：
   - 列出問答集定版後的所有計畫修訂公告
   - 依 hh_qa_revisions.json 之 section_map 換算舊條號為現行條號，
     並以現行章節標題驗證對照表（不符即中止，避免誤改）
   - 併入人工比對之扞格修訂（revised_answer／explain），
     原文一律保留於 answer 欄位，前端並陳對照

修訂內容一律來自 hh_qa_revisions.json 這份可覆核的人工比對表，
本腳本只負責套用與驗證，不自行判讀法規。

用法：
    python3 scraper/extract_hh.py --plan-pdf 計畫.pdf --qa-pdf 問答集.pdf \
        --plan-file <docs/files 檔名> --qa-file <docs/files 檔名> --out docs/data
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re

import fitz

# 問答集五欄 x 邊界（pt）
COL_NO, COL_UNIT, COL_Q, COL_A = 95, 145, 290, 450

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
          "十五": 15, "十六": 16, "十七": 17, "十八": 18}

REV_RE = re.compile(r"(\d{2,3})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*健保醫字第?\s*(\d+)\s*號公告(訂定|修訂)")
SEC_RE = re.compile(r"^\s*([一二三四五六七八九十]+)、\s*(.{2,40})$", re.M)
CITE_RE = re.compile(r"計畫第([一二三四五六七八九十]+)點")


def roc_to_iso(y: int, m: int, d: int) -> str:
    return f"{y + 1911:04d}-{m:02d}-{d:02d}"


def parse_plan(path: pathlib.Path) -> dict:
    doc = fitz.open(path)
    text = "\n".join(p.get_text() for p in doc)
    text = re.sub(r"^\s*\d{1,3}\s*$", "", text, flags=re.M)  # 頁碼

    revisions = []
    for m in REV_RE.finditer(text):
        y, mo, d, no, kind = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4), m.group(5)
        revisions.append({
            "date": roc_to_iso(y, mo, d),
            "date_roc": f"{y}.{mo:02d}.{d:02d}",
            "doc_no": f"健保醫字第{no}號",
            "kind": kind,
        })
    # 去重並排序（沿革列於首頁，正文可能重複引用）
    seen, uniq = set(), []
    for r in sorted(revisions, key=lambda x: x["date"]):
        if r["date"] not in seen:
            seen.add(r["date"])
            uniq.append(r)

    # 主體章節：一、～十六、（附件內另有重複編號，取第一輪）
    marks, seen_no = [], set()
    for m in SEC_RE.finditer(text):
        n = CN_NUM.get(m.group(1))
        if n is None or n in seen_no:
            continue
        seen_no.add(n)
        marks.append((m.start(), n, m.group(2).strip()))
    sections = []
    for i, (pos, n, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[pos:end].split("\n", 1)[1] if "\n" in text[pos:end] else ""
        sections.append({"no": n, "id": m_cn(n), "title": title, "text": reflow(body)})

    # 附件併於「十六、附則」之後，量體遠大於本文，拆為獨立條目便於閱讀
    attach = []
    for sec in sections:
        i = sec["text"].find("附件1「全民健康保險居家醫療照護整合計畫」")
        if sec["no"] == 16 and i > 0:
            attach.append({"no": 100, "id": "附件", "title": "附件1、給付項目及支付標準",
                           "text": sec["text"][i:]})
            sec["text"] = sec["text"][:i].rstrip()
    sections += attach

    return {
        "title": "全民健康保險居家醫療照護整合計畫",
        "version": uniq[-1]["date_roc"] if uniq else "",
        "version_date": uniq[-1]["date"] if uniq else "",
        "revisions": uniq,
        "sections": sections,
    }


def m_cn(n: int) -> str:
    for k, v in CN_NUM.items():
        if v == n:
            return k
    return str(n)


def reflow(text: str) -> str:
    """合併 PDF 硬換行，保留條列結構。"""
    mark = re.compile(r"^(\(\d{1,2}\)|（[一二三四五六七八九十]{1,3}）|\([一二三四五六七八九十]{1,3}\)|"
                      r"[一二三四五六七八九十]{1,3}、|\d{1,2}\.|附表|備註)")
    out = []
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


def h_rules(page) -> list[float]:
    """表格橫線的 y 座標（框線以極扁的矩形或線段繪製）。

    題號在儲存格內垂直置中，多行儲存格的題號會落在第二行以後，
    因此不能以「哪一行有題號」判斷題目起點，必須改用框線切分列。
    """
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


def band_columns(words: list) -> tuple[str, str, str, str, str]:
    """把一個表格列（band）內的字依行、再依 x 邊界切成五欄。"""
    rows: dict[float, list[tuple[float, str]]] = {}
    for x0, y0, x1, y1, w, *_ in words:
        key = min(rows, key=lambda k: abs(k - y0), default=None)
        if key is None or abs(key - y0) > 4:
            key = round(y0, 1)
        rows.setdefault(key, []).append((x0, w))
    cols = ["", "", "", "", ""]
    for y in sorted(rows):
        for x, w in sorted(rows[y]):
            i = 0 if x < COL_NO else 1 if x < COL_UNIT else 2 if x < COL_Q else 3 if x < COL_A else 4
            cols[i] += w
    return tuple(cols)  # type: ignore[return-value]


HEADER_RE = re.compile(r"(題|號|提問|單位|問題\(Q\)|說明\(A\)|修訂說明)+")


def parse_qa(path: pathlib.Path) -> dict:
    doc = fitz.open(path)
    version = ""
    version_date = ""
    entries: list[dict] = []
    current: dict | None = None
    category = ""

    # 封面列出問答集自身的改版沿革，取日期最新者為現行版本
    cover = doc[0].get_text()
    qa_revs = []
    for m in re.finditer(r"(\d{2,3})\.(\d{1,2})\.(\d{1,2})\s*第([一二三四五六七八九十]+)版", cover):
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        qa_revs.append({"date": roc_to_iso(y, mo, d),
                        "label": f"{m.group(1)}.{m.group(2)}.{m.group(3)} 第{m.group(4)}版"})
    qa_revs.sort(key=lambda r: r["date"])
    if qa_revs:
        version = qa_revs[-1]["label"]
        version_date = qa_revs[-1]["date"]

    for page in doc:
        rules = h_rules(page)
        words = page.get_text("words")
        for top, bot in zip(rules, rules[1:]):
            band = [w for w in words if top <= w[1] < bot]
            if not band:
                continue
            no_txt, unit, ques, ans, note = band_columns(band)
            joined = (no_txt + unit + ques + ans + note).strip()

            if HEADER_RE.fullmatch(joined):          # 每頁重複的表頭
                continue
            if not joined:
                continue
            if no_txt.strip() == joined and not joined.isdigit() and len(joined) >= 3:
                category = joined                     # 跨欄的分類列
                continue

            m_no = re.fullmatch(r"\d{1,3}", no_txt.strip())
            if m_no:
                if current:
                    entries.append(current)
                current = {"no": int(m_no.group(0)), "category": category, "unit": unit,
                           "question": ques, "answer": ans, "note": note}
            elif current is not None:                 # 跨頁續接的儲存格
                current["unit"] += unit
                current["question"] += ques
                current["answer"] += ans
                current["note"] += note
    if current:
        entries.append(current)

    for e in entries:
        e["question"] = reflow(e["question"]).strip()
        e["answer"] = reflow(e["answer"]).strip()
        e["note"] = e["note"].strip()
        e["unit"] = e["unit"].strip()
        e["cites"] = sorted({CN_NUM[m.group(1)] for m in CITE_RE.finditer(e["answer"] + e["question"])
                             if m.group(1) in CN_NUM})
    return {"title": "「全民健康保險居家醫療照護整合計畫」之問答輯", "version": version,
            "version_date": version_date, "revisions": qa_revs, "entries": entries}


REV_FILE = pathlib.Path(__file__).parent / "hh_qa_revisions.json"
CITE_POINT_RE = re.compile(r"計畫第([一二三四五六七八九十]{1,3})點")


def apply_revisions(plan: dict, qa: dict) -> dict:
    """套用 hh_qa_revisions.json：條號換算 + 人工比對之扞格修訂。"""
    spec = json.loads(REV_FILE.read_text(encoding="utf-8"))
    titles = {s["no"]: s["title"] for s in plan["sections"]}

    # 驗證條號對照表：現行該點標題須與 expect 相符，否則中止（計畫再改版時會擋下）
    smap: dict[int, int] = {}
    for old, ent in spec["section_map"].items():
        if old.startswith("_"):
            continue
        new = ent["to"]
        if titles.get(new) != ent["expect"]:
            raise SystemExit(
                f"條號對照失效：現行第{m_cn(new)}點為「{titles.get(new)}」，"
                f"對照表預期「{ent['expect']}」。請重新比對 hh_qa_revisions.json。")
        smap[int(old)] = new

    revs = {r["no"]: r for r in spec["revisions"]}
    counts = {"renumber": 0, "substantive": 0, "premise": 0, "supplement": 0}

    for e in qa["entries"]:
        rev = revs.get(e["no"], {})
        moved: list[dict] = []

        if rev.get("revised_answer"):
            # 人工改寫者已使用現行條號，不再自動換算
            e["revised_answer"] = rev["revised_answer"]
        else:
            def sub(m: re.Match) -> str:
                old = CN_NUM.get(m.group(1))
                new = smap.get(old)
                if new is None:
                    return m.group(0)
                moved.append({"from": m_cn(old), "to": m_cn(new)})
                return f"計畫第{m_cn(new)}點"

            new_ans = CITE_POINT_RE.sub(sub, e["answer"])
            e["revised_answer"] = new_ans if new_ans != e["answer"] else ""

        # 去重後保留位移紀錄（同一題可能重複引用同一點）
        seen, uniq = set(), []
        for mv in moved:
            k = (mv["from"], mv["to"])
            if k not in seen:
                seen.add(k)
                uniq.append(mv)
        e["renumbered"] = uniq

        kind = rev.get("type") or ("renumber" if uniq else "")
        e["revision"] = {
            "type": kind,
            "explain": rev.get("explain", ""),
            "basis": [{"no": int(n), "cn": m_cn(int(n)), "title": titles.get(int(n), "")}
                      for n in rev.get("basis", [])],
        } if kind else None
        if kind:
            counts[kind] = counts.get(kind, 0) + 1

        # cite_map 改列現行條號（含舊條號供對照）
        e["cite_map"] = [{"old_no": n, "old_cn": m_cn(n), "no": smap.get(n, n),
                          "cn": m_cn(smap.get(n, n)), "current_title": titles.get(smap.get(n, n), "（現行計畫無此點）"),
                          "moved": n in smap}
                         for n in e["cites"]]

    qa["revision_summary"] = counts
    qa["revision_note"] = (
        "本頁問答之答覆已依現行計畫（%s）校訂：條號位移逕行換算，實質規定變更者另行改寫並註明理由。"
        "原始答覆（%s）一律保留，可於各題內展開對照。" % (plan["version"], qa["version"]))
    return qa


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--plan-pdf", required=True)
    ap.add_argument("--qa-pdf", required=True)
    ap.add_argument("--plan-file", default="")
    ap.add_argument("--qa-file", default="")
    ap.add_argument("--out", default="docs/data")
    args = ap.parse_args()

    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    plan = parse_plan(pathlib.Path(args.plan_pdf))
    qa = parse_qa(pathlib.Path(args.qa_pdf))

    # 版本落差：問答集定版日之後的計畫修訂
    qa_date = qa.get("version_date", "")
    later = [r for r in plan["revisions"] if qa_date and r["date"] > qa_date]

    qa = apply_revisions(plan, qa)

    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    plan["generated_at"], plan["file"] = now, args.plan_file
    qa["generated_at"], qa["file"] = now, args.qa_file
    qa["staleness"] = {
        "qa_date": qa_date,
        "plan_version": plan["version"],
        "plan_version_date": plan["version_date"],
        "later_revisions": later,
    }

    (out / "hh_plan.json").write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "hh_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"計畫本文：{len(plan['sections'])} 章、沿革 {len(plan['revisions'])} 筆、版本 {plan['version']}")
    for s in plan["sections"]:
        print(f"  {s['id']}、{s['title'][:26]} ({len(s['text'])} 字)")
    print(f"\n問答集：{len(qa['entries'])} 題、版本 {qa['version']}")
    cats = list(dict.fromkeys(e["category"] for e in qa["entries"] if e["category"]))
    for c in cats:
        print(f"  {c}: {sum(1 for e in qa['entries'] if e['category'] == c)} 題")
    print(f"\n版本落差：問答集定版 {qa_date} 之後，計畫另有 {len(later)} 次修訂")
    for r in later:
        print(f"  {r['date_roc']} {r['doc_no']} {r['kind']}")
    cited = sum(1 for e in qa["entries"] if e["cites"])
    print(f"\n引用計畫條號之題目：{cited} 題（已換算為現行條號）")
    cs = qa["revision_summary"]
    print(f"校訂結果：條號位移 {cs.get('renumber', 0)} 題、實質變更 {cs.get('substantive', 0)} 題、"
          f"前提已變更 {cs.get('premise', 0)} 題、補充現行增訂 {cs.get('supplement', 0)} 題")
    for e in qa["entries"]:
        r = e.get("revision")
        if r and r["type"] in ("substantive", "premise"):
            print(f"  [{r['type']}] 第{e['no']}題　依據：" +
                  "、".join(f"第{b['cn']}點 {b['title']}" for b in r["basis"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
