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

import hashlib
import html
import json
import re
import os
import shutil
import subprocess
import tempfile
from html.parser import HTMLParser
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
ASSETS = ROOT / "assets"
TEMPLATE = ROOT / "index.template.html"
THUMB_TEMPLATE = ROOT / "thumb.template.html"
FONTS = ROOT / "scripts" / "fonts"
THUMB_DAYS = 30  # 썸네일을 새로 찍는 최근 날짜 수 (그 전 날짜는 기본 썸네일)
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


class _HeadClean(HTMLParser):
    """헤드라인 HTML에서 빨간 펜 표시(circ, ul)만 남기고 나머지 태그는 지운다"""
    KEEP = ("circ", "ul")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.stack, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag != "span":
            return
        cls = (dict(attrs).get("class") or "").split()
        if self.skip or "n" in cls:
            self.stack.append("skip"); self.skip += 1
        elif any(c in cls for c in self.KEEP):
            keep = next(c for c in cls if c in self.KEEP)
            self.stack.append("keep"); self.out.append(f'<span class="{keep}">')
        else:
            self.stack.append("drop")

    def handle_endtag(self, tag):
        if tag != "span" or not self.stack:
            return
        kind = self.stack.pop()
        if kind == "skip":
            self.skip -= 1
        elif kind == "keep":
            self.out.append("</span>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(re.sub(r"\s+", " ", data)))


def all_headlines(text: str):
    """그날 헤드라인 전부 [(펜 표시가 남은 HTML, 글자만)] — 신문형 1면 → 없으면 한 장 요약 기사 제목"""
    items = []
    m = re.search(r'<ol[^>]*class="heads"[^>]*>(.*?)</ol>', text, re.IGNORECASE | re.DOTALL)
    if m:
        items = re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.IGNORECASE | re.DOTALL)
    if not items:
        items = re.findall(r'<li class="story">.*?<h2[^>]*>(.*?)</h2>', text, re.IGNORECASE | re.DOTALL)
    out = []
    for frag in items:
        p = _HeadClean()
        p.feed(frag)
        p.close()
        rich = "".join(p.out).strip()
        plain = _strip(frag)
        if plain:
            out.append((rich, plain))
    return out


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
        heads = []
        for k in VARIANT_KEYS:
            if k in e["files"]:
                heads = all_headlines(read_text(CARDS / e["files"][k]))
                if heads:
                    break
        e["heads"] = heads
        out.append(e)
    return out, skipped


OG_IMAGE = ASSETS / "og-image.png"  # 링크 미리보기 썸네일 (1200x630)


def find_chrome():
    """썸네일을 찍을 Chrome. GitHub Actions(ubuntu)에는 google-chrome 이 기본으로 있다. 없으면 기본 썸네일을 쓴다"""
    cands = [os.environ.get("CHROME_PATH", ""), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
             r"C:\Program Files\Google\Chrome\Application\chrome.exe",
             "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    for c in cands:
        if c and (shutil.which(c) or Path(c).exists()):
            return shutil.which(c) or c
    return None


def make_thumbs(days):
    """날짜마다 1번 헤드라인을 넣은 링크 미리보기 썸네일(_site/cards/YYYY-MM-DD.og.png)을 찍는다.
    실패해도 배포는 멈추지 않고, 그날은 기본 썸네일(assets/og-image.png)을 쓴다. 돌려주는 값: {날짜: 사이트 안 경로}"""
    targets = [d for d in days[:THUMB_DAYS] if d.get("heads")]
    if not targets or not THUMB_TEMPLATE.exists():
        return {}
    chrome = find_chrome()
    if not chrome:
        print("::notice title=썸네일 기본 이미지 사용::Chrome을 찾지 못해 날짜별 썸네일을 만들지 않았습니다")
        return {}
    tpl = read_text(THUMB_TEMPLATE)
    tmp = Path(tempfile.mkdtemp(prefix="cardnews-thumb-"))

    def shot(d):
        rich, _ = d["heads"][0]
        page = (tpl.replace("{{FONTS}}", FONTS.resolve().as_uri())
                .replace("{{DATE}}", html.escape(d["label"].replace(" (", "(")))
                .replace("{{HEAD}}", rich)
                .replace("{{COUNT}}", str(len(d["heads"]))))
        src = tmp / f"{d['date']}.html"
        src.write_text(page, encoding="utf-8")
        out = OUT / "cards" / f"{d['date']}.og.png"
        cmd = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--mute-audio",
               "--force-device-scale-factor=1", "--window-size=1200,630", "--virtual-time-budget=4000",
               "--allow-file-access-from-files", f"--screenshot={out}", src.resolve().as_uri()]
        try:
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            pass
        return d["date"], out.exists() and out.stat().st_size > 5000

    done = {}  # 한 장에 1초 남짓. Chrome 여러 개를 동시에 띄우면 멈출 수 있어 차례로 찍는다
    for date_s, ok in map(shot, targets):
        if ok:
            done[date_s] = f"cards/{date_s}.og.png"
        else:
            print(f"::warning title=썸네일 실패::{date_s} — 기본 썸네일을 씁니다")
    shutil.rmtree(tmp, ignore_errors=True)
    return done


def og_tags(site_url: str, page_path: str, image: str = "") -> str:
    """카톡·슬랙 등 링크 미리보기용 태그. 썸네일은 전체 주소여야 해서 config.json 의 site_url 이 필요하다.
    썸네일 주소 끝에 파일 내용 해시(?v=)를 붙여, 이미지를 바꾸면 미리보기도 새로 받아가게 한다."""
    if not site_url:
        return ""
    site_url = site_url.rstrip("/") + "/"
    tags = [f'<meta property="og:url" content="{html.escape(site_url + page_path)}">',
            '<meta property="og:site_name" content="영업혁신실 신문">']
    image = image or f"assets/{OG_IMAGE.name}"
    built = OUT / image
    if built.exists():
        ver = hashlib.md5(built.read_bytes()).hexdigest()[:8]
        img = html.escape(f"{site_url}{image}?v={ver}")
        tags += [f'<meta property="og:image" content="{img}">',
                 '<meta property="og:image:width" content="1200">',
                 '<meta property="og:image:height" content="630">',
                 '<meta name="twitter:card" content="summary_large_image">']
    return "\n".join(tags)


def og_description(day) -> str:
    """미리보기 설명: 썸네일에 1번 헤드라인이 있으니 2·3번을 보여 준다"""
    rest = [plain for _, plain in day.get("heads", [])[1:]]
    if rest:
        return " / ".join(f"{i}. {t}" for i, t in enumerate(rest, start=2))
    return day["headline"]


def feedback_block(url: str) -> str:
    """카드 바로 아래 '의견 보내기' 줄. config.json 의 feedback_url 이 비어 있으면 아무것도 안 보인다"""
    if not url:
        return ""
    return (
        '<div class="fb"><span>이번 카드뉴스 어땠나요?</span>'
        f'<a href="{html.escape(url)}" target="_blank" rel="noopener">의견 보내기</a></div>'
    )


def render_page(template: str, days, idx: int, base: str, site_url: str = "", thumbs=None, feedback_url: str = "") -> str:
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
    page_title = f"보험 영업 뉴스 · {cur['label']}"
    return (
        template.replace("{{TITLE}}", html.escape(page_title))
        .replace("{{DESC}}", html.escape(og_description(cur)))
        .replace("{{OG}}", og_tags(site_url, "" if base == "" else cur["url"], (thumbs or {}).get(cur["date"], "")))
        .replace("{{FEEDBACK}}", feedback_block(feedback_url))
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

    site_url = str(config.get("site_url", "")).strip()
    feedback_url = str(config.get("feedback_url", "")).strip()
    thumbs = make_thumbs(days) if site_url else {}
    if not site_url:
        print("::warning title=site_url 없음::config.json 에 site_url 이 없어 링크 미리보기 썸네일이 빠집니다")

    template = read_text(TEMPLATE)
    if days:
        (OUT / "index.html").write_text(render_page(template, days, 0, "", site_url, thumbs, feedback_url), encoding="utf-8")
        for i, d in enumerate(days):
            (OUT / "cards" / f"{d['date']}.html").write_text(render_page(template, days, i, "../", site_url, thumbs, feedback_url), encoding="utf-8")
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
