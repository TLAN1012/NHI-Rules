#!/usr/bin/env python3
"""把藥品給付規定拆解成逐條規定，輸出 rules.json。

兩種輸入模式（可並用，完整 PDF 優先）：
1. --full-pdf：一份完整的藥品給付規定 PDF（官網「整份帶走」檔），
   自動切出通則與第 1~15 節。這是首選來源。
2. chapters_dir：目錄內含檔名帶「通則」或「第X節」的章節檔案，
   支援 .pdf（PyMuPDF）/.odt（解 content.xml）/.doc（antiword）。
   用於完整 PDF 缺漏時補章。

用法：
    python3 scraper/extract_rules.py --full-pdf docs/files/完整給付規定.pdf \
        --out docs/data/rules.json
    python3 scraper/extract_rules.py cache/chapters --out docs/data/rules.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import zipfile

CH_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
          "十五": 15, "十六": 16, "十七": 17}

CHAPTER_NAMES = {
    1: "神經系統藥物", 2: "心臟血管及腎臟藥物", 3: "代謝及營養劑", 4: "血液治療藥物",
    5: "激素及影響內分泌機轉藥物", 6: "呼吸道藥物", 7: "腸胃藥物", 8: "免疫製劑",
    9: "抗癌瘤藥物", 10: "抗微生物劑", 11: "解毒劑", 12: "耳鼻喉科製劑",
    13: "皮膚科製劑", 14: "眼科製劑", 15: "婦科製劑",
}

PAGE_HEADER = re.compile(r"^\s*\(\d{2,3}\.\d{1,2}\.\d{1,2}\s*更新\)\s*$")
PAGE_NUMBER = re.compile(r"^\s*\d{1,3}\s*$")


def text_from_pdf(path: pathlib.Path) -> str:
    import fitz

    doc = fitz.open(path)
    return "\n".join(page.get_text() for page in doc)


def text_from_odt(path: pathlib.Path) -> str:
    with zipfile.ZipFile(path) as z:
        xml = z.read("content.xml").decode("utf-8")
    xml = re.sub(r"<text:line-break/>", "\n", xml)
    xml = re.sub(r"</text:p>", "\n", xml)
    xml = re.sub(r"<[^>]+>", "", xml)
    xml = xml.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&apos;", "'").replace("&quot;", '"')
    return xml


def text_from_doc(path: pathlib.Path) -> str:
    out = subprocess.run(["antiword", "-m", "UTF-8.txt", str(path)],
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8", errors="replace")


def clean_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.rstrip()
        if PAGE_HEADER.match(line) or PAGE_NUMBER.match(line):
            continue
        lines.append(line)
    return lines


def chapter_of(filename: str) -> tuple[int | None, str]:
    if "通則" in filename:
        return 0, "通則"
    # 注意：中文數字在 Unicode 非連續區段，不能用 [一-九] 這類範圍
    m = re.match(r"第(十[一二三四五六七]?|[一二三四五六七八九])節?[_\s]*([^_.]*)", filename)
    if m:
        num = CH_NUM.get(m.group(1))
        return num, CHAPTER_NAMES.get(num, m.group(2))
    return None, filename


def split_rules(lines: list[str], chapter: int) -> list[dict]:
    """依「章號.節號…」條號切分成逐條規定。"""
    rule_re = re.compile(rf"^\s*({chapter}(?:\.\d{{1,2}}){{1,3}})\.\s*(.*)$")
    rules: list[dict] = []
    current: dict | None = None
    preamble: list[str] = []
    for line in lines:
        m = rule_re.match(line)
        if m:
            if current:
                rules.append(current)
            current = {"id": m.group(1), "heading": m.group(2).strip(), "lines": []}
        elif current is not None:
            current["lines"].append(line)
        else:
            preamble.append(line)
    if current:
        rules.append(current)

    out = []
    for r in rules:
        body = "\n".join(l for l in r["lines"] if l.strip())
        # 條號只有兩層且沒有內文的多半是小節標題（如 1.1. 鎮痛劑），仍保留供瀏覽
        out.append({"id": r["id"], "heading": r["heading"], "text": body})
    return out


def split_general(lines: list[str]) -> list[dict]:
    """通則依「一、二、…」切分。"""
    item_re = re.compile(r"^\s*([一二三四五六七八九十]+)、\s*(.*)$")
    rules, current = [], None
    for line in lines:
        m = item_re.match(line)
        if m:
            if current:
                rules.append(current)
            current = {"id": f"通則{m.group(1)}", "heading": "", "lines": [m.group(2)]}
        elif current is not None:
            current["lines"].append(line)
    if current:
        rules.append(current)
    return [
        {"id": r["id"], "heading": "", "text": "\n".join(l for l in r["lines"] if l.strip())}
        for r in rules
    ]


def fallback_chapter_text(pdf_path: pathlib.Path, chapter: int) -> list[str]:
    """從整份 PDF 中切出指定章節的文字（存檔截斷/缺章時的備援）。"""
    import fitz

    doc = fitz.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)
    name = CHAPTER_NAMES[chapter]
    nxt = CHAPTER_NAMES.get(chapter + 1)
    start = text.find(name)
    if start < 0:
        return []
    end = text.find(nxt, start) if nxt else -1
    seg = text[start:end] if end > 0 else text[start:]
    return clean_lines(seg)


VERSION_RE = re.compile(r"\((\d{2,3}\.\d{1,2}\.\d{1,2})\s*更新\)")
APPENDIX_RE = re.compile(r"^\s*(附表[一二三四五六七八九十]|藥品事前審查申請表)", re.M)


def build_from_full_pdf(pdf_path: pathlib.Path) -> dict[int, dict]:
    """從一份完整的藥品給付規定 PDF 切出通則與各章節，拆成逐條規定。"""
    import fitz

    doc = fitz.open(pdf_path)
    text = "\n".join(p.get_text() for p in doc)

    # 章節起點：內文中的「第N節」標題（避免誤中目錄，取條文密集區前的最後標記即可）
    marks: dict[int, int] = {}
    for m in re.finditer(r"第\s*(\d{1,2})\s*節", text):
        num = int(m.group(1))
        if num in CHAPTER_NAMES and num not in marks:
            marks[num] = m.start()

    chapters_meta: dict[int, dict] = {}

    def segment(start: int, end: int) -> str:
        return text[start:end if end > 0 else len(text)]

    # 通則：文件開頭到第 1 節
    if 1 in marks:
        seg = segment(0, marks[1])
        rules = split_general(clean_lines(seg))
        ver = VERSION_RE.search(seg)
        if rules:
            chapters_meta[0] = {
                "chapter": 0, "name": "通則",
                "version_label": ver.group(1) if ver else "",
                "file": pdf_path.name, "count": len(rules), "rules": rules,
            }

    nums = sorted(marks)
    for i, num in enumerate(nums):
        end = marks[nums[i + 1]] if i + 1 < len(nums) else -1
        seg = segment(marks[num], end)
        if end < 0:
            # 最後一章：在附表/申請表區之前截斷
            cut = None
            for m in APPENDIX_RE.finditer(seg):
                cut = m.start()
                break
            if cut:
                seg = seg[:cut]
        rules = split_rules(clean_lines(seg), num)
        ver = VERSION_RE.search(seg)
        if rules:
            chapters_meta[num] = {
                "chapter": num, "name": CHAPTER_NAMES[num],
                "version_label": ver.group(1) if ver else "",
                "file": pdf_path.name, "count": len(rules), "rules": rules,
            }
    return chapters_meta


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("chapters_dir", nargs="?", help="章節檔案目錄（可省略，若已提供 --full-pdf）")
    ap.add_argument("--full-pdf", help="完整的藥品給付規定 PDF（首選來源）")
    ap.add_argument("--fallback-pdf", help="整份 PDF（缺章時備援）")
    ap.add_argument("--out", default="docs/data/rules.json")
    args = ap.parse_args()

    chapters_meta: dict[int, dict] = {}
    all_rules: list[dict] = []

    if args.full_pdf:
        chapters_meta = build_from_full_pdf(pathlib.Path(args.full_pdf))

    for path in sorted(pathlib.Path(args.chapters_dir).iterdir()) if args.chapters_dir else []:
        num, name = chapter_of(path.name)
        if num is None:
            continue
        if path.suffix == ".pdf":
            text = text_from_pdf(path)
        elif path.suffix == ".odt":
            text = text_from_odt(path)
        elif path.suffix == ".doc":
            text = text_from_doc(path)
        else:
            continue
        # 同章有多個格式時，取條文數較多者
        lines = clean_lines(text)
        rules = split_general(lines) if num == 0 else split_rules(lines, num)
        label = re.search(r"\((\d{2,3}\.\d{1,2}\.\d{1,2})[^)]*\)", path.name)
        if args.full_pdf and num in chapters_meta:
            continue  # 完整 PDF 為首選來源，章節檔僅補缺
        if num not in chapters_meta or len(rules) > chapters_meta[num]["count"]:
            chapters_meta[num] = {
                "chapter": num,
                "name": name,
                "version_label": label.group(1) if label else "",
                "file": path.name,
                "count": len(rules),
                "rules": rules,
            }

    missing = [n for n in [0, *CHAPTER_NAMES] if n not in chapters_meta]
    if args.fallback_pdf and missing:
        for num in missing:
            if num == 0:
                continue
            lines = fallback_chapter_text(pathlib.Path(args.fallback_pdf), num)
            rules = split_rules(lines, num)
            if rules:
                chapters_meta[num] = {
                    "chapter": num,
                    "name": CHAPTER_NAMES[num],
                    "version_label": "",
                    "file": pathlib.Path(args.fallback_pdf).name + " (fallback)",
                    "count": len(rules),
                    "rules": rules,
                }

    for num in sorted(chapters_meta):
        meta = chapters_meta[num]
        for r in meta["rules"]:
            all_rules.append({
                "id": r["id"],
                "chapter": meta["chapter"],
                "chapter_name": meta["name"],
                "heading": r["heading"],
                "text": r["text"],
            })

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "chapters": [
            {k: v for k, v in m.items() if k != "rules"}
            for m in (chapters_meta[n] for n in sorted(chapters_meta))
        ],
        "rules": all_rules,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"章節 {len(chapters_meta)}，條文 {len(all_rules)} → {out}")
    for n in sorted(chapters_meta):
        m = chapters_meta[n]
        print(f"  第{n}節 {m['name']}: {m['count']} 條 ({m['file']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
