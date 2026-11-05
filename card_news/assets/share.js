/*
 * 카카오톡 공유 버튼
 * - config.json 에 카카오 JavaScript 키가 있으면: 카카오톡 공유 창이 바로 뜸
 * - 키가 없으면: 휴대폰 공유 메뉴(카톡 포함)가 뜨고, PC에서는 링크가 복사됨
 * data-share="주소" 가 붙은 버튼은 모두 자동으로 동작한다. (빈 값이면 지금 보고 있는 페이지 주소)
 */
(function () {
  var cfg = window.CARDNEWS_CONFIG || {};
  var KAKAO_SDK = "https://t1.kakaocdn.net/kakao_js_sdk/2.7.4/kakao.min.js";
  var kakaoReady = null;

  function loadKakao() {
    if (!cfg.kakaoKey) return Promise.resolve(null);
    if (kakaoReady) return kakaoReady;
    kakaoReady = new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = KAKAO_SDK;
      s.crossOrigin = "anonymous";
      s.onload = function () {
        try {
          if (!window.Kakao.isInitialized()) window.Kakao.init(cfg.kakaoKey);
          resolve(window.Kakao);
        } catch (e) {
          resolve(null);
        }
      };
      s.onerror = function () { resolve(null); };
      document.head.appendChild(s);
    });
    return kakaoReady;
  }
  // 버튼을 누르기 전에 미리 불러둔다 (누른 직후 바로 뜨도록)
  loadKakao();

  function toast(msg) {
    var el = document.createElement("div");
    el.textContent = msg;
    el.setAttribute("role", "status");
    el.style.cssText =
      "position:fixed;left:50%;bottom:calc(76px + env(safe-area-inset-bottom));transform:translateX(-50%);" +
      "z-index:2147483647;max-width:calc(100% - 32px);padding:11px 16px;border-radius:12px;" +
      "background:rgba(23,24,28,.92);color:#fff;font:500 14px/1.4 -apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;" +
      "text-align:center;box-shadow:0 6px 20px rgba(0,0,0,.25)";
    document.body.appendChild(el);
    setTimeout(function () { el.remove(); }, 2600);
  }

  function copy(url) {
    function fallback() {
      var ta = document.createElement("textarea");
      ta.value = url;
      ta.style.cssText = "position:fixed;opacity:0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy"); toast("링크를 복사했어요. 카톡에 붙여넣기 하세요"); }
      catch (e) { window.prompt("아래 링크를 복사하세요", url); }
      ta.remove();
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(function () {
        toast("링크를 복사했어요. 카톡에 붙여넣기 하세요");
      }, fallback);
    } else {
      fallback();
    }
  }

  function share(url, title) {
    url = new URL(url || location.href, location.href).href;
    loadKakao().then(function (Kakao) {
      if (Kakao && Kakao.Share) {
        try {
          Kakao.Share.sendScrap({ requestUrl: url });
          return;
        } catch (e) { /* 아래 방법으로 넘어감 */ }
      }
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () {});
        return;
      }
      copy(url);
    });
  }

  window.cardnewsShare = share;

  document.addEventListener("click", function (e) {
    var btn = e.target.closest && e.target.closest("[data-share]");
    if (!btn) return;
    e.preventDefault();
    share(btn.getAttribute("data-share"), btn.getAttribute("data-title") || document.title);
  });
})();
