"""
카톡·메신저 링크 미리보기 이미지(썸네일) 만들기

build.py 가 _site/ 를 만든 뒤에 실행한다 (GitHub Actions에서 자동).
- 최근 며칠치 카드마다 1장씩: 신문형 1면과 한 장 요약 1장을 나란히 놓은 1200x630 이미지
  → _site/og/YYYY-MM-DD.png
- 이미지를 만든 페이지(홈, cards/YYYY-MM-DD.html)에만 og:image 태그를 넣는다.
  이미지 만들기에 실패해도 사이트 배포는 그대로 진행된다 (미리보기 사진만 빠짐).

필요한 것: pip install playwright && python -m playwright install chromium
로컬 확인:  python3 card_news/scripts/build.py && python3 card_news/scripts/thumbnail.py
"""

import base64
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "_site"
MARK = "<!--OG_IMAGE-->"
KEEP_DAYS = 14          # 최근 며칠치만 만든다 (오래된 날짜는 공유될 일이 드물어 생략)
W, H = 1200, 630        # 카카오톡·페이스북 등 링크 미리보기 권장 비율 (약 1.9:1)
ORDER = ["newspaper", "onepage"]


def sheet_png(page, card_file: Path) -> bytes:
    """카드 파일의 첫 장(.sheet)만 잘라서 PNG로"""
    page.goto(card_file.as_uri(), wait_until="load")
    try:
        page.wait_for_function("document.fonts && document.fonts.status === 'loaded'", timeout=8000)
    except Exception:
        pass
    page.wait_for_timeout(300)
    return page.locator(".sheet").first.screenshot(type="png")


def compose_html(images) -> str:
    imgs = "".join(
        f'<img src="data:image/png;base64,{base64.b64encode(b).decode()}">' for b in images
    )
    return f"""<!doctype html><meta charset="utf-8"><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden}}
body{{display:flex;align-items:center;justify-content:center;gap:44px;
  background:#CFE6EE;
  background-image:radial-gradient(circle at 30% 40%,#BFDCE7 0 2px,transparent 3px),
                   radial-gradient(circle at 70% 60%,#BFDCE7 0 1.5px,transparent 2.5px);
  background-size:28px 28px}}
img{{height:{H - 64}px;width:auto;border-radius:6px;
  box-shadow:0 10px 28px rgba(15,40,55,.22),0 2px 6px rgba(15,40,55,.12)}}
</style><body>{imgs}</body>"""


def set_og(page_file: Path, image_url: str):
    if not page_file.exists():
        return
    text = page_file.read_text(encoding="utf-8")
    if MARK not in text:
        return
    tags = (
        f'<meta property="og:image" content="{image_url}">\n'
        f'<meta property="og:image:width" content="{W}">\n'
        f'<meta property="og:image:height" content="{H}">\n'
        f'<meta name="twitter:card" content="summary_large_image">\n'
        f'<meta name="twitter:image" content="{image_url}">'
    )
    page_file.write_text(text.replace(MARK, tags), encoding="utf-8")


def main():
    site_url = os.environ.get("SITE_URL", "").strip().rstrip("/")
    manifest_path = OUT / "manifest.json"
    if not manifest_path.exists():
        print("::warning title=썸네일 생략::_site/manifest.json 이 없음 (build.py 먼저 실행)")
        return
    days = json.loads(manifest_path.read_text(encoding="utf-8"))[:KEEP_DAYS]
    if not days:
        return
    if not site_url:
        # og:image 는 전체 주소여야 한다. 로컬 미리보기에서는 이미지만 만들고 태그는 상대 경로로 넣는다.
        print("::notice title=SITE_URL 없음::로컬 미리보기로 보고 상대 경로를 씁니다")

    from playwright.sync_api import sync_playwright

    (OUT / "og").mkdir(exist_ok=True)
    made = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        card_page = browser.new_page(viewport={"width": 520, "height": 900}, device_scale_factor=2, color_scheme="light")
        canvas = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=1, color_scheme="light")
        for d in days:
            try:
                files = d.get("variants", {})
                shots = [sheet_png(card_page, OUT / files[k]) for k in ORDER if k in files]
                if not shots:
                    continue
                canvas.set_content(compose_html(shots), wait_until="load")
                out = OUT / "og" / f"{d['date']}.png"
                canvas.screenshot(path=str(out), type="png")
                rel = f"og/{d['date']}.png"
                url = f"{site_url}/{rel}" if site_url else rel
                set_og(OUT / "cards" / f"{d['date']}.html", url if site_url else f"../{rel}")
                if d is days[0]:
                    set_og(OUT / "index.html", url)
                made += 1
            except Exception as e:  # 한 날짜가 실패해도 나머지는 계속
                print(f"::warning title=썸네일 실패::{d.get('date')} — {e}")
        browser.close()

    # 이미지를 못 만든 페이지에는 표시만 지운다
    for f in [OUT / "index.html", *(OUT / "cards").glob("????-??-??.html")]:
        t = f.read_text(encoding="utf-8")
        if MARK in t:
            f.write_text(t.replace(MARK + "\n", "").replace(MARK, ""), encoding="utf-8")
    print(f"미리보기 이미지 {made}개를 만들었습니다.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"::warning title=썸네일 단계 실패::{e}")
        sys.exit(0)
