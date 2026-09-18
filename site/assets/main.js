/* 桌面歌词 · 官网交互
   只做三件事：滚动入场、画廊滑动、下载链接未配置时给提示。
   没有依赖，没有构建步骤 —— 直接把 site/ 整个上传即可部署。 */

(function () {
  'use strict';

  /* ---------- 1. 滚动入场 ---------- */
  (function initReveal() {
    var items = Array.prototype.slice.call(document.querySelectorAll('.reveal'));

    function revealAll() {
      items.forEach(function (el) { el.classList.add('in'); });
    }

    // 告诉 index.html <head> 里的兜底定时器："入场逻辑已经装好了"，
    // 它就不用强行把内容全显示出来（那样会牺牲滚动动画）。
    window.__dlRevealReady = true;

    if (!items.length) return;

    try {
      // ① 带 #download / #faq 这类锚点直接打开时，页面会**一次性跳**到目标位置，
      //    中间区块根本没进过视口、也就永远不触发入场 —— 用户会直接看到空白。
      // ② 浏览器没有 IntersectionObserver 时同理。
      // 两种情况都不做动画，直接全部显示。
      if (location.hash || !('IntersectionObserver' in window)) {
        revealAll();
        return;
      }

      // 待在视口里（下方留 6% 余量，让元素"快露头"时就淡入）
      function inView(el) {
        var r = el.getBoundingClientRect();
        var vh = window.innerHeight || document.documentElement.clientHeight;
        return r.top < vh * 0.94 && r.bottom > 0;
      }

      var pending = items.slice();

      // sweep 是**保底**通道：不依赖 IntersectionObserver、也不依赖 scroll 事件，
      // 任何一次调用都会把"此刻在视口里"的元素点亮。
      function sweep() {
        if (!pending.length) return;
        pending = pending.filter(function (el) {
          if (el.classList.contains('in')) return false;
          if (inView(el)) { el.classList.add('in'); return false; }
          return true;
        });
      }

      // 主通道：IO 负责"一露头就立刻淡入"，观感最顺
      var io = new IntersectionObserver(function (entries) {
        entries.forEach(function (en) {
          if (en.isIntersecting) {
            en.target.classList.add('in');
            io.unobserve(en.target);
          }
        });
      }, { rootMargin: '0px 0px -6% 0px', threshold: 0.05 });
      items.forEach(function (el) { io.observe(el); });

      sweep();                                   // 首屏立刻点亮，不等 IO 首轮回调
      window.addEventListener('load', sweep);
      window.addEventListener('scroll', sweep, { passive: true });
      window.addEventListener('resize', sweep);
      // 硬保底：无头 / 省电模式 / 后台标签页里 IO 与 scroll 都可能整个不派发，
      // 页面会永久停在隐藏态（整站空白）。定时扫一遍兜住这种情况。
      // 正常浏览器里 pending 很快清空，这里退化成每 400ms 一次的空函数调用。
      var iv = setInterval(sweep, 400);
      setTimeout(function () { clearInterval(iv); }, 12000);
    } catch (err) {
      // 任何一步抛错（老浏览器、被扩展干扰……）都不能让内容留在隐藏态
      revealAll();
    }
  })();

  /* ---------- 2. 画廊：滚轮竖向转横向 + 鼠标拖拽 ---------- */
  document.querySelectorAll('.gallery').forEach(function (g) {
    g.addEventListener('wheel', function (e) {
      // 只在"竖滚为主、且还没有横滚到底"时接管，避免把正常的上下滚动吃掉
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      var max = g.scrollWidth - g.clientWidth;
      var next = g.scrollLeft + e.deltaY;
      if (next > 0 && next < max) {
        e.preventDefault();
        g.scrollLeft = next;
      }
    }, { passive: false });

    var down = false, startX = 0, startLeft = 0;
    g.addEventListener('pointerdown', function (e) {
      if (e.pointerType !== 'mouse') return;      // 触屏交给浏览器原生滚动
      down = true; startX = e.clientX; startLeft = g.scrollLeft;
      g.style.cursor = 'grabbing';
    });
    g.addEventListener('pointermove', function (e) {
      if (!down) return;
      g.scrollLeft = startLeft - (e.clientX - startX);
    });
    ['pointerup', 'pointerleave', 'pointercancel'].forEach(function (t) {
      g.addEventListener(t, function () { down = false; g.style.cursor = ''; });
    });
  });

  /* ---------- 3. 下载链接未配置时给个明确提示 ---------- */
  var tip = null;
  function toast(msg) {
    if (!tip) {
      tip = document.createElement('div');
      tip.style.cssText =
        'position:fixed;left:50%;bottom:32px;transform:translateX(-50%);' +
        'max-width:min(92vw,560px);padding:14px 20px;border-radius:14px;' +
        'background:rgba(28,30,36,.96);color:#f5f5f7;font-size:14px;line-height:1.55;' +
        'border:1px solid rgba(255,255,255,.16);box-shadow:0 18px 50px rgba(0,0,0,.5);' +
        'z-index:200;opacity:0;transition:opacity .25s;';
      document.body.appendChild(tip);
    }
    tip.textContent = msg;
    requestAnimationFrame(function () { tip.style.opacity = '1'; });
    clearTimeout(tip._t);
    tip._t = setTimeout(function () { tip.style.opacity = '0'; }, 4200);
  }

  document.querySelectorAll('[data-dl]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      var href = a.getAttribute('href');
      if (!href || href === '#') {
        e.preventDefault();
        toast('下载地址还没填：打开 index.html，搜索「配置区」，把 href="#" 换成你的蓝奏云 / GitHub 链接即可。');
      }
    });
  });
})();
