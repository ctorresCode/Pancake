// Sonidos, vibración, contador de XP y animaciones de entrada.
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Los sonidos se generan con Web Audio, así no hay que cargar archivos.
  var ctx = null;
  function muted() { try { return localStorage.getItem("pancake-muted") === "1"; } catch (e) { return false; } }
  function setMuted(v) { try { localStorage.setItem("pancake-muted", v ? "1" : "0"); } catch (e) {} }
  function audio() {
    if (!ctx) {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) return null;
      ctx = new AC();
    }
    if (ctx.state === "suspended") ctx.resume();
    return ctx;
  }
  function tone(freq, start, dur, opts) {
    var c = audio(); if (!c) return;
    opts = opts || {};
    var t = c.currentTime + start;
    var osc = c.createOscillator(), gain = c.createGain();
    osc.type = opts.type || "triangle";
    osc.frequency.setValueAtTime(freq, t);
    if (opts.to) osc.frequency.exponentialRampToValueAtTime(opts.to, t + dur);
    gain.gain.setValueAtTime(0.0001, t);
    gain.gain.exponentialRampToValueAtTime(opts.vol || 0.18, t + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    osc.connect(gain).connect(c.destination);
    osc.start(t); osc.stop(t + dur + 0.05);
  }
  var sounds = {
    tap: function () { tone(660, 0, 0.06, { type: "sine", vol: 0.06 }); },
    correct: function () {
      tone(784, 0, 0.14, { vol: 0.16 }); tone(1175, 0.09, 0.28, { vol: 0.16 });
      tone(1568, 0.09, 0.28, { type: "sine", vol: 0.05 });
    },
    wrong: function () {
      tone(311, 0, 0.16, { type: "square", vol: 0.05, to: 277 });
      tone(233, 0.13, 0.3, { type: "square", vol: 0.05, to: 196 });
    },
    complete: function () {
      [523, 659, 784, 1047].forEach(function (f, i) { tone(f, i * 0.11, 0.3, { vol: 0.14 }); });
      tone(1319, 0.48, 0.6, { vol: 0.12 }); tone(1047, 0.48, 0.6, { type: "sine", vol: 0.08 });
    },
    streak: function () { tone(880, 0, 0.1, { type: "sine", vol: 0.08 }); tone(1320, 0.08, 0.2, { type: "sine", vol: 0.08 }); }
  };
  function play(name) { if (!muted() && sounds[name]) { try { sounds[name](); } catch (e) {} } }

  function buzz(pattern) { if (navigator.vibrate && !reduce) { try { navigator.vibrate(pattern); } catch (e) {} } }

  function countUp(el, to, ms) {
    var from = parseInt(el.textContent, 10) || 0;
    if (reduce || from === to) { el.textContent = to; return; }
    var start = performance.now(); ms = ms || 700;
    (function step(now) {
      var p = Math.min(1, (now - start) / ms), e = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step);
    })(start);
  }

  function react(el, mood) {
    if (!el) return;
    el.classList.remove("happy", "sad"); void el.getBoundingClientRect();
    el.classList.add(mood);
  }

  window.PancakeFX = { play: play, buzz: buzz, countUp: countUp, react: react, muted: muted, setMuted: setMuted, reduce: reduce };

  // Secciones de la portada que aparecen al bajar
  document.documentElement.classList.add("js");
  var revealEls = document.querySelectorAll("[data-reveal]");
  if (reduce || !("IntersectionObserver" in window)) {
    revealEls.forEach(function (el) { el.classList.add("in"); });
  } else {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
    }, { threshold: 0.15, rootMargin: "0px 0px -40px 0px" });
    revealEls.forEach(function (el) { io.observe(el); });
  }

  // Al cargar cada página, los bloques entran uno detrás de otro
  if (!reduce) {
    var sel = [".page-head", ".lesson-head", ".summary", ".class-head", ".level-title", ".lesson-list > *",
               ".lesson-cards > *", ".quick-actions > *", ".stats > .card", ".video-frame", ".strip", ".practice",
               ".grid-2 > .card", "main .container > .card", "form.card", ".vocab-grid > *", ".auth-card",
               ".panel-nav a", ".ex-list > *"];
    var seen = new Set(), i = 0;
    document.querySelectorAll(sel.join(",")).forEach(function (el) {
      if (seen.has(el) || el.closest(".dropdown")) return;
      seen.add(el);
      el.style.setProperty("--d", Math.min(i++, 14) * 55 + "ms");
      el.classList.add("reveal");
    });
  }
})();
