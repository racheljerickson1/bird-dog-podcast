(function () {
  var KEY = 'bdbg-announce-dismissed';
  var DAYS = 14;
  var bar = document.getElementById('announce-bar');
  var closeBtn = document.getElementById('announce-bar-close');
  if (!bar) return;

  function dismissed() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return false;
      var until = parseInt(raw, 10);
      if (!until || Date.now() > until) {
        localStorage.removeItem(KEY);
        return false;
      }
      return true;
    } catch (e) {
      return false;
    }
  }

  if (!dismissed()) {
    bar.hidden = false;
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      bar.hidden = true;
      try {
        localStorage.setItem(KEY, String(Date.now() + DAYS * 24 * 60 * 60 * 1000));
      } catch (e) {}
    });
  }
})();

(function () {
  var toggle = document.getElementById('nav-toggle');
  var nav = document.querySelector('.site-nav');
  if (!toggle || !nav) return;

  toggle.addEventListener('click', function () {
    var open = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? 'Close menu' : 'Open menu');
  });
})();
