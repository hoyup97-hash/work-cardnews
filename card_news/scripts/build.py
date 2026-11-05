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
NAV_SNIPPET = (
    "\n<!-- cardnews-nav: 배포 시 자동 추가됨 -->\n"
    '<div style="position:fixed;left:50%;bottom:calc(16px + env(safe-area-inset-bottom));'
    'transform:translateX(-50%);z-index:2147483647;display:flex;gap:8px">'
    f'<a href="../" aria-label="전체 카드뉴스 목록" style="{_PILL}background:rgba(255,255,255,.95);color:#17181c">&#8249; 전체 목록</a>'
    f'<button type="button" data-share="" aria-label="카카오톡으로 공유" style="{_PILL}background:#FEE500;color:#191919">'
    '<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
    'd="M12 3C6.5 3 2 6.6 2 11c0 2.8 1.8 5.3 4.6 6.7L5.7 21l3.9-2.6c.8.1 1.6.2 2.4.2 5.5 0 10-3.6 10-8S17.5 3 12 3z"/></svg>'
    "공유</button></div>\n"
    '<script src="../assets/config.js"></script><script src="../assets/share.js"></script>\n'
)
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


KAKAO_ICON = (
    '<svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
    'd="M12 3C6.5 3 2 6.6 2 11c0 2.8 1.8 5.3 4.6 6.7L5.7 21l3.9-2.6c.8.1 1.6.2 2.4.2 5.5 0 10-3.6 10-8S17.5 3 12 3z"/></svg>'
)


def share_button(card, cls, label) -> str:
    return (
        f'<button type="button" class="{cls}" data-share="{html.escape(card["url"])}" '
        f'data-title="{html.escape(card["title"])}" aria-label="{html.escape(card["title"])} 카카오톡으로 공유">'
        f"{KAKAO_ICON}{label}</button>"
    )


def render_latest(card) -> str:
    if card is None:
        return (
            '<div class="empty">아직 올라온 카드뉴스가 없어요.<br>'
            "<span>cards 폴더에 YYYY-MM-DD.html 파일을 올리면 여기에 나타납니다.</span></div>"
        )
    desc = (
        f'<p class="hero-desc">{html.escape(card["description"])}</p>'
        if card["description"]
        else ""
    )
    url = html.escape(card["url"])
    return (
        f'<div class="hero">'
        f'<a class="hero-link" href="{url}">'
        f'<span class="chip">{day_label(card["_day"])}</span>'
        f'<h2 class="hero-title">{html.escape(card["title"])}</h2>'
        f"{desc}</a>"
        f'<div class="hero-actions">'
        f'<a class="btn btn-primary" href="{url}">카드뉴스 보기 <span aria-hidden="true">→</span></a>'
        f'{share_button(card, "btn btn-kakao", "카카오톡 공유")}'
        f"</div></div>"
    )


def render_archive(cards) -> str:
    if not cards:
        return '<p class="muted">지난 카드뉴스가 아직 없어요.</p>'
    parts, current = [], None
    for c in cards:
        month = (c["_day"].year, c["_day"].month)
        if month != current:
            if current is not None:
                parts.append("</ul></section>")
            parts.append(
                f'<section class="month"><h3>{month[0]}년 {month[1]}월</h3><ul>'
            )
            current = month
        parts.append(
            f'<li><a href="{html.escape(c["url"])}">'
            f'<span class="d">{c["_day"].month}/{c["_day"].day}'
            f'<small>{WEEKDAYS[c["_day"].weekday()]}</small></span>'
            f'<span class="t">{html.escape(c["title"])}</span>'
            f'</a>{share_button(c, "share-mini", "")}</li>'
        )
    parts.append("</ul></section>")
    return "".join(parts)


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()

    cards, skipped = collect_cards()

    # 카드 파일 복사 (+ 목록 버튼 삽입)
    (OUT / "cards").mkdir()
    if CARDS.exists():
        for path in CARDS.iterdir():
            if path.name.startswith("."):
                continue
            dest = OUT / "cards" / path.name
            if path.is_dir():
                shutil.copytree(path, dest)
            elif INJECT_NAV and path.suffix.lower() == ".html" and NAME_RE.match(path.name):
                text = read_text(path)
                # 카톡 공유 미리보기용 제목이 없으면 <title>로 채워 넣기
                if not OG_TITLE_RE.search(text):
                    t = TITLE_RE.search(text)
                    if t:
                        og = f'<meta property="og:title" content="{html.escape(html.unescape(t.group(1).strip()))}">'
                        idx = text.lower().find("</head>")
                        if idx != -1:
                            text = text[:idx] + og + "\n" + text[idx:]
                if "cardnews-nav" not in text:
                    idx = text.lower().rfind("</body>")
                    text = (
                        text[:idx] + NAV_SNIPPET + text[idx:]
                        if idx != -1
                        else text + NAV_SNIPPET
                    )
                dest.write_text(text, encoding="utf-8")
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

    # 메인 페이지
    latest = cards[0] if cards else None
    archive = cards[1:]
    now = datetime.now(KST)
    page = read_text(TEMPLATE)
    page = (
        page.replace("{{LATEST}}", render_latest(latest))
        .replace("{{ARCHIVE}}", render_archive(archive))
        .replace("{{COUNT}}", str(len(cards)))
        .replace("{{UPDATED}}", now.strftime("%Y.%m.%d %H:%M"))
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
