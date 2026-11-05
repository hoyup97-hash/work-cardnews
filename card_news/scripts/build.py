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
OUT = ROOT / "_site"

# 각 카드 페이지에 '전체 목록' 버튼을 붙일지 여부 (원본 파일은 건드리지 않고 배포본에만 추가)
INJECT_NAV = True

NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:-(\d+))?\.html$")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
OG_DESC_RE = re.compile(
    r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
KST = timezone(timedelta(hours=9))

NAV_SNIPPET = """
<!-- cardnews-nav: 배포 시 자동 추가됨 -->
<a href="../" aria-label="전체 카드뉴스 목록" style="position:fixed;left:50%;bottom:calc(16px + env(safe-area-inset-bottom));transform:translateX(-50%);z-index:2147483647;padding:9px 16px;border-radius:999px;background:rgba(255,255,255,.94);color:#17181c;border:1px solid rgba(0,0,0,.12);font:600 13px/1 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;text-decoration:none;box-shadow:0 4px 14px rgba(0,0,0,.18);-webkit-backdrop-filter:blur(6px);backdrop-filter:blur(6px)">&#8249; 전체 목록</a>
"""


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
    return (
        f'<a class="hero" href="{html.escape(card["url"])}">'
        f'<span class="chip">{day_label(card["_day"])}</span>'
        f'<h2 class="hero-title">{html.escape(card["title"])}</h2>'
        f"{desc}"
        f'<span class="hero-cta">카드뉴스 보기 <span aria-hidden="true">→</span></span>'
        f"</a>"
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
            f'<span class="arrow" aria-hidden="true">›</span></a></li>'
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
