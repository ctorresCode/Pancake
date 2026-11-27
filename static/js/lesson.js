/* Motor de la lección: video de YouTube + ejercicios sincronizados */
(function () {
  "use strict";

  var CFG = window.PANCAKE;
  var DATA = JSON.parse(document.getElementById("lesson-data").textContent);
  var EXS = DATA.exercises;
  var DONE = { correct: 1, wrong: 1 };
  var HAS_VIDEO = !!DATA.videoId;  // lección solo con ejercicios: sin reproductor, todo disponible

  var $ = function (id) { return document.getElementById(id); };
  var card = $("ex-card");

  var state = {
    mode: readMode(),
    unlocked: new Set(),
    current: null,     // índice del ejercicio en pantalla
    answer: null,      // respuesta seleccionada en la tarjeta actual
    checked: false,    // ya se pulsó COMPROBAR en la tarjeta actual
    pausedFor: null,   // índice del ejercicio que pausó el video
    clipEnd: null,
    duration: 0,
    maxWatched: DATA.startAt || 0,
    lastSaved: 0,
    showDoneAfter: false,
    lessonXp: 0,
    player: null,
    ready: false
  };

  // Ejercicios ya respondidos antes, o anteriores a donde se quedó el video, quedan disponibles.
  EXS.forEach(function (ex, i) {
    if (ex.status || ex.trigger <= (DATA.startAt || 0)) state.unlocked.add(i);
  });

  // Utilidades
  function h(tag, attrs, children) {
    var el = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "class") el.className = v;
      else if (k === "text") el.textContent = v;
      else if (k.slice(0, 2) === "on") el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? "" : v);
    });
    (children || []).forEach(function (c) {
      if (c === null || c === undefined) return;
      el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
    });
    return el;
  }
  var FX = window.PancakeFX || { play: function () {}, buzz: function () {}, react: function () {}, countUp: function (el, v) { el.textContent = v; }, muted: function () { return true; }, setMuted: function () {} };
  function mascot() {
    var tpl = document.getElementById("mascot-tpl");
    return tpl ? tpl.content.firstElementChild.cloneNode(true) : h("img", { src: CFG.mascot, alt: "" });
  }
  function ic(name, weight) { return h("i", { class: "ph-" + (weight || "fill") + " ph-" + name, "aria-hidden": "true" }); }
  function fmt(s) { s = Math.max(0, Math.floor(s || 0)); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); }
  function url(tpl, id) { return tpl.replace("/0/", "/" + id + "/"); }
  function post(u, body, keepalive) {
    return fetch(u, {
      method: "POST", keepalive: !!keepalive, credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CFG.csrf },
      body: JSON.stringify(body || {})
    }).then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); });
  }
  function readMode() { try { return localStorage.getItem("pancake-mode") || "synced"; } catch (e) { return "synced"; } }
  function saveMode(m) { try { localStorage.setItem("pancake-mode", m); } catch (e) {} }
  var toastTimer;
  function toast(msg, icon) {
    var t = $("toast"); t.innerHTML = "";
    if (icon) t.appendChild(ic(icon));
    t.appendChild(document.createTextNode(msg)); t.classList.add("show");
    clearTimeout(toastTimer); toastTimer = setTimeout(function () { t.classList.remove("show"); }, 2600);
  }
  function bump(el) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
  function isUnlocked(i) { return state.mode === "free" || state.unlocked.has(i); }
  function isDone(i) { return !!DONE[EXS[i].status]; }

  // Video
  window.onYouTubeIframeAPIReady = function () {
    state.player = new YT.Player("player", {
      videoId: DATA.videoId,
      playerVars: { rel: 0, modestbranding: 1, playsinline: 1, start: DATA.startAt || 0, hl: "en" },
      events: {
        onReady: function () {
          state.ready = true;
          state.duration = state.player.getDuration() || 0;
          drawCues();
          if (state.current === null) render(false);  // muestra el botón "Watch video"
        },
        onStateChange: function (e) {
          if (!state.duration) { state.duration = state.player.getDuration() || 0; drawCues(); }
          if (e.data === YT.PlayerState.PAUSED) saveProgress();
          if (state.current === null && (e.data === YT.PlayerState.PLAYING || e.data === YT.PlayerState.PAUSED)) render(false);
          if (e.data === YT.PlayerState.ENDED) { state.maxWatched = state.duration; saveProgress(); onVideoEnded(); }
        }
      }
    });
  };
  if (HAS_VIDEO) setTimeout(function () {
    if (!state.ready && !window.YT) {
      toast("The video couldn't load. All exercises are open in free mode.");
      setMode("free");
    }
  }, 9000);

  function time() { try { return state.player && state.ready ? state.player.getCurrentTime() || 0 : 0; } catch (e) { return 0; } }
  function playing() { try { return state.ready && state.player.getPlayerState() === YT.PlayerState.PLAYING; } catch (e) { return false; } }
  function play() { if (state.ready) state.player.playVideo(); }
  function pause() { if (state.ready) state.player.pauseVideo(); }
  function seek(s) { if (state.ready) state.player.seekTo(Math.max(0, s), true); }

  function playClip(range) {
    if (!state.ready) return toast("The video is still loading...");
    state.clipEnd = range[1];
    seek(range[0]); play();
  }

  function tick() {
    if (!state.ready) return;
    var t = time();
    $("time-label").textContent = fmt(t) + (state.duration ? " / " + fmt(state.duration) : "");
    if (state.duration) $("cue-fill").style.width = Math.min(100, (t / state.duration) * 100) + "%";
    if (playing() && t > state.maxWatched) state.maxWatched = t;

    if (state.clipEnd !== null && t >= state.clipEnd) { state.clipEnd = null; pause(); }

    if (state.mode !== "free") {
      var fresh = [];
      EXS.forEach(function (ex, i) {
        if (!state.unlocked.has(i) && t + 0.2 >= ex.trigger) { state.unlocked.add(i); fresh.push(i); }
      });
      if (fresh.length) onUnlocked(fresh[fresh.length - 1], fresh.length);
    }
    if (playing() && Date.now() - state.lastSaved > 15000) saveProgress();
  }
  setInterval(tick, 250);

  function saveProgress(keepalive) {
    if (!state.duration) return;
    state.lastSaved = Date.now();
    post(CFG.progressUrl, {
      percent: Math.round((state.maxWatched / state.duration) * 100),
      position: Math.floor(time())
    }, keepalive).catch(function () {});
  }
  document.addEventListener("visibilitychange", function () { if (document.hidden) saveProgress(true); });

  function onUnlocked(i, howMany) {
    var ex = EXS[i];
    var busy = state.current !== null && !state.checked && state.answer !== null && state.answer !== undefined &&
               !(Array.isArray(state.answer) && !state.answer.length);
    if (busy) {
      toast(howMany > 1 ? "New exercises available!" : "New exercise available!", "arrow-down");
      renderChrome();
    } else {
      go(i, true);
    }
    if ((state.mode === "pause" || ex.pause) && !isDone(i)) {
      pause(); state.pausedFor = i;
      if (!busy) toast("Video paused: answer to keep going", "pause-circle");
    }
    if (window.innerWidth > 720) {
      var r = card.getBoundingClientRect();
      if (r.top > window.innerHeight - 120) card.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function onVideoEnded() {
    // Los ejercicios puestos después del final del video se abren al terminar
    EXS.forEach(function (ex, i) { state.unlocked.add(i); });
    renderChrome(); drawCues();
    var pending = EXS.findIndex(function (ex, i) { return isUnlocked(i) && !isDone(i); });
    if (pending >= 0 && state.current === null) go(pending, true);
  }

  // Modo
  function setMode(m) {
    state.mode = m; saveMode(m);
    document.querySelectorAll(".mode-opt").forEach(function (b) { b.setAttribute("aria-pressed", b.dataset.mode === m); });
    if (m === "free" && state.current === null && EXS.length) {
      var first = EXS.findIndex(function (ex, i) { return !isDone(i); });
      go(first >= 0 ? first : 0, true);
    } else if (m !== "free" && state.current !== null && !state.unlocked.has(state.current)) {
      state.current = null; render();
    } else renderChrome();
  }
  var MODE_NAMES = { synced: "Synced", pause: "Pause at exercises", free: "Free" };
  var setBtn = $("settings-btn"), pop = $("settings-pop");
  function togglePop(open) {
    if (!pop) return;
    open = open === undefined ? pop.hidden : open;
    pop.hidden = !open; setBtn.setAttribute("aria-expanded", open);
    var head = pop.closest(".lesson-head"); if (head) head.classList.toggle("pop-open", open);
    if (open) { var cur = pop.querySelector('[aria-pressed="true"]'); if (cur) cur.focus(); }
  }
  if (setBtn) {
    setBtn.addEventListener("click", function (e) { e.stopPropagation(); togglePop(); });
    pop.addEventListener("click", function (e) { e.stopPropagation(); });
    document.addEventListener("click", function () { togglePop(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape" && !pop.hidden) { togglePop(false); setBtn.focus(); } });
  }
  document.querySelectorAll(".mode-opt").forEach(function (b) {
    b.addEventListener("click", function () {
      setMode(b.dataset.mode); togglePop(false);
      toast("Mode: " + MODE_NAMES[b.dataset.mode], "gear-six");
    });
  });

  // Navegación
  function go(i, animate, fresh) {
    state.current = i; state.answer = null; state.checked = false; state.retry = !!fresh;
    render(animate);
    state.retry = false;
    if (animate) fitCard();
  }
  // En celular: deja el ejercicio justo debajo del video fijo
  function fitCard() {
    if (window.innerWidth > 720) return;
    var vz = document.querySelector(".video-zone");
    var below = vz ? vz.getBoundingClientRect().bottom : 0;
    var top = card.getBoundingClientRect().top;
    if (Math.abs(top - below - 10) < 30) return;
    window.scrollTo({ top: Math.max(0, window.scrollY + top - below - 10), behavior: FX.reduce ? "auto" : "smooth" });
  }
  // Primero los que no ha visto; luego los que saltó (sin volver al que acaba de saltar)
  function nextPending(from) {
    var skipped = null;
    for (var k = 1; k <= EXS.length; k++) {
      var j = (from + k) % EXS.length;
      if (!isUnlocked(j) || isDone(j)) continue;
      if (!EXS[j].status) return j;
      if (skipped === null && j !== from) skipped = j;
    }
    return skipped;
  }
  function continueFlow() {
    if (state.pausedFor === state.current) { state.pausedFor = null; play(); }
    if (state.showDoneAfter) { state.showDoneAfter = false; return showDone(); }
    var nxt = nextPending(state.current === null ? -1 : state.current);
    if (nxt !== null) return go(nxt, true);
    state.current = null; render(true);
  }
  $("prev-btn").addEventListener("click", function () { step(-1); });
  $("next-btn").addEventListener("click", function () { step(1); });
  function step(dir) {
    var i = state.current === null ? (dir > 0 ? -1 : EXS.length) : state.current;
    for (var j = i + dir; j >= 0 && j < EXS.length; j += dir) if (isUnlocked(j)) return go(j, true);
  }

  // Interfaz general
  function renderChrome() {
    var seg = $("segments"); seg.innerHTML = "";
    EXS.forEach(function (ex, i) {
      var cls = "seg";
      if (ex.status) cls += " " + ex.status;
      else if (isUnlocked(i)) cls += " unlocked";
      if (i === state.current) cls += " current";
      seg.appendChild(h("button", {
        class: cls, type: "button", disabled: !isUnlocked(i),
        "aria-label": "Exercise " + (i + 1) + (ex.status ? " (" + statusText(ex.status) + ")" : isUnlocked(i) ? "" : " (locked)"),
        onclick: function () { go(i, true); }
      }));
    });
    var done = EXS.filter(function (ex, i) { return isDone(i); }).length;
    $("count").textContent = done + " of " + EXS.length + " done";
    $("strip").style.display = EXS.length ? "" : "none";

    var prevOk = false, nextOk = false, c = state.current === null ? -1 : state.current;
    EXS.forEach(function (ex, i) { if (isUnlocked(i)) { if (i < c) prevOk = true; if (i > c) nextOk = true; } });
    if (state.current === null) prevOk = EXS.some(function (ex, i) { return isUnlocked(i); });
    $("prev-btn").disabled = !prevOk; $("next-btn").disabled = !nextOk;

    var teasers = $("teasers"); teasers.innerHTML = "";
    EXS.forEach(function (ex, i) {
      if (isUnlocked(i)) return;
      teasers.appendChild(h("div", { class: "teaser" }, [
        h("span", { class: "lock" }, [ic("lock-simple")]),
        h("span", { text: "Exercise " + (i + 1) + ": " + ex.label }),
        h("span", { class: "time", text: "shows up at " + ex.triggerLabel })
      ]));
    });
    drawCues();
  }

  function drawCues() {
    var strip = $("cue-strip");
    if (!strip) return;
    strip.querySelectorAll(".cue").forEach(function (c) { c.remove(); });
    if (!state.duration) return;
    EXS.forEach(function (ex, i) {
      var cls = "cue" + (ex.status ? " " + ex.status : isUnlocked(i) ? " unlocked" : "");
      strip.appendChild(h("button", {
        class: cls, type: "button", style: "left:" + Math.min(100, (ex.trigger / state.duration) * 100) + "%",
        title: "Exercise " + (i + 1) + ", at " + ex.triggerLabel,
        "aria-label": "Go to exercise " + (i + 1) + " at " + ex.triggerLabel,
        onclick: function () {
          if (isUnlocked(i)) go(i, true);
          else { seek(ex.trigger - 3); play(); }
        }
      }));
    });
  }

  function statusText(s) { return s === "correct" ? "correct" : s === "wrong" ? "wrong" : "skipped"; }

  // Tarjeta
  function render(animate) {
    renderChrome();
    card.innerHTML = "";
    if (animate) { card.classList.remove("enter"); void card.offsetWidth; card.classList.add("enter"); }
    if (state.current === null) return renderWaiting();
    var i = state.current, ex = EXS[i];

    var top = h("div", { class: "ex-top" }, [
      h("span", { class: "chip label", text: "Exercise " + (i + 1) + ": " + ex.label }),
      !HAS_VIDEO ? null : h("button", {
        class: "btn ghost sm", type: "button", title: "Watch this part of the video again",
        onclick: function () { seek(ex.trigger - 10); play(); }
      }, [ic("arrow-counter-clockwise", "bold"), " " + ex.triggerLabel])
    ]);
    if (ex.status === "correct") {
      var done = h("span", { class: "pill on" }, [ic("check", "bold"), " Done"]);
      if (HAS_VIDEO) top.insertBefore(done, top.lastChild); else top.appendChild(done);
    }

    var body = h("div", { class: "ex-body" });
    var builders = {
      multiple_choice: buildChoice, listening: buildChoice, fill_blank: buildFill,
      true_false: buildTrueFalse, order_words: buildOrder, listen_type: buildType, flashcard: buildFlash
    };
    (builders[ex.type] || buildChoice)(ex, body);

    card.appendChild(top);
    card.appendChild(body);
    card.appendChild(ex.type === "flashcard" ? flashActions(ex) : actions(ex));

    // Repaso: si ya lo respondió, se muestra su respuesta
    if (!state.retry && ex.type !== "flashcard" && (ex.status === "correct" || ex.status === "wrong") &&
        ex.lastAnswer !== null && ex.lastAnswer !== undefined) {
      restoreAnswer(ex);
      paintResult(ex, { correct: ex.status === "correct", correctAnswer: ex.correctAnswer, explanation: ex.explanation }, true);
    }
  }

  function restoreAnswer(ex) {
    var a = ex.lastAnswer;
    if (ex.type === "order_words") {
      var words = Array.isArray(a) ? a : String(a).split(" "), used = [];
      words.forEach(function (w) {
        for (var k = 0; k < ex.tiles.length; k++) {
          if (used.indexOf(k) < 0 && ex.tiles[k] === w) { used.push(k); break; }
        }
      });
      state.answer = used; state.checked = true;
      if (card._redraw) card._redraw();
    } else if (ex.type === "listen_type") {
      var input = card.querySelector(".type-answer");
      if (input) input.value = a;
      state.answer = a; state.checked = true;
    } else {
      select(a, true);
      state.checked = true;
    }
  }

  function renderWaiting() {
    var next = EXS.findIndex(function (ex, i) { return !isUnlocked(i); });
    var allDone = EXS.length && EXS.every(function (ex, i) { return isDone(i); });
    var title, sub;
    if (!EXS.length) { title = "This lesson has no exercises yet"; sub = HAS_VIDEO ? "Enjoy the video." : "Your teacher is still working on it."; }
    else if (allDone) { title = "You finished all the exercises!"; sub = "Use the arrows to review them any time."; }
    else if (next >= 0) { title = state.unlocked.size ? "Nice! Keep watching the video" : "Press play on the video"; sub = state.duration && EXS[next].trigger >= state.duration ? "The next exercise shows up when the video ends." : "The next exercise shows up at " + EXS[next].triggerLabel + "."; }
    var left = EXS.findIndex(function (ex, i) { return isUnlocked(i) && !isDone(i); });
    if (EXS.length && !allDone && next < 0) {
      var n = EXS.filter(function (ex, i) { return !isDone(i); }).length;
      var allSkipped = EXS.every(function (ex, i) { return isDone(i) || ex.status === "skipped"; });
      title = allSkipped ? (n === 1 ? "You skipped 1 exercise" : "You skipped " + n + " exercises")
                         : (n === 1 ? "1 exercise left" : n + " exercises left");
      sub = "Answer " + (n === 1 ? "it" : "them") + " to finish the lesson.";
    }
    card.appendChild(h("div", { class: "waiting" }, [
      mascot(),
      h("h2", { text: title }),
      h("p", { class: "muted", text: sub }),
      next >= 0 && state.ready && !playing() ? h("button", { class: "btn", type: "button", onclick: play }, [ic("play"), " Watch video"]) : null,
      next < 0 && left >= 0 && !allDone ? h("button", { class: "btn", type: "button", onclick: function () { go(left, true); } }, [n === 1 ? "Answer it now" : "Answer them now"]) : null
    ]));
  }

  function promptBubble(text) {
    return h("div", { class: "ex-prompt" }, [
      mascot(),
      h("div", { class: "bubble" }, [h("p", { class: "ex-question", text: text })])
    ]);
  }

  function listenBox(ex) {
    return h("div", { class: "listen-box" }, [
      h("button", { class: "play-clip", type: "button", "aria-label": "Play the clip", onclick: function () { playClip(ex.clip); } }, [ic("speaker-high")]),
      h("span", { class: "muted", text: "Listen to the clip (" + fmt(ex.clip[0]) + " to " + fmt(ex.clip[1]) + "). You can play it again." })
    ]);
  }

  function select(value, quiet) {
    if (state.checked) return;
    if (!quiet && state.answer !== value) FX.play("tap");
    state.answer = value;
    card.querySelectorAll("[data-value]").forEach(function (b) {
      var on = String(b.dataset.value) === String(value);
      b.classList.toggle("selected", on); b.setAttribute("aria-pressed", on);
    });
    var blank = card.querySelector(".blank");
    if (blank) {
      var opt = EXS[state.current].options.find(function (o) { return String(o.id) === String(value); });
      blank.textContent = opt ? opt.text : ""; blank.classList.toggle("filled", !!opt);
    }
    updateCheck();
  }

  function buildChoice(ex, body) {
    body.appendChild(promptBubble(ex.title));
    if (ex.type === "listening") body.appendChild(listenBox(ex));
    var grid = h("div", { class: "options" });
    ex.options.forEach(function (o, k) {
      grid.appendChild(h("button", {
        class: "option", type: "button", "data-value": o.id, "aria-pressed": "false",
        onclick: function () { select(o.id); }
      }, [h("span", { class: "key", text: String(k + 1) }), h("span", { text: o.text })]));
    });
    body.appendChild(grid);
  }

  function buildFill(ex, body) {
    body.appendChild(promptBubble(ex.title));
    var parts = (ex.sentence || "").split("___");
    var line = h("div", { class: "sentence" });
    parts.forEach(function (p, k) {
      if (p.trim()) line.appendChild(h("span", { text: p.trim() }));
      if (k < parts.length - 1) line.appendChild(h("span", { class: "blank", "aria-label": "blank" }));
    });
    body.appendChild(line);
    var tiles = h("div", { class: "tiles" });
    ex.options.forEach(function (o) {
      tiles.appendChild(h("button", { class: "tile", type: "button", "data-value": o.id, "aria-pressed": "false", text: o.text, onclick: function () { select(o.id); } }));
    });
    body.appendChild(tiles);
  }

  function buildTrueFalse(ex, body) {
    body.appendChild(promptBubble(ex.title));
    body.appendChild(h("div", { class: "sentence", text: ex.statement }));
    var grid = h("div", { class: "options tf" });
    [["true", "True", "check-circle"], ["false", "False", "x-circle"]].forEach(function (p, k) {
      grid.appendChild(h("button", { class: "option", type: "button", "data-value": p[0], "aria-pressed": "false", onclick: function () { select(p[0]); } },
        [ic(p[2]), h("span", { text: p[1] })]));
    });
    body.appendChild(grid);
  }

  function buildOrder(ex, body) {
    body.appendChild(promptBubble(ex.title));
    var line = h("div", { class: "answer-line", "aria-label": "Your sentence" });
    var pool = h("div", { class: "tiles" });
    state.answer = [];
    function redraw() {
      line.innerHTML = "";
      state.answer.forEach(function (idx, pos) {
        line.appendChild(h("button", { class: "tile", type: "button", text: ex.tiles[idx], disabled: state.checked,
          onclick: function () { state.answer.splice(pos, 1); redraw(); } }));
      });
      pool.querySelectorAll(".tile").forEach(function (b) { b.classList.toggle("used", state.answer.indexOf(+b.dataset.idx) >= 0); });
      updateCheck();
    }
    ex.tiles.forEach(function (w, idx) {
      pool.appendChild(h("button", { class: "tile", type: "button", "data-idx": idx, text: w,
        onclick: function () { if (!state.checked && state.answer.indexOf(idx) < 0) { state.answer.push(idx); redraw(); } } }));
    });
    body.appendChild(line); body.appendChild(pool);
    card._redraw = redraw;
    setTimeout(redraw);
  }

  function buildType(ex, body) {
    body.appendChild(promptBubble(ex.title));
    body.appendChild(listenBox(ex));
    var input = h("input", { type: "text", class: "type-answer", placeholder: "Type in English...", autocomplete: "off", autocapitalize: "off", spellcheck: "false", "aria-label": "Your answer" });
    input.addEventListener("input", function () { state.answer = input.value.trim() || null; updateCheck(); });
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); primary(); } });
    body.appendChild(h("div", { class: "field" }, [input]));
  }

  function buildFlash(ex, body) {
    body.appendChild(h("div", { class: "flashcard" }, [
      h("div", { class: "muted", text: "New expression from the video" }),
      h("div", { class: "expr", text: ex.expression }),
      h("div", { class: "meaning", text: ex.meaning }),
      ex.explanation ? h("p", { class: "muted", style: "margin-top:14px", text: ex.explanation }) : null
    ]));
  }

  // Acciones
  function actions(ex) {
    var bar = h("div", { class: "ex-actions", id: "ex-actions" }, [
      h("button", { class: "btn ghost", type: "button", text: "Skip", onclick: skip }),
      h("button", { class: "btn", type: "button", id: "check-btn", text: "Check", disabled: true, onclick: primary })
    ]);
    return bar;
  }

  function flashActions(ex) {
    function saveLabel(b) {
      b.innerHTML = "";
      b.appendChild(ic("bookmark-simple", ex.saved ? "fill" : "bold"));
      b.appendChild(document.createTextNode(ex.saved ? " Saved" : " Save to my vocabulary"));
    }
    var saveBtn = h("button", {
      class: "btn secondary", type: "button",
      onclick: function () {
        post(url(CFG.vocabUrl, ex.id)).then(function (d) {
          ex.saved = d.saved; saveLabel(saveBtn);
          toast(d.saved ? "Saved to your vocabulary" : "Removed from your vocabulary", "bookmark-simple");
        }).catch(function () { toast("Couldn't save it. Try again."); });
      }
    });
    saveLabel(saveBtn);
    return h("div", { class: "ex-actions", id: "ex-actions" }, [
      saveBtn,
      h("button", { class: "btn", type: "button", id: "check-btn", text: "Got it!", onclick: function () { state.answer = "ok"; primary(); } })
    ]);
  }

  function updateCheck() {
    var b = $("check-btn"); if (!b || state.checked) return;
    var a = state.answer, was = b.disabled;
    b.disabled = a === null || a === undefined || (Array.isArray(a) && !a.length);
    if (was && !b.disabled) { b.classList.remove("pop"); void b.offsetWidth; b.classList.add("pop"); }
  }

  function primary() {
    if (state.checked) return continueFlow();
    var b = $("check-btn"); if (!b || b.disabled) return;
    var ex = EXS[state.current];
    var answer = state.answer;
    if (ex.type === "order_words") answer = state.answer.map(function (k) { return ex.tiles[k]; });
    b.disabled = true;
    post(url(CFG.checkUrl, ex.id), { answer: answer }).then(function (d) { showResult(ex, d, answer); })
      .catch(function () { b.disabled = false; toast("We couldn't check your answer. Try again."); });
  }

  function skip() {
    var i = state.current, ex = EXS[i];
    if (!ex.status) {
      ex.status = "skipped";
      post(url(CFG.skipUrl, ex.id)).catch(function () {});
    }
    continueFlow();
  }

  var PRAISE = ["Excellent!", "Great job!", "Perfect!", "Awesome!", "Nice work!"];
  function showResult(ex, d, answer) {
    state.checked = true;
    ex.status = d.status;
    if (ex.type !== "flashcard") { ex.lastAnswer = answer; ex.correctAnswer = d.correctAnswer; ex.explanation = d.explanation; }
    state.lessonXp = d.lessonXp;

    // sonido, vibración y mascota
    if (ex.type !== "flashcard") {
      FX.play(d.correct ? "correct" : "wrong");
      FX.buzz(d.correct ? 35 : [40, 60, 40]);
      FX.react(card.querySelector(".mascot"), d.correct ? "happy" : "sad");
    } else FX.play("correct");

    // actualizar top bar
    var xpVal = $("xp-val"), stVal = $("streak-val");
    if (xpVal && +xpVal.textContent !== d.totalXp) { FX.countUp(xpVal, d.totalXp); bump($("xp-chip")); }
    if (stVal) { stVal.textContent = d.streak; $("streak-chip").classList.toggle("off", !d.streak); if (d.streakUp) { bump($("streak-chip")); setTimeout(function () { FX.play("streak"); }, 450); toast(d.streak + " day streak!", "fire"); } }

    if (ex.type === "flashcard") { renderChrome(); state.checked = true; return finishAfter(d) || continueFlow(); }
    paintResult(ex, d, false);
    $("check-btn").focus({ preventScroll: true });
    renderChrome();
    finishAfter(d);
  }

  // Marca la respuesta en la tarjeta y muestra la barra de resultado (en vivo o en repaso)
  function paintResult(ex, d, review) {
    card.querySelectorAll("[data-value], .tile, input, .play-clip").forEach(function (el) { if (!el.classList.contains("play-clip")) el.disabled = true; });
    var sel = card.querySelector("[data-value].selected");
    if (sel) sel.classList.add(d.correct ? "is-correct" : "is-wrong");
    if (!d.correct && d.correctAnswer) {
      card.querySelectorAll("[data-value]").forEach(function (el) {
        var txt = el.querySelector("span:last-child") ? el.querySelector("span:last-child").textContent : el.textContent;
        if (txt === d.correctAnswer) el.classList.add("is-correct");
      });
    }
    var blank = card.querySelector(".blank"); if (blank) blank.classList.add(d.correct ? "ok" : "bad");
    var line = card.querySelector(".answer-line"); if (line) line.classList.add(d.correct ? "ok" : "bad");
    var typed = card.querySelector(".type-answer"); if (typed) typed.classList.add(d.correct ? "typed-ok" : "typed-bad");

    var bar = $("ex-actions");
    bar.className = "ex-actions " + (d.correct ? "ok" : "bad");
    bar.innerHTML = "";
    var msg = d.correct
      ? (review ? "This is the answer you gave." : d.xpGained ? "+" + d.xpGained + " XP" : "You already got this one")
      : (d.correctAnswer ? "Correct answer: " + d.correctAnswer : "Try again later");
    var title = review ? (d.correct ? "You got this one right" : "Your answer was wrong")
                       : (d.correct ? PRAISE[Math.floor(Math.random() * PRAISE.length)] : "Almost!");
    var i = state.current, hasNext = review && i + 1 < EXS.length && isUnlocked(i + 1);
    var fb = h("div", { class: "feedback", role: "status" }, [
      h("span", { class: "fb-ico", "aria-hidden": "true" }, [ic(d.correct ? "check" : "x", "bold")]),
      h("div", {}, [
        h("strong", { text: title }),
        h("span", { class: d.correct && d.xpGained ? "xp-pop" : "", text: msg }),
        d.explanation ? h("div", { class: "small muted", text: d.explanation }) : null
      ])
    ]);
    var btns = h("div", { class: "row-actions" }, [
      (!d.correct || review) ? h("button", { class: "btn ghost", type: "button", text: "Try again", onclick: function () { go(state.current, false, true); } }) : null,
      h("button", { class: "btn " + (d.correct ? "green" : "coral"), type: "button", id: "check-btn", text: hasNext ? "Next" : "Continue",
        onclick: hasNext ? function () { go(i + 1, true); } : continueFlow })
    ]);
    bar.appendChild(fb); bar.appendChild(btns);
  }

  function finishAfter(d) {
    if (d.justCompleted && !state.doneShown) {
      $("done-xp").textContent = "+" + d.lessonXp;
      $("done-acc").textContent = d.correctCount + "/" + d.total;
      state.showDoneAfter = true;
    }
    return false;
  }

  function showDone() {
    state.doneShown = true;
    if (playing()) state.player.pauseVideo();  // que se oiga el festejo
    $("done-modal").classList.add("open");
    FX.play("complete"); FX.buzz([30, 50, 30, 50, 60]);
    FX.react($("done-modal").querySelector(".mascot"), "happy");
    var xpEl = $("done-xp"), target = parseInt(xpEl.textContent.replace("+", ""), 10) || 0;
    xpEl.textContent = "+0";
    (function () { var span = document.createElement("span"); span.textContent = "0"; xpEl.textContent = "+"; xpEl.appendChild(span); FX.countUp(span, target, 1100); })();
    $("done-close").focus();
    confetti();
  }
  $("done-close").addEventListener("click", function () { $("done-modal").classList.remove("open"); state.current = null; render(true); });

  // Teclado
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.ctrlKey || e.metaKey || e.altKey) return;
    if ($("done-modal").classList.contains("open")) return;
    if (/^[1-9]$/.test(e.key) && !state.checked && state.current !== null) {
      var btns = card.querySelectorAll("[data-value]");
      var b = btns[+e.key - 1]; if (b) { b.click(); e.preventDefault(); }
    } else if (e.key === "Enter" && state.current !== null && document.activeElement === document.body) {
      e.preventDefault(); primary();
    }
  });

  // Confeti
  function confetti() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var cv = $("confetti"), ctx = cv.getContext("2d");
    cv.width = innerWidth; cv.height = innerHeight;
    var colors = ["#7C3AED", "#FFC800", "#C4B5FD", "#22C55E", "#FF9600"];
    var parts = Array.from({ length: 160 }, function () {
      return { x: Math.random() * cv.width, y: -20 - Math.random() * cv.height * .5, vx: (Math.random() - .5) * 4,
        vy: 2 + Math.random() * 4, r: 4 + Math.random() * 6, c: colors[Math.floor(Math.random() * colors.length)],
        a: Math.random() * Math.PI, va: (Math.random() - .5) * .3 };
    });
    var start = performance.now();
    (function frame(now) {
      ctx.clearRect(0, 0, cv.width, cv.height);
      parts.forEach(function (p) {
        p.x += p.vx; p.y += p.vy; p.vy += .05; p.a += p.va;
        ctx.save(); ctx.translate(p.x, p.y); ctx.rotate(p.a); ctx.fillStyle = p.c;
        ctx.fillRect(-p.r / 2, -p.r / 4, p.r, p.r / 2); ctx.restore();
      });
      if (now - start < 4000) requestAnimationFrame(frame); else ctx.clearRect(0, 0, cv.width, cv.height);
    })(start);
  }

  // Sonido on/off
  var sb = $("sound-btn");
  function paintSound() {
    var m = FX.muted();
    sb.setAttribute("aria-pressed", m);
    sb.setAttribute("aria-label", m ? "Turn sounds on" : "Mute sounds");
    sb.innerHTML = ""; sb.appendChild(ic(m ? "speaker-slash" : "speaker-high"));
  }
  if (sb) { paintSound(); sb.addEventListener("click", function () { FX.setMuted(!FX.muted()); paintSound(); if (!FX.muted()) FX.play("tap"); }); }

  // Inicio
  if (HAS_VIDEO) {
    setMode(state.mode);
  } else {
    state.mode = "free";
    var firstPending = EXS.findIndex(function (ex, i) { return !isDone(i); });
    if (EXS.length) go(firstPending >= 0 ? firstPending : 0, true);
  }
  if (state.current === null) render();
})();
