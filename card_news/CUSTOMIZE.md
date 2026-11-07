# 사이트 구조·디자인 바꾸기 (담당자용)

홈 화면 모양, 지난 카드 목록, 버튼, 카드 디자인처럼 **사이트 자체**를 바꾸고 싶을 때 보는 문서입니다.
매일 카드뉴스를 올리는 일은 SETUP.md 와 AUTOMATION.md 를 보세요.

## 먼저 알아둘 것
- 원본은 GitHub 저장소(work-cardnews) 하나입니다. 여기 main 에 올리면(Push) 1~2분 뒤 사이트에 반영됩니다.
- 여러 사람이 고치므로 **작업 전에 항상 최신 상태를 받습니다**(GitHub Desktop: Fetch origin → Pull origin).
- 예약 발행이 도는 시각(평일 아침)에는 고치지 않는 게 좋습니다. 같은 시각에 올리면 한쪽이 다시 올려야 할 수 있습니다.
- 저장소와 사이트는 공개입니다. 사내 실적·고객 정보, 유앤아이 폰트 파일은 올리지 않습니다.

## 방법 1. Claude 채팅에서 고치기 (설치 필요 없음, 추천)
1. cardnews-site 스킬이 있는 Claude 계정에서 새 채팅을 엽니다.
2. 바꾸고 싶은 것을 말합니다. 예: "카드뉴스 사이트 홈 화면에서 지난 카드 목록을 날짜별 카드 모양으로 바꿔줘"
3. Claude가 저장소를 받아 고친 뒤 **미리보기**(화면 캡처나 HTML 파일)를 보여줍니다. 이때는 아직 사이트에 안 올라갑니다.
4. 마음에 들면 "올려줘"라고 하면 Claude가 올리고 배포까지 확인합니다.

## 방법 2. 내 PC에서 Claude Code로 고치기
1. **처음 한 번:** GitHub Desktop → File → Clone repository → work-cardnews 를 받을 폴더를 정합니다.
2. **매번 시작할 때:** GitHub Desktop 에서 Fetch origin → Pull origin.
3. 그 폴더에서 Claude Code를 열고 바꾸고 싶은 것을 말합니다.
4. **미리보기:** "빌드해서 미리 보여줘"라고 하면 Claude가 `card_news/scripts/build.py` 를 실행해 `card_news/_site/index.html` 을 만듭니다. 브라우저로 열어 확인합니다(`_site` 는 올라가지 않음).
5. **올리기:** GitHub Desktop 왼쪽 아래 Summary 에 무엇을 바꿨는지 적고 **Commit to main** → 위쪽 **Push origin**. (Claude Code 에게 "커밋하고 푸시해줘"라고 해도 됩니다.)
6. **확인:** GitHub 저장소 Actions 탭에서 초록 체크(✓)가 뜨면 사이트를 새로고침합니다. 빨간 X면 실패 → 아래 '되돌리기'.

## 무엇을 고치면 어디가 바뀌나
| 바꾸고 싶은 것 | 파일 |
|---|---|
| 보기 화면(위쪽 날짜·전환 버튼·공유, 아래 '지난 카드뉴스' 걸침) 모양 | `card_news/index.template.html` (홈과 날짜 주소가 같은 틀) |
| 무작위로 보여주는 방식, 전환 동작 | `card_news/index.template.html` 아래쪽 `<script>` (`pick`, `show`) |
| 보기 방식 종류·버튼 이름, 지난 목록 채우는 방식 | `card_news/scripts/build.py` 의 `VARIANTS`, `render_page` |
| 공유 버튼 동작(카톡 공유) | `card_news/assets/share.js`, 카카오 키는 `card_news/config.json` |
| 카톡 미리보기 제목·설명 | `card_news/index.template.html` 의 og 태그 |
| 카드 디자인(신문형 5장 / 한 장 요약 2장) | 아래 '카드 디자인 바꾸기' |
| Claude가 카드를 올릴 때 지키는 규칙 | `card_news/AUTOMATION.md` |
| 자동 배포 방식 | `.github/workflows/deploy.yml` (웬만하면 건드리지 않음) |

## 카드 디자인 바꾸기
- Claude는 새 카드를 만들 때 **`card_news/cards/` 의 가장 최근 `*.newspaper.html` / `*.onepage.html` 을 복사해서** 내용만 바꿉니다. 그래서 새 디자인을 적용하려면 **새 디자인으로 만든 카드를 올리면** 다음 회차부터 그 모양을 따라갑니다. 지난 카드는 바꿀 필요 없습니다.
- 동료의 카드뉴스 스킬(fubon-news-newspaper, fubon-news-onepage) 안에 있는 템플릿만 바꾸면 사이트 카드에는 반영되지 않습니다. 디자인을 바꾸면 스킬을 만든 동료에게도 알려 서로 맞춥니다.
- 세 번째 보기 방식을 추가하려면 `build.py` 의 `VARIANTS` 에 이름을 더하고, 그 이름으로 파일(`YYYY-MM-DD.<이름>.html`)을 올립니다.
- 새 디자인에서도 지킬 것:
  - 파일 하나에 모두 담기(HTML 안에 스타일·스크립트). 글꼴은 Pretendard 링크만.
  - `<title>` 유지 (홈 화면 목록·카톡 미리보기에 쓰임).
  - 신문형 1면 헤드라인 `<ol class="heads"><li>…</li></ol>`, 한 장 요약 기사 제목 `<li class="story">…<h2>` 구조 유지 (지난 카드 목록에 첫 헤드라인이 뜸). 바꾸려면 `build.py` 의 `first_headline` 도 같이 고칩니다.
  - 장 구성(1면 / 기사 3장 / 더 읽어볼 기사)이 바뀌면 `AUTOMATION.md` 2번도 같이 고칩니다.
  - 휴대폰 폭(390px)에서 한 장이 넘치지 않는지 확인.

## 조심할 것
- **파일 이름 규칙**(`YYYY-MM-DD.newspaper.html`, `YYYY-MM-DD.onepage.html`)은 `build.py`, `AUTOMATION.md`, `SETUP.md`, cardnews-site 스킬이 모두 기대고 있습니다. 바꾸려면 넷을 함께 고칩니다.
- `.github/workflows/deploy.yml` 이 잘못되면 배포가 멈춥니다. 고쳐야 하면 Claude에게 이유를 설명하고 맡깁니다.
- 한 번 올린 내용은 지워도 GitHub 기록(History)에 남습니다.

## 잘못 올렸을 때 되돌리기
- **Claude에게:** "방금 사이트 수정 되돌려줘" → 마지막 변경을 되돌리는 커밋(git revert)을 만들어 올립니다.
- **GitHub Desktop 에서:** History 탭 → 되돌릴 커밋 우클릭 → **Revert changes in commit** → Push origin.

## 저장소를 팀 Organization으로 옮길 때
주소(`hoyup97-hash/work-cardnews`, `hoyup97-hash.github.io`)가 바뀌므로 아래를 함께 고칩니다.
1. `card_news/AUTOMATION.md`, `card_news/SETUP.md`, `card_news/README.md`, `card_news/cardnews-site/SKILL.md` 안의 주소
2. 각자 계정의 cardnews-site 스킬(바뀐 SKILL.md 로 다시 추가)
3. 걸어 둔 예약 작업 (새 주소로 다시 만들기)
4. 카카오 개발자 앱의 사이트 도메인
5. 단톡방에 공유했던 사이트 주소 안내
