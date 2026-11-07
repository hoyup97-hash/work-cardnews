/*
 * 오늘의 운세
 * - 화면 구석의 '오늘의 운세' 버튼을 누르면 운세 카드가 열린다.
 * - 같은 사람(같은 기기)은 하루 동안 같은 운세, 날이 바뀌면 새 운세. 사람마다 다르게 나온다.
 * - 문구를 바꾸려면 아래 목록만 고치면 된다.
 */
(function () {
  var TOTAL = [
    "막혔던 일이 술술 풀리는 날. 미뤄 둔 연락부터 해 보세요.",
    "작은 칭찬 한마디가 큰 계약으로 돌아오는 날입니다.",
    "숫자보다 사람이 먼저 보이는 날. 고객 이야기를 끝까지 들어 주세요.",
    "오전에 정리한 자료가 오후에 빛을 봅니다.",
    "생각지 못한 곳에서 좋은 소식이 들어옵니다.",
    "오늘은 질문을 많이 할수록 답이 빨리 옵니다.",
    "서두르지 않아도 됩니다. 꼼꼼함이 오늘의 무기예요.",
    "동료와 커피 한 잔이 좋은 아이디어로 이어지는 날.",
    "오래 기다린 답장이 오는 날. 메일함을 한 번 더 확인하세요.",
    "새로운 시도에 운이 따릅니다. 평소와 다른 길로 가 보세요.",
    "말 한마디에 무게가 실리는 날. 회의에서 먼저 의견을 내 보세요.",
    "작게 시작한 일이 크게 자랄 씨앗이 됩니다.",
    "실수해도 금방 만회되는 날. 부담 없이 도전하세요.",
    "주변 사람 덕을 보는 날. 고맙다는 말을 아끼지 마세요.",
    "집중력이 최고인 날. 어려운 일을 오전에 끝내세요.",
    "웃는 얼굴이 최고의 영업 무기가 되는 날입니다.",
    "정리 정돈에 운이 숨어 있어요. 책상부터 치워 보세요.",
    "오늘 만나는 사람이 오래 갈 인연이 됩니다.",
    "계획대로 착착 진행되는 날. 할 일 목록을 끝까지 지워 보세요.",
    "점심 이후 기운이 올라갑니다. 중요한 통화는 오후에.",
  ];
  var TIPS = [
    "통화는 짧게, 메모는 길게.",
    "숫자 하나만 기억해도 대화가 달라집니다.",
    "고객의 첫 질문에 답이 있습니다.",
    "오늘 할 일 세 가지만 정해 보세요.",
    "보낸 자료는 한 번 더 열어 보고 보내세요.",
    "먼저 묻고, 나중에 설명하세요.",
    "점심 산책 10분이 오후를 바꿉니다.",
    "어제 받은 연락에 오늘 답하세요.",
    "칭찬은 구체적으로, 부탁은 짧게.",
    "중요한 건 오전에, 반복 업무는 오후에.",
  ];
  var CHANNELS = ["GA", "BA(방카)", "FP(전속)", "TM"];
  var TIMES = ["오전 9시", "오전 10시", "오전 11시", "점심 직후", "오후 2시", "오후 3시", "오후 4시", "퇴근 30분 전"];
  var COLORS = [["파랑", "#0094C2"], ["청록", "#00A9A1"], ["빨강", "#D7332B"], ["노랑", "#F2B705"], ["초록", "#2E9E5B"], ["보라", "#7B5EA7"], ["주황", "#F07B24"], ["남색", "#2C3E73"]];
  var WEEK = ["일", "월", "화", "수", "목", "금", "토"];

  function store(k, v) { try { if (v === undefined) return localStorage.getItem(k); localStorage.setItem(k, v); } catch (e) { return null; } }

  // 기기마다 한 번 만든 번호 (저장이 안 되는 환경이면 이번 방문 동안만)
  var id = store("cardnews-fortune-id");
  if (!id) { id = String(Math.floor(Math.random() * 1e9)); store("cardnews-fortune-id", id); }

  function today() {
    var d = new Date(); // 보는 사람 기기 시각 기준
    return { key: d.getFullYear() + "-" + (d.getMonth() + 1) + "-" + d.getDate(), label: (d.getMonth() + 1) + "월 " + d.getDate() + "일 (" + WEEK[d.getDay()] + ")" };
  }
  // 문자열 → 같은 입력이면 늘 같은 난수열
  function rng(seed) {
    var h = 2166136261;
    for (var i = 0; i < seed.length; i++) { h ^= seed.charCodeAt(i); h = Math.imul(h, 16777619); }
    return function () {
      h += 0x6D2B79F5; var t = h;
      t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function pick(r, list) { return list[Math.floor(r() * list.length)]; }

  var btn = document.getElementById("fortune-btn");
  var dlg = document.getElementById("fortune");
  if (!btn || !dlg) return;
  var box = dlg.querySelector(".ft-body");

  function render() {
    var t = today();
    var r = rng(id + "|" + t.key);
    var stars = 3 + Math.floor(r() * 3); // 3~5개 (나쁜 운세는 없음)
    var color = pick(r, COLORS);
    box.innerHTML =
      '<p class="ft-date">' + t.label + "</p>" +
      '<p class="ft-stars" aria-label="오늘의 기운 ' + stars + '점">' + "★★★★★".slice(0, stars) + '<span>' + "★★★★★".slice(stars) + "</span></p>" +
      '<p class="ft-main">' + pick(r, TOTAL) + "</p>" +
      '<dl class="ft-grid">' +
      "<div><dt>행운의 채널</dt><dd>" + pick(r, CHANNELS) + "</dd></div>" +
      "<div><dt>행운의 시간</dt><dd>" + pick(r, TIMES) + "</dd></div>" +
      "<div><dt>행운의 숫자</dt><dd>" + (1 + Math.floor(r() * 99)) + "</dd></div>" +
      '<div><dt>행운의 색</dt><dd><i style="background:' + color[1] + '"></i>' + color[0] + "</dd></div>" +
      "</dl>" +
      '<p class="ft-tip"><b>오늘의 한 줄</b> ' + pick(r, TIPS) + "</p>" +
      '<p class="ft-note">재미로 보는 운세예요. 하루 동안 같은 운세가 나옵니다.</p>';
    store("cardnews-fortune-seen", t.key);
    btn.classList.remove("ft-new");
  }

  function open() { render(); dlg.hidden = false; document.body.style.overflow = "hidden"; dlg.querySelector(".ft-close").focus(); }
  function close() { dlg.hidden = true; document.body.style.overflow = ""; btn.focus(); }

  if (store("cardnews-fortune-seen") !== today().key) btn.classList.add("ft-new"); // 오늘 아직 안 봤으면 반짝
  btn.addEventListener("click", open);
  dlg.addEventListener("click", function (e) { if (e.target === dlg || e.target.closest(".ft-close")) close(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !dlg.hidden) close(); });
})();
