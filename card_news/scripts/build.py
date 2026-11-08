"""
카드뉴스 사이트 빌드 스크립트

cards/ 폴더의 HTML 파일을 모아 _site/ 폴더에 배포용 사이트를 만든다.
- 하루에 하나. 같은 날짜에 보기 방식(버전)이 둘:
    YYYY-MM-DD.newspaper.html  (신문형, fubon-news-newspaper 스킬)
    YYYY-MM-DD.onepage.html    (한 장 요약, fubon-news-onepage 스킬)
  버전 표시가 없는 YYYY-MM-DD.html 은 신문형으로 본다.
- 홈(index.html)과 날짜별 주소(cards/YYYY-MM-DD.html)는 같은 '보기 화면'이다.
  위쪽 오른쪽 버튼으로 두 버전을 오가고, 처음 들어온 사람에게는 둘 중 하나가 무작위로 보인다.
  화면 맨 아래에는 '지난 카드뉴스' 목록이 살짝 걸쳐 보여, 아래로 내릴 수 있다는 걸 알려 준다.
- 규칙에 안 맞는 파일은 목록에서 빠지고, 로그에 경고가 찍힌다 (배포는 멈추지 않음).

GitHub Actions에서 자동 실행되므로 담당자가 직접 돌릴 필요는 없다.
로컬에서 확인하고 싶으면:  python3 card_news/scripts/build.py  →  card_news/_site/index.html 열기
"""

import html
import json
import os
import re
import shutil
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
ASSETS = ROOT / "assets"
TEMPLATE = ROOT / "index.template.html"
CONFIG = ROOT / "config.json"
OUT = ROOT / "_site"

# 보기 방식(버전): 파일 이름 표시, 버튼 이름. 순서 = 버튼 순서
VARIANTS = [("newspaper", "신문형"), ("onepage", "한 장 요약")]
VARIANT_KEYS = [k for k, _ in VARIANTS]

NAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:\.([a-z]+))?\.html$")
WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]
_SHARE_SVG = (
    '<svg width="15" height="15" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" '
    'd="M12 3C6.5 3 2 6.6 2 11c0 2.8 1.8 5.3 4.6 6.7L5.7 21l3.9-2.6c.8.1 1.6.2 2.4.2 5.5 0 10-3.6 10-8S17.5 3 12 3z"/></svg>'
)


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp949"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def day_label(day: date) -> str:
    return f"{day.month}월 {day.day}일 ({WEEKDAYS[day.weekday()]})"


def add_base_target(text: str) -> str:
    """보기 화면 안에서 기사 링크를 누르면 새 창으로 열리도록"""
    if re.search(r"<base\b", text, re.IGNORECASE):
        return text
    m = re.search(r"<head[^>]*>", text, re.IGNORECASE)
    tag = '<base target="_blank">'
    return text[: m.end()] + tag + text[m.end():] if m else tag + text


def _strip(fragment: str) -> str:
    fragment = re.sub(r'<span class="n">.*?</span>', "", fragment, flags=re.DOTALL)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return html.unescape(re.sub(r"\s+", " ", fragment)).strip()


def first_headline(text: str) -> str:
    """지난 카드 목록에 쓸 첫 번째 헤드라인 (신문형 1면 → 없으면 한 장 요약의 첫 기사 제목)"""
    m = re.search(r'<ol[^>]*class="heads"[^>]*>(.*?)</ol>', text, re.IGNORECASE | re.DOTALL)
    if m:
        li = re.search(r"<li[^>]*>(.*?)</li>", m.group(1), re.IGNORECASE | re.DOTALL)
        if li:
            return _strip(li.group(1))
    m = re.search(r'<li class="story">.*?<h2[^>]*>(.*?)</h2>', text, re.IGNORECASE | re.DOTALL)
    return _strip(m.group(1)) if m else ""


def collect_days():
    days, skipped = {}, []
    if not CARDS.exists():
        return [], skipped
    for path in sorted(CARDS.glob("*.html")):
        m = NAME_RE.match(path.name)
        if not m:
            skipped.append((path.name, "파일 이름이 YYYY-MM-DD.newspaper.html / YYYY-MM-DD.onepage.html 형식이 아님 (하루에 하나)"))
            continue
        y, mo, d, variant = m.groups()
        variant = variant or "newspaper"
        if variant not in VARIANT_KEYS:
            skipped.append((path.name, f"알 수 없는 보기 방식 '{variant}' (newspaper / onepage 중 하나)"))
            continue
        try:
            day = date(int(y), int(mo), int(d))
        except ValueError:
            skipped.append((path.name, "존재하지 않는 날짜"))
            continue
        entry = days.setdefault(day, {"_day": day, "date": day.isoformat(), "files": {}})
        if variant in entry["files"]:
            skipped.append((path.name, f"같은 날짜·같은 보기 방식 파일이 이미 있음 ({entry['files'][variant]})"))
            continue
        entry["files"][variant] = path.name
    out = []
    for day in sorted(days, reverse=True):
        e = days[day]
        e["label"] = day_label(day)
        e["url"] = f"cards/{e['date']}.html"
        headline = ""
        for k in VARIANT_KEYS:
            if k in e["files"]:
                headline = first_headline(read_text(CARDS / e["files"][k]))
                if headline:
                    break
        e["headline"] = headline
        out.append(e)
    return out, skipped


def render_page(template: str, days, idx: int, base: str) -> str:
    """보기 화면 하나 (홈: base='' / 날짜 주소: base='../')"""
    cur = days[idx]
    variants = [
        {"key": k, "label": label, "src": f"{base}embed/{cur['files'][k]}"}
        for k, label in VARIANTS if k in cur["files"]
    ]
    seg = ""
    if len(variants) > 1:
        seg = (
            '<div class="seg" role="group" aria-label="보기 방식">'
            + "".join(f'<button type="button" data-v="{v["key"]}" aria-pressed="false">{v["label"]}</button>' for v in variants)
            + "</div>"
        )
    is_home = base == ""
    left = (
        f'<span class="day">{cur["label"]}</span>' if is_home
        else f'<a class="home" href="{base}" aria-label="최신 카드뉴스로">&#8249;</a><span class="day">{cur["label"]}</span>'
    )
    others = [d for i, d in enumerate(days) if i != idx]
    archive = peek = ""
    if others:
        rows = []
        for d in others:
            tag = '<span class="new">최신</span>' if d is days[0] else ""
            rows.append(
                f'<li><a href="{base}{html.escape(d["url"])}"><span class="d">{d["label"]}</span>'
                f'<span class="t">{tag}{html.escape(d["headline"] or "카드뉴스")}</span></a></li>'
            )
        title = "지난 카드뉴스" if is_home else "다른 날 카드뉴스"
        peek = (
            f'<a class="peek" href="#archive"><span class="grab" aria-hidden="true"></span>'
            f'<span class="ph">{title}</span><span class="pc">{len(others)}건 · 아래로 내려 보기</span>'
            f'<span class="chev" aria-hidden="true">&#8964;</span></a>'
        )
        archive = f'<section class="archive" id="archive" aria-label="{title}"><ul>{"".join(rows)}</ul></section>'
    data = {"variants": variants}
    page_title = f"영업혁신실 카드뉴스 · {cur['label']}"
    desc = cur["headline"] or "보험 영업·상품·제도 오늘의 뉴스"
    # 링크 미리보기용 전체 주소 (GitHub Actions가 SITE_URL 을 넘겨줌. 없으면 생략)
    site_url = os.environ.get("SITE_URL", "").strip().rstrip("/")
    og_url = ""
    if site_url:
        og_url = f'<meta property="og:url" content="{site_url}/{"" if is_home else cur["url"]}">\n'

    return (
        template.replace("{{TITLE}}", html.escape(page_title))
        .replace("{{DESC}}", html.escape(desc))
        .replace("{{OG_URL}}", og_url)
        .replace("{{BASE}}", base)
        .replace("{{LEFT}}", left)
        .replace("{{SEG}}", seg)
        .replace("{{SHARE}}", f'<button type="button" class="share" data-share="{base}{cur["url"]}" data-title="{html.escape(page_title)}" aria-label="카카오톡으로 공유">{_SHARE_SVG}<span>공유</span></button>')
        .replace("{{PEEK}}", peek)
        .replace("{{ARCHIVE}}", archive)
        .replace("{{DATA}}", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    )


def build():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / "cards").mkdir()
    (OUT / "embed").mkdir()

    days, skipped = collect_days()

    # 카드 원본: 보기 화면 안에 끼워 넣는 용도(embed) + 원본 그대로(cards)
    for d in days:
        for k, name in d["files"].items():
            raw = read_text(CARDS / name)
            (OUT / "embed" / name).write_text(add_base_target(raw), encoding="utf-8")
            (OUT / "cards" / name).write_text(raw, encoding="utf-8")

    if ASSETS.exists():
        shutil.copytree(ASSETS, OUT / "assets", dirs_exist_ok=True, ignore=shutil.ignore_patterns(".*"))
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
        "window.CARDNEWS_CONFIG = " + json.dumps(js_config, ensure_ascii=False) + ";\n", encoding="utf-8"
    )

    template = read_text(TEMPLATE)
    if days:
        (OUT / "index.html").write_text(render_page(template, days, 0, ""), encoding="utf-8")
        for i, d in enumerate(days):
            (OUT / "cards" / f"{d['date']}.html").write_text(render_page(template, days, i, "../"), encoding="utf-8")
    else:
        (OUT / "index.html").write_text(
            '<!doctype html><meta charset="utf-8"><p style="padding:40vh 16px;text-align:center">아직 올라온 카드뉴스가 없어요.</p>',
            encoding="utf-8",
        )

    # 목록 데이터 (배포 확인·다른 기능용). 맨 위가 가장 최근 날짜
    manifest = [
        {"date": d["date"], "label": d["label"], "url": d["url"], "headline": d["headline"],
         "variants": {k: f"embed/{v}" for k, v in d["files"].items()}}
        for d in days
    ]
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"카드뉴스 {len(days)}일치로 사이트를 만들었습니다.")
    for d in days:
        missing = [k for k in VARIANT_KEYS if k not in d["files"]]
        if missing:
            print(f"::notice title=보기 방식 하나만 있음::{d['date']} — {', '.join(missing)} 없음 (전환 버튼 없이 표시)")
    for name, reason in skipped:
        print(f"::warning title=목록에서 제외된 파일::cards/{name} — {reason}")


if __name__ == "__main__":
    build()
