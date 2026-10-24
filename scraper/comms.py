#!/usr/bin/env python3
"""供應端與處理端之間的訊息通道。

用法：
    python scraper/comms.py list [--from supplier] [--unanswered]
    python scraper/comms.py show <id>
    python scraper/comms.py send --from processor --subject "..." --body-file msg.md
                                 [--reply-to <id>] [--needs-reply] [--ref path ...]
    python scraper/comms.py validate

設計要點

**每則訊息是一個獨立檔案，只新增、永不修改。** 兩端都會推送到同一個 repo，
共用一份訊息檔必然撞 merge conflict，而自動化的一方撞到衝突時多半只會放棄
或強制覆蓋——兩種結果都會靜靜吃掉訊息。一訊息一檔之後衝突面歸零。

放在 `comms/` 而非 `incoming/`：投遞區有清除步驟，曾經因為「排除清單」寫法
把回執一起刪掉。訊息不該放在任何會被自動清理的目錄底下。

這裡只負責「把話留下來」。真正要讓對方讀到，靠的是對方下次執行時會來讀：
供應端每週排程跑、處理端則由人開啟工作階段。needs_reply 的訊息會由
comms workflow 開成 GitHub Issue，因為「通知到人」才是真正能喚醒另一端的途徑。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import re
import sys

SCHEMA = 1
PARTIES = ("supplier", "processor")
COMMS = pathlib.Path(__file__).resolve().parent.parent / "comms"
REQUIRED = ("schema", "id", "at", "from", "subject", "body")
# 保留中日韓文字：兩端以中文溝通，只留 [a-z0-9] 會讓所有中文主旨都塌成
# 同一個 slug，檔名失去辨識度，同秒同寄件者還可能直接撞名
SLUG_RE = re.compile(r"[^\w]+", re.UNICODE)


def slugify(text: str) -> str:
    slug = SLUG_RE.sub("-", text.strip()).strip("-").lower()
    return (slug[:40].rstrip("-") or "message")


def message_id(at: dt.datetime, sender: str, subject: str) -> str:
    return f"{at.strftime('%Y%m%dT%H%M%SZ')}-{sender}-{slugify(subject)}"


def load_all(comms: pathlib.Path) -> list[dict]:
    out = []
    for path in sorted(comms.glob("*.json")):
        try:
            msg = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            msg = {"_path": str(path), "_error": f"JSON 無法解析：{e}"}
        msg.setdefault("_path", str(path))
        out.append(msg)
    return out


def problems_in(msg: dict) -> list[str]:
    if "_error" in msg:
        return [msg["_error"]]
    bad = [f"缺少欄位 {f}" for f in REQUIRED if f not in msg]
    if msg.get("schema") != SCHEMA:
        bad.append(f"schema 應為 {SCHEMA}，實得 {msg.get('schema')!r}")
    if msg.get("from") not in PARTIES:
        bad.append(f"from 應為 {' 或 '.join(PARTIES)}，實得 {msg.get('from')!r}")
    if not str(msg.get("subject", "")).strip():
        bad.append("subject 不可為空")
    if not str(msg.get("body", "")).strip():
        bad.append("body 不可為空")
    expected = pathlib.Path(msg["_path"]).stem
    if msg.get("id") and msg["id"] != expected:
        bad.append(f"id（{msg['id']}）與檔名（{expected}）不一致")
    return bad


def cmd_send(args: argparse.Namespace) -> int:
    body = pathlib.Path(args.body_file).read_text(encoding="utf-8").strip() if args.body_file \
        else (args.body or "").strip()
    if not body:
        print("body 不可為空（用 --body 或 --body-file）", file=sys.stderr)
        return 2
    at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    mid = message_id(at, args.sender, args.subject)

    COMMS.mkdir(parents=True, exist_ok=True)
    path = COMMS / f"{mid}.json"
    # 同一秒內的同主旨訊息極少見，但撞名會覆蓋掉前一則，寧可明確失敗
    if path.exists():
        print(f"{path.name} 已存在，請換個主旨或稍後再送", file=sys.stderr)
        return 2

    msg = {
        "schema": SCHEMA,
        "id": mid,
        "at": at.isoformat().replace("+00:00", "Z"),
        "from": args.sender,
        "subject": args.subject,
        "body": body,
        "needs_reply": bool(args.needs_reply),
        "in_reply_to": args.reply_to,
        "refs": args.ref or [],
    }
    path.write_text(json.dumps(msg, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"已寫入 {path.relative_to(COMMS.parent)}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    msgs = [m for m in load_all(COMMS) if "_error" not in m]
    if args.sender:
        msgs = [m for m in msgs if m.get("from") == args.sender]
    if args.unanswered:
        answered = {m.get("in_reply_to") for m in load_all(COMMS)}
        msgs = [m for m in msgs if m.get("needs_reply") and m.get("id") not in answered]
    if not msgs:
        print("（沒有符合條件的訊息）")
        return 0
    for m in msgs:
        flag = "需回覆" if m.get("needs_reply") else "　　　"
        reply = f"　↩ {m['in_reply_to']}" if m.get("in_reply_to") else ""
        print(f"{m.get('at', '?'):21} {m.get('from', '?'):10} [{flag}] {m.get('subject', '')}{reply}")
        print(f"{'':21} {m.get('id', '?')}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    for m in load_all(COMMS):
        if m.get("id") == args.id or pathlib.Path(m["_path"]).stem == args.id:
            print(f"寄件者：{m.get('from')}　時間：{m.get('at')}")
            if m.get("in_reply_to"):
                print(f"回覆：{m['in_reply_to']}")
            if m.get("refs"):
                print(f"相關：{'、'.join(m['refs'])}")
            print(f"主旨：{m.get('subject')}\n")
            print(m.get("body", ""))
            return 0
    print(f"找不到訊息 {args.id}", file=sys.stderr)
    return 1


def cmd_validate(args: argparse.Namespace) -> int:
    msgs = load_all(COMMS)
    bad = 0
    for m in msgs:
        issues = problems_in(m)
        if issues:
            bad += 1
            name = pathlib.Path(m["_path"]).name
            for issue in issues:
                print(f"::error file={m['_path']}::{name}：{issue}")
    known = {m.get("id") for m in msgs}
    for m in msgs:
        target = m.get("in_reply_to")
        if target and target not in known:
            bad += 1
            print(f"::error file={m['_path']}::"
                  f"{pathlib.Path(m['_path']).name}：in_reply_to 指向不存在的訊息 {target}")
    print(f"檢查 {len(msgs)} 則訊息，{bad} 則有問題")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send", help="寫一則新訊息")
    s.add_argument("--from", dest="sender", required=True, choices=PARTIES)
    s.add_argument("--subject", required=True)
    s.add_argument("--body")
    s.add_argument("--body-file")
    s.add_argument("--reply-to", default=None)
    s.add_argument("--needs-reply", action="store_true")
    s.add_argument("--ref", action="append")
    s.set_defaults(func=cmd_send)

    l = sub.add_parser("list", help="列出訊息")
    l.add_argument("--from", dest="sender", choices=PARTIES)
    l.add_argument("--unanswered", action="store_true", help="只列出待回覆的")
    l.set_defaults(func=cmd_list)

    sh = sub.add_parser("show", help="顯示單則訊息")
    sh.add_argument("id")
    sh.set_defaults(func=cmd_show)

    v = sub.add_parser("validate", help="檢查所有訊息格式")
    v.set_defaults(func=cmd_validate)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
