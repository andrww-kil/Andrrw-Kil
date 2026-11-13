#!/usr/bin/env python3
"""네이버 메일 정리 스크립트 (IMAP)

사용법
  1단계 - 현황 보기 (아무것도 바꾸지 않음):
      python naver_cleanup.py report
    -> 보낸사람별 메일 개수를 report.csv 로 저장하고 상위 40개를 화면에 출력

  2단계 - 규칙 미리보기 (아무것도 바꾸지 않음):
      python naver_cleanup.py apply --dry-run
    -> rules.json 규칙대로 하면 몇 개가 어떻게 처리될지 출력

  3단계 - 실제 적용:
      python naver_cleanup.py apply
    -> 'trash' 는 휴지통으로 이동(복구 가능), 'move' 는 지정 폴더로 이동

준비물
  - 네이버 메일 > 환경설정 > POP3/IMAP 설정 > IMAP '사용함'
  - 2단계 인증 사용 시 '애플리케이션 비밀번호' 발급
  - 아이디/비밀번호는 실행할 때 입력합니다(어디에도 저장하지 않음).
"""
import argparse
import base64
import csv
import getpass
import imaplib
import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

HOST = "imap.naver.com"
PORT = 993
BATCH = 500
HERE = Path(__file__).resolve().parent
TRASH_CANDIDATES = ["Deleted Messages", "Trash", "휴지통"]


# ---------- IMAP 폴더 이름(한글) 인코딩: modified UTF-7 ----------
def imap_utf7_encode(s: str) -> str:
    out, buf = [], []

    def flush():
        if buf:
            b = "".join(buf).encode("utf-16-be")
            out.append("&" + base64.b64encode(b).decode().rstrip("=").replace("/", ",") + "-")
            buf.clear()

    for ch in s:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            buf.append(ch)
    flush()
    return "".join(out)


def imap_utf7_decode(s: str) -> str:
    def repl(m):
        body = m.group(1)
        if body == "":
            return "&"
        body = body.replace(",", "/")
        body += "=" * (-len(body) % 4)
        return base64.b64decode(body).decode("utf-16-be")

    return re.sub(r"&([^-]*)-", repl, s)


def q(name: str) -> str:
    return '"' + imap_utf7_encode(name).replace('"', '\\"') + '"'


# ---------- 연결 ----------
def connect():
    user = input("네이버 아이디(@naver.com 앞부분): ").strip()
    pw = getpass.getpass("비밀번호 또는 애플리케이션 비밀번호(입력이 안 보여도 정상): ")
    m = imaplib.IMAP4_SSL(HOST, PORT)
    try:
        m.login(user, pw)
    except imaplib.IMAP4.error as e:
        sys.exit(f"로그인 실패: {e}\n- IMAP '사용함' 설정 확인\n- 2단계 인증이면 애플리케이션 비밀번호 사용")
    return m


def list_folders(m):
    typ, data = m.list()
    names = []
    for raw in data or []:
        line = raw.decode(errors="replace")
        mm = re.search(r'\) "[^"]*" (.+)$', line)
        if mm:
            names.append(imap_utf7_decode(mm.group(1).strip().strip('"')))
    return names


def find_trash(m):
    folders = list_folders(m)
    for c in TRASH_CANDIDATES:
        if c in folders:
            return c
    sys.exit(f"휴지통 폴더를 찾지 못했습니다. 폴더 목록: {folders}")


def decode(s):
    try:
        return str(make_header(decode_header(s or "")))
    except Exception:
        return s or ""


def fetch_headers(m, folder="INBOX"):
    """(uid, 주소, 이름, 날짜) 목록을 돌려줌. 메일은 읽음 처리되지 않음(PEEK)."""
    typ, _ = m.select(q(folder), readonly=True)
    if typ != "OK":
        sys.exit(f"폴더 열기 실패: {folder}")
    typ, data = m.uid("search", None, "ALL")
    uids = data[0].split() if data and data[0] else []
    rows = []
    for i in range(0, len(uids), BATCH):
        chunk = b",".join(uids[i:i + BATCH])
        typ, resp = m.uid("fetch", chunk, "(BODY.PEEK[HEADER.FIELDS (FROM DATE)])")
        for item in resp:
            if not isinstance(item, tuple):
                continue
            meta, hdr = item
            um = re.search(rb"UID (\d+)", meta)
            if not um:
                continue
            text = hdr.decode(errors="replace")
            fm = re.search(r"^From:(.*(?:\r?\n[ \t].*)*)", text, re.M | re.I)
            dm = re.search(r"^Date:(.*)", text, re.M | re.I)
            name, addr = parseaddr(decode(fm.group(1).strip()) if fm else "")
            try:
                dt = parsedate_to_datetime(dm.group(1).strip()) if dm else None
                if dt and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except Exception:
                dt = None
            rows.append((um.group(1).decode(), addr.lower(), name, dt))
        print(f"  헤더 읽는 중... {min(i + BATCH, len(uids))}/{len(uids)}", end="\r")
    print()
    return rows


# ---------- 1단계: 현황 ----------
def cmd_report(args):
    m = connect()
    print("폴더 목록:", ", ".join(list_folders(m)))
    rows = fetch_headers(m, args.folder)
    by_addr = Counter(r[1] for r in rows)
    names = {r[1]: r[2] for r in rows}
    latest = {}
    for _, a, _, dt in rows:
        if dt and (a not in latest or dt > latest[a]):
            latest[a] = dt
    out = HERE / "report.csv"
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["보낸사람주소", "이름", "도메인", "개수", "최근수신"])
        for a, n in by_addr.most_common():
            w.writerow([a, names.get(a, ""), a.split("@")[-1], n,
                        latest[a].strftime("%Y-%m-%d") if a in latest else ""])
    print(f"\n[{args.folder}] 총 {len(rows)}개, 보낸사람 {len(by_addr)}명")
    print(f"{'개수':>6}  보낸사람")
    for a, n in by_addr.most_common(40):
        print(f"{n:>6}  {a}  ({names.get(a, '')})")
    print(f"\n전체 목록 저장: {out}")
    m.logout()


# ---------- 2·3단계: 규칙 적용 ----------
def load_rules():
    p = HERE / "rules.json"
    if not p.exists():
        sys.exit("rules.json 이 없습니다. rules.example.json 을 복사해서 만드세요.")
    return json.loads(p.read_text(encoding="utf-8"))


def match(rule, addr, dt, now):
    pats = rule["match"] if isinstance(rule["match"], list) else [rule["match"]]
    if not any(p.lower() in addr for p in pats):
        return False
    days = rule.get("older_than_days")
    if days is not None:
        if dt is None or dt > now - timedelta(days=days):
            return False
    return True


def cmd_apply(args):
    rules = load_rules()
    m = connect()
    rows = fetch_headers(m, args.folder)
    now = datetime.now(timezone.utc)
    plan = {}  # (action, folder) -> [uid]
    for uid, addr, _, dt in rows:
        for r in rules:  # 위에 있는 규칙이 우선
            if match(r, addr, dt, now):
                if r["action"] != "keep":
                    plan.setdefault((r["action"], r.get("folder", "")), []).append(uid)
                break
    total = sum(len(v) for v in plan.values())
    print(f"\n처리 대상 {total}개 / 전체 {len(rows)}개")
    for (act, folder), uids in plan.items():
        print(f"  {act:<5} {folder or '휴지통':<15} {len(uids)}개")
    if args.dry_run or total == 0:
        print("\n(미리보기만 했습니다. 실제 적용은 --dry-run 없이 실행)")
        m.logout()
        return
    if input("\n위대로 적용할까요? (yes 입력): ").strip().lower() != "yes":
        sys.exit("취소했습니다.")
    trash = find_trash(m)
    existing = set(list_folders(m))
    m.select(q(args.folder))
    for (act, folder), uids in plan.items():
        dest = trash if act == "trash" else folder
        if dest not in existing:
            m.create(q(dest))
            existing.add(dest)
        for i in range(0, len(uids), BATCH):
            chunk = ",".join(uids[i:i + BATCH])
            typ, _ = m.uid("copy", chunk, q(dest))
            if typ != "OK":
                sys.exit(f"이동 실패: {dest} (여기까지 처리된 것은 안전합니다)")
            m.uid("store", chunk, "+FLAGS.SILENT", r"(\Deleted)")
            m.expunge()
            print(f"  {dest}: {min(i + BATCH, len(uids))}/{len(uids)}", end="\r")
        print()
    print("완료. 휴지통으로 간 메일은 네이버 휴지통에서 복구할 수 있습니다.")
    m.logout()


def main():
    ap = argparse.ArgumentParser(description="네이버 메일 정리")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("report", help="보낸사람별 현황 (변경 없음)")
    r.add_argument("--folder", default="INBOX")
    a = sub.add_parser("apply", help="rules.json 적용")
    a.add_argument("--folder", default="INBOX")
    a.add_argument("--dry-run", action="store_true", help="미리보기만")
    args = ap.parse_args()
    {"report": cmd_report, "apply": cmd_apply}[args.cmd](args)


if __name__ == "__main__":
    main()
