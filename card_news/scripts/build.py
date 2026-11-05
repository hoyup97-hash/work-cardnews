"""
카드뉴스 사이트 빌드 스크립트

cards/ 폴더의 HTML 파일을 모아 _site/ 폴더에 배포용 사이트를 만든다.
- 파일 이름 규칙: YYYY-MM-DD.html  (같은 날 두 번째부터는 YYYY-MM-DD-2.html)
- 메인 페이지(index.html)의 '오늘의 카드뉴스'와 '지난 카드뉴스' 목록을 자동으로 만든다.
- 규칙에 안 맞는 파일은 목록에서 빠지고, 로그에 경고가 찍힌다 (배포는 멈추지 않음).

GitHub Actions에서 자동 실행되므로 담당자가 직접 돌릴 필요는 없다.
로컬에서 확인하고 싶으면:  python3 scripts/build.py  →  _site/index.html 열기
"""

import html
import json
import re
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
ASSETS = ROOT / "assets"
TEMPLATE = ROOT / "index.template.html"
CONFIG = ROOT / "config.json"
OUT = ROOT / "_site"

# 각 카드 페이지에 '전체 목록 / 공유' 버튼을 붙일지 여부 (원본 파일은 건드리지 않고 배포본에만 추가)
INJECT_NAV = True

NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-(\d+))?\.html$")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_DESC_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

_PILL = (
    "display:inline-flex;align-items:center;gap:6px;padding:9px 15px;border-radius:999px;"
    "font:600 13px/1 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;"
    "text-decoration:none;cursor:pointer;border:1px solid rgba(0,0,0,.12);"
    "box-shadow:0 4px 14px rgba(0,0,0,.18);"
)
_KAKAO_SVG = (
    '<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
    'd="M12 3C6.5 3 2 6.6 2 11c0 2.8 1.8 5.3 4.6 6.7L5.7 21l3.9-2.6c.8.1 1.6.2 2.4.2 5.5 0 10-3.6 10-8S17.5 3 12 3z"/></svg>'
)


def nav_snippet(list_href: str, asset_prefix: str, share_url: str = "", list_label: str = "&#8249; 전체 목록") -> str:
    """카드 화면 아래에 띄우는 버튼 묶음 (목록 / 카톡 공유). 배포본에만 들어가고 원본은 그대로."""
    return (
        "\n<!-- cardnews-nav: 배포 시 자동 추가됨 -->\n"
        '<div style="position:fixed;left:50%;bottom:calc(16px + env(safe-area-inset-bottom));'
        'transform:translateX(-50%);z-index:2147483647;display:flex;gap:8px;white-space:nowrap">'
        f'<a href="{list_href}" aria-label="지난 카드뉴스 목록" style="{_PILL}background:rgba(255,255,255,.95);color:#17181c">{list_label}</a>'
        f'<button type="button" data-share="{share_url}" aria-label="카카오톡으로 공유" style="{_PILL}background:#FEE500;color:#191919">'
        f"{_KAKAO_SVG}공유</button></div>\n"
        f'<script src="{asset_prefix}config.js"></script><script src="{asset_prefix}share.js"></script>\n'
    )


def decorate(text: str, snippet: str) -> str:
    """카톡 미리보기용 og:title 보충 + 하단 버튼 삽입"""
    if not OG_TITLE_RE.search(text):
        t = TITLE_RE.search(text)
        if t:
            og = f'<meta property="og:title" content="{html.escape(html.unescape(t.group(1).strip()))}">'
            idx = text.lower().find("</head>")
            if idx != -1:
                text = text[:idx] + og + "\n" + text[idx:]
    if "cardnews-nav" not in text:
        idx = text.lower().rfind("</body>")
        text = text[:idx] + snippet + text[idx:] if idx != -1 else text + snippet
    return text


OG_TITLE_RE = re.compile(r'property=["\']og:title["\']', re.IGNORECASE)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def collect_cards():
    cards, skipped = [], []
    if not CARDS.exists():
        return cards, skipped
    for path in sorted(CARDS.glob("*.html")):
        m = NAME_RE.match(path.name)
        if not m:
            skipped.append((path.name, "파일 이름이 YYYY-MM-DD.html 형식이 아님"))
            continue
        y, mo, d, seq = m.groups()
        try:
            day = date(int(y), int(mo), int(d))
        except ValueError:
            skipped.append((path.name, "존재하지 않는 날짜"))
            continue
        text = read_text(path)
        t = TITLE_RE.search(text)
        title = html.unescape(re.sub(r"\s+", " ", t.group(1))).strip() if t else ""
        if not title:
            title = f"{day.month}월 {day.day}일 카드뉴스"
        dm = OG_DESC_RE.search(text)
        desc = html.unescape(dm.group(1)).strip() if dm else ""
        cards.append(
            {
                "file": path.name,
                "url": f"cards/{path.name}",
                "date": day.isoformat(),
                "seq": int(seq) if seq else 1,
                "title": title,
                "description": desc,
                "_day": day,
            }
        )
    cards.sort(key=lambda c: (c["_day"], c["seq"]), reverse=True)
    return cards, skipped


def day_label(day: date) -> str:
    return f"{day.month}월 {day.day}일 ({WEEKDAYS[day.weekday()]})"


def add_base_target(text: str) -> str:
    """홈 화면 안에서 기사 링크를 누르면 새 창으로 열리도록"""
    if re.search(r"<base\b", text, re.IGNORECASE):
        return text
    m = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    tag = '<base target="_blank">'
    return text[: m.end()] + tag + text[m.end():] if m else tag + text


def render_feed(cards) -> str:
    if not cards:
        return '<p class="empty">아직 올라온 카드뉴스가 없어요.</p>'
    parts = []
    for i, c in enumerate(cards):
        if i > 0:
            parts.append(f'<div class="divider">{day_label(c["_day"])}</div>')
        parts.append(
            f'<iframe class="card-frame" src="embed/{html.escape(c["file"])}" '
            f'data-url="{html.escape(c["url"])}" title="{html.escape(c["title"])}" '
            f'loading="{"eager" if i == 0 else "lazy"}"></iframe>'
        )
    first = cards[0]
    parts.append(
        f'<button type="button" class="fab" data-share="{html.escape(first["url"])}" '
        f'data-title="{html.escape(first["title"])}" aria-label="카카오톡으로 공유">{_KAKAO_SVG}공유</button>'
    )
    return "\n".join(parts)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    cards, skipped = collect_cards()

    # 카드 파일 복사 (+ 목록 버튼 삽입)
    (OUT / "cards").mkdir()
    (OUT / "embed").mkdir()
    if CARDS.exists():
        for path in CARDS.iterdir():
            if path.name.startswith("."):
                continue
            dest = OUT / "cards" / path.name
            if path.is_dir():
                shutil.copytree(path, dest)
            elif INJECT_NAV and path.suffix.lower() == ".html" and NAME_RE.match(path.name):
                raw = read_text(path)
                # 날짜 주소로 따로 열었을 때: 아래에 '홈 / 공유' 버튼
                dest.write_text(decorate(raw, nav_snippet("../", "../assets/", "", "&#8249; 홈")), encoding="utf-8")
                # 홈 화면에 끼워 넣는 용도: 버튼 없이 원본 그대로, 기사 링크는 새 창으로
                (OUT / "embed" / path.name).write_text(add_base_target(raw), encoding="utf-8")
            else:
                shutil.copy2(path, dest)

    if ASSETS.exists():
        shutil.copytree(ASSETS, OUT / "assets", ignore=shutil.ignore_patterns(".*"))
    else:
        (OUT / "assets").mkdir()

    # 설정(카카오 키 등)을 페이지에서 읽을 수 있게 config.js로 내보내기
    config = {}
    if CONFIG.exists():
        try:
            config = json.loads(read_text(CONFIG))
        except json.JSONDecodeError as e:
            print(f"::warning title=config.json 형식 오류::{e}")
    js_config = {"kakaoKey": str(config.get("kakao_js_key", "")).strip()}
    (OUT / "assets" / "config.js").write_text(
        "window.CARDNEWS_CONFIG = " + json.dumps(js_config, ensure_ascii=False) + ";\n",
        encoding="utf-8",
    )

    # 홈 화면 (index.html) = 오늘의 카드뉴스 + 아래로 지난 카드뉴스
    latest = cards[0] if cards else None
    page = read_text(TEMPLATE)
    page = (
        page.replace("{{FEED}}", render_feed(cards))
        .replace("{{TITLE}}", html.escape(latest["title"]) if latest else "카드뉴스")
        .replace("{{DESC}}", html.escape(day_label(latest["_day"])) if latest else "")
    )
    (OUT / "index.html").write_text(page, encoding="utf-8")

    # 목록 데이터 (나중에 다른 기능에서 쓸 수 있도록)
    manifest = [{k: v for k, v in c.items() if not k.startswith("_")} for c in cards]
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"카드뉴스 {len(cards)}건으로 사이트를 만들었습니다.")
    for name, reason in skipped:
        # GitHub Actions 화면에 노란 경고로 표시됨
        print(f"::warning title=목록에서 제외된 파일::cards/{name} — {reason}")


if __name__ == "__main__":
    build()
