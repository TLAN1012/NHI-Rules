#!/usr/bin/env python3
"""由 flows.json 產生流程圖 SVG（內嵌於頁面，不依賴任何外部程式庫）。

版面由本腳本計算，內容與依據條號放在 scraper/flows.json，規定異動時只需改資料。
節點可標 sec／plan，前端據以連到該計畫全文對應條號。

節點種類：start／step／decision／end／fail（不符合之出口）／note（旁註）
版面模型：以 12 欄格線分列排版，邊為明確指定，走正交折線。

用法：
    python3 scraper/build_flows.py --out docs/data
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re

W = 980           # 畫布寬
MARGIN = 24
GUTTER = 14
COLS = 12
FS = 13           # 內文字級
LH = 18           # 行高
PAD_X, PAD_Y = 12, 11
VGAP = 44         # 列間距（需容納邊上的標籤）
CELL = (W - 2 * MARGIN) / COLS


def text_em(s: str) -> float:
    """近似字寬（以 em 計）：CJK 與全形標點算 1，其餘算 0.55。"""
    return sum(1.0 if ord(c) > 0x2E80 else 0.55 for c in s)


def tokenize(s: str) -> list[str]:
    """CJK 逐字可斷行，拉丁字母與數字串不拆開。"""
    return re.findall(r"[A-Za-z0-9%().,:/＋+－\-–]+|\s+|.", s)


def wrap(s: str, max_em: float) -> list[str]:
    lines: list[str] = []
    for para in s.split("\n"):
        cur, cur_em = "", 0.0
        for tok in tokenize(para):
            if tok.isspace():
                tok = " "
            em = text_em(tok)
            if cur and cur_em + em > max_em:
                lines.append(cur.rstrip())
                cur, cur_em = "", 0.0
                if tok == " ":
                    continue
            cur += tok
            cur_em += em
        lines.append(cur.rstrip())
    return [ln for ln in lines if ln != ""] or [""]


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


class Box:
    def __init__(self, spec: dict, row: int):
        self.id = spec["id"]
        self.kind = spec.get("kind", "step")
        self.text = spec["text"]
        self.sec = spec.get("sec")
        self.plan = spec.get("plan", "")
        self.tint = spec.get("tint", "")   # hh／dis：以顏色標示所屬計畫
        self.row = row
        self.span = spec.get("span", 12)
        self.col = spec.get("col", (COLS - self.span) // 2)
        self.w = self.span * CELL - GUTTER
        inner = self.w - 2 * PAD_X - (14 if self.kind == "decision" else 0)
        self.lines = wrap(self.text, inner / FS)
        self.h = 2 * PAD_Y + len(self.lines) * LH
        self.x = MARGIN + self.col * CELL + GUTTER / 2
        self.y = 0.0

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    @property
    def bottom(self) -> float:
        return self.y + self.h

    @property
    def right(self) -> float:
        return self.x + self.w


def shape(b: Box) -> str:
    cls = f"fl-box fl-{b.kind}" + (f" fl-tint-{b.tint}" if b.tint else "")
    if b.kind == "decision":
        c = 12  # 切角以示判斷
        pts = " ".join(f"{px:.1f},{py:.1f}" for px, py in [
            (b.x + c, b.y), (b.right - c, b.y), (b.right, b.y + c),
            (b.right, b.bottom - c), (b.right - c, b.bottom), (b.x + c, b.bottom),
            (b.x, b.bottom - c), (b.x, b.y + c)])
        return f'<polygon class="{cls}" points="{pts}"/>'
    r = b.h / 2 if b.kind in ("start", "end") else 8
    return (f'<rect class="{cls}" x="{b.x:.1f}" y="{b.y:.1f}" '
            f'width="{b.w:.1f}" height="{b.h:.1f}" rx="{r:.1f}"/>')


def render_box(b: Box) -> str:
    body = shape(b)
    ty = b.y + PAD_Y + LH * 0.75
    for i, ln in enumerate(b.lines):
        tint = f" fl-tt-{b.tint}" if b.tint else ""
        body += (f'<text class="fl-text fl-t-{b.kind}{tint}" x="{b.cx:.1f}" '
                 f'y="{ty + i * LH:.1f}" text-anchor="middle">{esc(ln)}</text>')
    if b.sec:
        return (f'<a class="fl-link" href="#" data-sec="{b.sec}" '
                f'data-plan="{esc(b.plan)}"><title>跳至該計畫條文</title>{body}</a>')
    return body


def edge_path(a: Box, z: Box, kind: str) -> str:
    if kind == "side":                       # 同列向右的不符合出口
        return f"M {a.right:.1f} {a.cy:.1f} L {z.x - 7:.1f} {z.cy:.1f}"
    if abs(a.cx - z.cx) < 1:
        return f"M {a.cx:.1f} {a.bottom:.1f} L {z.cx:.1f} {z.y - 7:.1f}"
    mid = a.bottom + (z.y - a.bottom) / 2
    return (f"M {a.cx:.1f} {a.bottom:.1f} L {a.cx:.1f} {mid:.1f} "
            f"L {z.cx:.1f} {mid:.1f} L {z.cx:.1f} {z.y - 7:.1f}")


def label_pos(a: Box, z: Box, kind: str) -> tuple[float, float]:
    if kind == "side":
        return (a.right + z.x) / 2, a.cy - 7
    if abs(a.cx - z.cx) < 1:
        return a.cx + 6, a.bottom + (z.y - a.bottom) / 2 - 3
    return (a.cx + z.cx) / 2, a.bottom + (z.y - a.bottom) / 2 - 5


def build(flow: dict) -> str:
    boxes: dict[str, Box] = {}
    rows: list[list[Box]] = []
    for ri, row in enumerate(flow["rows"]):
        bs = [Box(spec, ri) for spec in row]
        for b in bs:
            boxes[b.id] = b
        rows.append(bs)

    y = MARGIN
    for bs in rows:
        for b in bs:
            b.y = y
        y += max(b.h for b in bs) + VGAP
    height = y - VGAP + MARGIN

    parts = [render_box(b) for bs in rows for b in bs]
    edges = []
    for e in flow["edges"]:
        a, z = boxes[e["from"]], boxes[e["to"]]
        kind = e.get("kind", "down")
        cls = "fl-edge" + (" fl-edge-fail" if kind == "side" else "")
        edges.append(f'<path class="{cls}" d="{edge_path(a, z, kind)}" '
                     f'marker-end="url(#fl-arrow{"-fail" if kind == "side" else ""})"/>')
        if e.get("label"):
            lx, ly = label_pos(a, z, kind)
            edges.append(f'<text class="fl-label" x="{lx:.1f}" y="{ly:.1f}" '
                         f'text-anchor="middle">{esc(e["label"])}</text>')

    defs = ('<defs>'
            '<marker id="fl-arrow" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path class="fl-arrow" d="M 0 0 L 10 5 L 0 10 z"/></marker>'
            '<marker id="fl-arrow-fail" viewBox="0 0 10 10" refX="9" refY="5" '
            'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
            '<path class="fl-arrow fl-arrow-f" d="M 0 0 L 10 5 L 0 10 z"/></marker>'
            '</defs>')
    return (f'<svg class="flow-svg" viewBox="0 0 {W} {height:.0f}" '
            f'role="img" aria-label="{esc(flow["title"])}" '
            f'xmlns="http://www.w3.org/2000/svg">'
            f'<title>{esc(flow["title"])}</title>{defs}'
            + "".join(edges) + "".join(parts) + "</svg>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--spec", default=str(pathlib.Path(__file__).parent / "flows.json"))
    ap.add_argument("--out", default="docs/data")
    args = ap.parse_args()

    spec = json.loads(pathlib.Path(args.spec).read_text(encoding="utf-8"))
    out = []
    for flow in spec["flows"]:
        svg = build(flow)
        out.append({k: flow.get(k, "") for k in ("id", "title", "subtitle", "plan", "legend")}
                   | {"svg": svg})
        print(f"  {flow['id']}：{flow['title']}"
              f"（{sum(len(r) for r in flow['rows'])} 節點、{len(flow['edges'])} 邊、"
              f"{len(svg) // 1024} KB）")
    path = pathlib.Path(args.out) / "flows.json"
    path.write_text(json.dumps({"flows": out}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"共 {len(out)} 張流程圖 → {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
