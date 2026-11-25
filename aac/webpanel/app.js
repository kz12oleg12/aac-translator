"use strict";
const T = "__TOKEN__", H = {"X-Token": T, "Content-Type": "application/json"};
const I = {
  home:'<path d="M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  games:'<rect x="2" y="6" width="20" height="12" rx="4"/><path d="M6 12h4M8 10v4M15 11h.01M18 13h.01"/>',
  tr:'<path d="m5 8 6 6M4 14l6-6 2-3M2 5h12M7 2h1M22 22l-5-10-5 10M14 18h6"/>',
  voice:'<path d="M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
  hist:'<path d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2"/>',
  keys:'<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  subs:'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M7 15h4M13 15h4M7 11h10"/>',
  lines:'<path d="M4 7h16M4 12h10M4 17h7"/>', ans:'<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  chat:'<path d="M4 4h16v12H7l-3 3z"/>',
  frame:'<path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3"/>',
  grid:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  mon:'<rect x="3" y="4" width="18" height="14" rx="2"/><path d="M8 21h8M12 18v3"/>',
  search:'<circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>', plus:'<path d="M12 5v14M5 12h14"/>',
  x:'<path d="M18 6 6 18M6 6l12 12"/>', play:'<path d="M7 4v16l13-8z"/>',
  dots:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
  eye:'<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><path d="M3 3l18 18"/>',
  font:'<path d="M4 7V5h16v2M9 20h6M12 5v15"/>', people:'<circle cx="9" cy="8" r="4"/><path d="M2 21c0-4 3-6 7-6s7 2 7 6M17 4a4 4 0 0 1 0 8M22 21c0-3-2-5-4-5.5"/>',
  info:'<circle cx="12" cy="12" r="9"/><path d="M12 16v-5M12 8h.01"/>', start:'<path d="M7 4v16l13-8z"/>',
  spark:'<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  db:'<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  book:'<path d="M4 19.5V5a2 2 0 0 1 2-2h14v16H6.5A2.5 2.5 0 0 0 4 21.5M8 7h8"/>',
  mute:'<path d="M11 5 6 9H2v6h4l5 4zM22 9l-6 6M16 9l6 6"/>',
  cloud:'<path d="M17.5 19H9a7 7 0 1 1 6.7-9h1.8a4.5 4.5 0 1 1 0 9z"/>',
  cpu:'<rect x="5" y="5" width="14" height="14" rx="2"/><path d="M9 1v4M15 1v4M9 19v4M15 19v4M1 9h4M1 15h4M19 9h4M19 15h4"/>',
  win:'<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18"/>',
  mix:'<circle cx="8" cy="9" r="3"/><circle cx="16" cy="9" r="3"/><path d="M2 20c0-3 3-5 6-5M22 20c0-3-3-5-6-5"/>',
  wave:'<path d="M2 12h2M6 8v8M10 5v14M14 8v8M18 10v4"/>', end:'<path d="M5 12h14M13 6l6 6-6 6"/>',
  ru:'<path d="M4 6h16M4 12h16M4 18h16"/>', folder:'<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  img:'<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5L5 20"/>',
  check:'<path d="M20 6 9 17l-5-5"/>', pin:'<path d="M12 17v5M9 3h6l-1 6 3 3H7l3-3z"/>'
};
const svg = (k, s = 17, w = 1.8) => `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0">${I[k] || ""}</svg>`;
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const $ = id => document.getElementById(id);
const sw = (on, attrs = "") => `<button class="sw" role="switch" aria-checked="${!!on}" ${attrs}><i></i></button>`;
const ico = (k, on = true) => `<span class="ico" style="${on ? "background:var(--acc);color:#fff" : ""}">${svg(k, 16, 2)}</span>`;
const lnk = (t, attrs) => `<a ${attrs} style="font-size:12px;white-space:nowrap">${t}</a>`;

async function act(name, arg) {
  let r = null;
  try { const x = await fetch("/api/action", {method: "POST", headers: H, body: JSON.stringify({name, arg})}); r = await x.json(); } catch (e) {}
  setTimeout(refresh, 150);
  return r || {};
}
async function get(url) { try { const r = await fetch(url, {headers: H}); return r.ok ? await r.json() : null; } catch (e) { return null; } }

// ---------- навигация ----------
const NAV = [["home","Главная"],["games","Игры"],["tr","Переводчики"],["voice","Озвучка"],["hist","История"],["keys","Клавиши"]];
let SCR = "home", SUB = {voice: "voice", game: null, histKind: "Все", histQ: "", charQ: "", charG: "all"};
function nav() {
  const cur = {win: "games", gloss: "tr", win_default: "tr"}[SCR] || SCR;
  $("nav").innerHTML = NAV.map(([id, t]) => `<button class="it" data-go="${id}" title="${t}" ${cur == id ? 'aria-current="page"' : ""}>${svg(id)}<span>${t}</span>${id == "games" ? '<span class="n" id="gcount"></span>' : ""}</button>`).join("");
  $("gear").style.background = SCR == "settings" ? "rgba(88,101,242,.16)" : "";
}
function go(s) { SCR = s; nav(); $("main").innerHTML = ""; $("main").dataset.last = "";
  $("ttl").textContent = ({home: "Главная", settings: "Настройки", win: "Вид перевода", gloss: "Словарь", win_default: "Вид для новых игр", start: "Начало работы"})[s] || (NAV.find(n => n[0] == s) || ["", ""])[1]; D = null; refresh(true); $("main").scrollTop = 0; }

// ---------- общие клики ----------
document.addEventListener("click", e => {
  const b = e.target.closest("[data-go],[data-act],[data-old],[data-report],[data-a]");
  if (!b) return;
  if (b.dataset.go) return go(b.dataset.go);
  if (b.dataset.report) return reportDlg();
  if (b.dataset.act) return act(b.dataset.act);
  if (b.dataset.old) return act("old", b.dataset.old);
  if (b.dataset.a) { const f = HANDLERS[b.dataset.a]; if (f) f(b, e); }
});
document.addEventListener("change", e => {
  const b = e.target.closest("[data-c]");
  if (b) { const f = HANDLERS[b.dataset.c]; if (f) f(b, e); }
});
document.addEventListener("input", e => {
  const b = e.target.closest("[data-i]");
  if (b) { const f = HANDLERS[b.dataset.i]; if (f) f(b, e); }
});
const HANDLERS = {};

// ---------- данные ----------
let S = null, D = null, busy = false;
function typing() { const a = document.activeElement; return a && /INPUT|TEXTAREA|SELECT/.test(a.tagName) && $("main").contains(a); }
async function refresh(force) {
  if (busy) return; busy = true;
  try {
    const s = await get("/api/state");
    if (s) { S = s; bootView(s.boot); if (s.wizard && !window._wzShown && SCR == "home") { window._wzShown = 1; setTimeout(() => go("start"), 0); } updNav(); $("ver").textContent = "v " + s.version; $("gear").title = document.body.classList.contains("nav-c") ? `Настройки · версия ${s.version}` : "Настройки"; const gc = $("gcount"); if (gc) gc.textContent = s.games.length || ""; }
    if (SCR != "home") D = await get("/api/screen?name=" + SCR);
    if ((force || !typing()) && !$("modal").classList.contains("on")) render();
  } finally { busy = false; }
}
function render() {
  const f = R[SCR]; if (!f || !S) return;
  const m = $("main"), y = m.scrollTop;
  let html = f();
  if (html == null) return;
  const TT = {home: "Главная"};
  const h = html.match(/<h1>([\s\S]*?)<\/h1>/);       // заголовок экрана — в верхнюю строку
  const title = h ? h[1] : (TT[SCR] || "");
  if (h) html = html.replace(h[0], "");
  if ($("ttl").innerHTML !== title) $("ttl").innerHTML = title;
  if (m.dataset.last !== html) { m.innerHTML = html; m.dataset.last = html; m.scrollTop = y; }
}
const R = {};

// ---------- главная ----------
R.home = () => {
  const s = S, cur = s.game, a = s.auto, M = s.modes, K = s.keys;
  const others = s.games.filter(x => !x.active).slice(0, 4);
  const card = (id, ic, t, d, on, key, toggle) => `<button class="mode${on ? " on" : ""}" data-a="mode" data-mode="${id}" role="switch" aria-checked="${on}">
    <div class="row"><span class="ico">${svg(ic, 16, 2)}</span><span style="flex-grow:1"></span>${toggle ? `<span class="sw" aria-checked="${on}"><i></i></span>` : ""}</div>
    <div style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:600">${t}</span><span style="font-size:12px;color:var(--m)">${d}</span></div>
    <div class="row" style="margin-top:auto"><span class="key">${esc(key)}</span></div></button>`;
  const lim = b => b ? `<div class="bar"><i style="width:${b.frac == null ? 0 : Math.round(b.frac * 100)}%"></i></div><span class="lbl" style="margin-top:4px;display:block">${esc(b.name)}: ${esc(b.text)}</span>` : "";
  const show = ["once","repeat","tooltip","once_tts","subs_once","answers_once","chat_once","chat_compose","layout","reset","panel","flip_gender","menu_learn","quit"];
  const ng = s.new_game ? `<div class="upd" style="display:flex"><span style="flex-grow:1">Новая игра: <b>${esc(s.new_game.name)}</b> — пресет создан сам. Обведите субтитры (${esc(K.select)}) — и можно переводить.</span><button class="btnp" style="padding:6px 14px" data-a="ngareas" data-id="${esc(s.new_game.id)}">Области</button><button class="btn" style="height:32px" data-a="ngno">Это не игра</button></div>` : "";
  return ng + `
  <div class="games"><div class="gnow"><span class="logo">${cur.free ? svg("mon", 26) : esc((cur.name || "?")[0])}</span><div style="display:flex;flex-direction:column;gap:2px;min-width:0">
    <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--m)"><span class="dot" style="background:${cur.running ? "var(--ok)" : "var(--f)"}"></span>${cur.free ? "В любом окне" : cur.running ? "Запущена" : cur.name ? "Не запущена" : "Ждёт игру"}</span>
    <span style="font-size:18px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(cur.name || "Игра не выбрана")}</span>
    ${cur.name ? `<a data-go="games" style="font-size:12px">Настройки игры</a>` : ""}</div></div>
    ${others.map(x => `<button class="gt" data-a="game" data-id="${esc(x.id)}" title="${esc(x.name)}" aria-label="${esc(x.name)}">${esc(x.name[0])}</button>`).join("")}
    ${cur.free ? "" : `<button class="gt tool" data-a="free" title="Переводить без игры: в любом окне, по пресету «Без игры» со своими областями">${svg("mon", 20)}Без игры</button>`}
    <button class="gt tool" data-go="games">${svg("grid", 20)}Все игры</button></div>
  <div class="card auto"><span class="dot" style="width:10px;height:10px;border-radius:5px;background:${!a.on ? "var(--f)" : a.paused ? "var(--warn)" : "var(--acc)"}"></span>
    <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1"><span class="ttl">Автоперевод</span><span class="sub">${esc(a.sub)}</span></div>
    <span class="key">${esc(K.auto)}</span><button class="btnp${a.on ? "" : " off"}" data-act="auto">${a.on ? "Выключить" : "Включить"}</button></div>
  <div class="two">
    <div class="card tc"><div class="row th">${ico("tr", true)}<span class="lbl" style="flex-grow:1">Переводчик</span></div><button class="vbtn" data-go="tr" aria-label="Сменить переводчика"><span>${esc(s.translator.chain.join(" → ") || "Нет ключей")}</span>${svg("end", 14, 2)}</button>${lim(s.limits[0])}</div>
    <div class="card tc"><div class="row th">${ico("spark", s.translator.editor_on)}<span class="lbl" style="flex-grow:1">ИИ-редактор</span>${sw(s.translator.editor_on, 'data-a="hedon" data-sm="1" title="Включить или выключить ИИ-редактор"')}</div>
      ${s.translator.editor_on ? `<button class="vbtn" data-a="eddlg" aria-label="Выбрать нейросеть редактора"><span>${esc((s.translator.editors.find(e => e.id == s.translator.editor_id) || {}).name || "Groq")}</span>${svg("end", 14, 2)}</button>` : `<span style="font-size:16px;color:var(--f);line-height:24px">Выключен</span>`}${s.translator.editor_on ? lim(s.limits[1]) : ""}</div>
    <div class="card tc"><div class="row th">${ico("voice", S.modes.tts.on)}<span class="lbl" style="flex-grow:1">Основной голос</span></div>
      <button class="vbtn" data-a="vdlg" aria-label="Выбрать основной голос"><span>${esc(((s.voice.list.find(v => v.id == s.voice.id) || {}).name || "По умолчанию").split(" — ")[0])}</span>${svg("end", 14, 2)}</button></div></div>
  <div class="grid3">
    ${card("select","subs","Субтитры",M.subs.ready ? "Основная область" : "Не обведена — нажмите",M.subs.ready,K.select,false)}
    ${card("select_subs2","lines","Реплики",M.subs2.ready ? "Вторая область" : "Не обведена — нажмите",M.subs2.ready,K.select_subs2,false)}
    ${card("answers","ans","Ответы",M.answers.ready ? "Переводятся сами" : "Сначала обведите: " + esc(K.select_answers),M.answers.on,K.select_answers,true)}
    ${card("chat","chat","Чат",M.chat.ready ? "Переводится сам" : "Область не задана",M.chat.on,K.select_chat,true)}
    ${card("toggle","frame","Окна поверх игры","Показать или спрятать",true,K.toggle,false)}
    ${card("tts","voice","Озвучка","Читать вслух",M.tts.on,K.tts,true)}</div>
  <div class="card" style="padding:12px 14px;display:flex;align-items:center;gap:12px">${ico("img")}
    <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1"><span style="font-weight:600">Показывать на трансляции</span><span style="font-size:12px;color:var(--m)">Зрители в Discord, OBS и на записи экрана видят переводы. Панель и журнал скрыты</span></div>
    ${sw(s.stream, 'data-a="stream"')}</div>
  <div style="height:.5px;background:var(--line)"></div>
  <div style="display:flex;flex-direction:column;gap:10px"><h2>Горячие клавиши</h2>
    <div class="hk">${show.filter(h => K[h]).map(h => { const d = s.key_desc[h] || ""; return `<div class="hkt"><span class="hkk">${esc(K[h])}</span><span class="hkd">${esc(d[0].toUpperCase() + d.slice(1))}</span></div>`; }).join("")}</div>
    <button class="btn" data-go="keys" style="padding:3px 16px">Изменить</button></div>`;
};
HANDLERS.ngareas = b => { SUB.game = b.dataset.id; act("new_dismiss"); go("games"); };
HANDLERS.ngno = () => act("new_not_game");
HANDLERS.hvoice = b => act("tts_voice", b.value);
HANDLERS.vdlg = () => voiceDlg();
HANDLERS.hedon = b => act("editor_on", b.getAttribute("aria-checked") != "true");
HANDLERS.eddlg = () => edDlg();
function edDlg() {
  const E = S.translator.editors, cur = S.translator.editor_id;
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">Кто редактирует</span><button class="ib" data-close="1">${svg("x", 16)}</button></div>
    <span style="font-size:13px;color:var(--t3)">Нейросеть доводит машинный перевод: падежи и род, имена по словарю, тон и «ты»/«вы». Работает поверх DeepL, Microsoft и Google.</span>
    <div style="display:flex;flex-direction:column;gap:2px;margin:0 -8px">${E.map(e => `<div class="r" style="padding:6px 8px;border-radius:8px;${e.id == cur ? "background:rgba(88,101,242,.16)" : ""}">
      <button class="gi" style="flex-grow:1;padding:2px 0;background:none" ${e.has ? `data-pe="${e.id}"` : "disabled"}><span style="display:flex;flex-direction:column;align-items:flex-start"><span style="font-weight:${e.id == cur ? 600 : 400};color:${e.has ? "var(--t)" : "var(--f)"}">${esc(e.name)}</span><span style="font-size:12px;color:var(--f)">${esc(e.desc)}</span></span></button>
      ${e.id == cur ? `<span style="color:var(--acc2);display:flex">${svg("check", 16, 2)}</span>` : e.has ? "" : `<a data-close="1" data-go="tr" style="font-size:12px;white-space:nowrap">добавить ключ</a>`}</div>`).join("")}</div>
    <div style="display:flex;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Готово</button></div>`);
  $("dlg").querySelectorAll("[data-pe]").forEach(b => b.onclick = async () => { await act("editor", b.dataset.pe); S.translator.editor_id = b.dataset.pe; edDlg(); });
}
function voiceDlg() {
  const L = S.voice.list, cur = S.voice.id;
  const groups = [["Женские", v => /женск/i.test(v.name)], ["Мужские", v => /мужск/i.test(v.name)], ["", v => !/женск|мужск/i.test(v.name)]];
  const item = v => { const [n, d0] = v.name.split(" — "); const d = d0 || "";
    const g = /женск/i.test(d) ? "f" : /мужск/i.test(d) ? "m" : "";
    const extra = /доп/i.test(d), rest = d.replace(/(женский|мужской)/i, "").replace(/\(доп\.?\)/i, "").replace(/^[,\s]+|[,\s]+$/g, "");
    const col = g == "f" ? "#d16ba5" : g == "m" ? "#5865F2" : "#4D4C48";
    return `<div class="r" style="padding:6px 8px;border-radius:8px;${v.id == cur ? "background:rgba(88,101,242,.16)" : ""}">
    <span class="av" style="background:${col}">${esc(n[0] || "?")}</span>
    <button class="gi" style="flex-grow:1;padding:2px 0;background:none" data-pickv="${esc(v.id)}"><span style="display:flex;flex-direction:column;align-items:flex-start"><span style="font-weight:${v.id == cur ? 600 : 400}">${esc(n)}</span>${rest || extra ? `<span style="font-size:12px;color:var(--f)">${esc(rest || "")}${extra ? (rest ? " · " : "") + "дополнительный, офлайн" : ""}</span>` : ""}</span></button>
    ${g ? `<span style="font-size:11px;padding:2px 8px;border-radius:6px;background:${col}26;color:${g == "f" ? "#f0a6cf" : "#aab2ff"}">${g == "f" ? "женский" : "мужской"}</span>` : ""}
    <span style="width:20px;display:flex;justify-content:center;color:var(--acc2)">${v.id == cur ? svg("check", 16, 2) : ""}</span>
    <button class="ib" style="color:var(--acc2)" title="Прослушать" data-prev="${esc(v.id)}">${svg("play", 14)}</button></div>`; };
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">Основной голос</span><button class="ib" data-close="1">${svg("x", 16)}</button></div>
    <span style="font-size:13px;color:var(--t3)">Им читаются реплики без имени говорящего${S && S.modes ? "" : ""}. Нажмите ▶, чтобы послушать.</span>
    <div style="display:flex;flex-direction:column;gap:2px;max-height:420px;overflow-y:auto;margin:0 -8px">${L.length ? groups.map(([t, f]) => { const g = L.filter(f); return g.length ? (t ? `<div class="sec" style="padding:8px 8px 4px">${t}</div>` : "") + g.map(item).join("") : ""; }).join("") : '<div class="empty">Загружаю список голосов…</div>'}</div>
    <div style="display:flex;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Готово</button></div>`);
  $("dlg").querySelectorAll("[data-pickv]").forEach(b => b.onclick = async () => { await act("tts_voice", b.dataset.pickv); S.voice.id = b.dataset.pickv; voiceDlg(); });
  $("dlg").querySelectorAll("[data-prev]").forEach(b => b.onclick = () => act("voice_preview", b.dataset.prev));
}
HANDLERS.mode = b => { const m = b.dataset.mode, on = b.getAttribute("aria-checked") != "true"; (m == "answers" || m == "chat") ? act(m, on) : act(m); };
HANDLERS.game = b => act("game", b.dataset.id);
HANDLERS.free = () => act("free");
HANDLERS.stream = b => act("stream", b.getAttribute("aria-checked") != "true");

// ---------- игры ----------
R.games = () => {
  if (!D) return null;
  const G = D.games, sel = G.find(g => g.id == SUB.game) || G.find(g => g.active) || G.find(g => !g.free) || G[0];
  if (sel) SUB.game = sel.id;
  const item = g => `<button class="gi" data-a="gpick" data-id="${esc(g.id)}" ${sel && g.id == sel.id ? 'aria-current="true"' : ""}>
    <span class="lg" style="${g.free ? "background:#30302E" : ""}">${g.free ? svg("mon", 18) : esc(g.name[0])}</span>
    <span style="display:flex;flex-direction:column;min-width:0;gap:1px"><span style="font-weight:${sel && g.id == sel.id ? 600 : 500};white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${esc(g.name)}</span>
    ${g.free ? `<span style="font-size:12px;color:var(--f)">В любом окне</span>` : g.running ? `<span style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--m)"><span class="dot" style="width:7px;height:7px;background:var(--ok)"></span>Запущена</span>` : !g.configured ? `<span style="font-size:12px;color:var(--warn)">Не настроена</span>` : ""}</span></button>`;
  const free = G.filter(g => g.free), games = G.filter(g => !g.free);
  const list = `<div class="gl"><label style="display:flex;align-items:center;gap:8px;height:34px;padding:0 10px;border-radius:8px;background:var(--card);color:var(--f)">${svg("search", 15)}<input class="inp" style="background:none;padding:0;height:auto" placeholder="Поиск игры" data-i="gq" value="${esc(SUB.gq || "")}"></label>
    <div style="display:flex;flex-direction:column;gap:2px">${free.map(item).join("")}${free.length ? '<div style="height:.5px;background:var(--line);margin:4px 6px"></div>' : ""}
    ${games.filter(g => !SUB.gq || g.name.toLowerCase().includes(SUB.gq.toLowerCase())).map(item).join("") || '<div class="empty">Игр пока нет. Запустите игру — программа заведёт её сама.</div>'}</div>
    <button class="btn" data-a="gadd" style="height:32px;display:flex;align-items:center;justify-content:center;gap:6px">${svg("plus", 14)}Добавить игру</button>
    ${D.not_games.length ? `<div style="font-size:12px;color:var(--m);padding-top:8px">Не игры — программа их не трогает:</div><div style="display:flex;flex-wrap:wrap;gap:6px">${D.not_games.map(x => `<span class="chip" style="height:26px;font-size:12px">${esc(x)}<a data-a="unng" data-v="${esc(x)}" title="Вернуть" style="color:var(--f)">${svg("x", 12)}</a></span>`).join("")}</div>` : ""}</div>`;
  if (!sel) return `<h1>Игры</h1><div style="display:flex;gap:16px;align-items:flex-start">${list}</div>`;
  const g = sel, activeHere = g.active, K = D.keys;
  const regRow = r => `<div class="r"><span style="width:30px;display:flex;justify-content:center"><span class="sq" style="${r.has ? "background:" + ({region:"#5865F2",region2:"#949cf7",answers_region:"#23a55a",chat_region:"#f0b232"}[r.key]) : "border:1.5px dashed var(--f)"}"></span></span>
    <span class="tx"><span>${r.title}</span><span class="d">${r.has ? esc(r.size) : "Не обведена"}</span></span>
    ${r.has && activeHere ? `<a data-a="aclear" data-k="${r.key}" title="Удалить область" style="color:var(--f)">${svg("x", 14)}</a>` : ""}
    <button class="${r.has ? "btn" : "btnp"}" style="${r.has ? "" : "padding:4px 12px;font-size:12px;border-radius:6px"}" data-a="adraw" data-k="${r.key}">${r.has ? "Перерисовать" : "Обвести"}</button></div>`;
  const n = g.regions.filter(r => r.has).length;
  const detail = `<div style="flex-grow:1;min-width:0;display:flex;flex-direction:column;gap:8px">
    <div class="card" style="padding:14px;display:flex;align-items:center;gap:14px;background:rgba(88,101,242,.12)">
      <span class="logo" style="width:72px;height:72px;border-radius:12px">${g.free ? svg("mon", 28) : esc(g.name[0])}</span>
      <div style="display:flex;flex-direction:column;gap:2px;flex-grow:1;min-width:0">
        <span style="display:flex;align-items:center;gap:6px;font-size:12px;color:var(--m)"><span class="dot" style="background:${g.running ? "var(--ok)" : "var(--f)"}"></span>${g.free ? "В любом окне" : g.running ? "Запущена" : "Не запущена"}${g.locked ? " · закреплена" : ""}${activeHere && !g.running && !g.free ? " · настраиваете" : ""}</span>
        ${g.free ? `<span style="font-size:20px;font-weight:600">${esc(g.name)}</span>` : `<input class="inp" style="font-size:20px;font-weight:600;background:none;padding:0;height:30px" value="${esc(g.name)}" data-c="grename" aria-label="Название игры">`}
        ${g.exes.length ? `<span style="display:flex;flex-wrap:wrap;gap:6px;font-size:12px;color:var(--f)">${g.exes.map(x => `<span>${esc(x)}${g.exes.length > 1 ? ` <a data-a="gexrm" data-exe="${esc(x)}" style="color:var(--f)">×</a>` : ""}</span>`).join(" · ")} · <a data-a="gexadd" style="font-size:12px">ещё файл</a></span>` : ""}</div>
      ${g.free ? "" : `<div style="display:flex;flex-direction:column;gap:6px;align-self:flex-start;align-items:flex-end">
        <button class="btn" data-a="glock">${g.locked ? "Открепить" : "Закрепить"}</button><button class="btnd" data-a="gdel">Удалить</button></div>`}</div>
    ${activeHere ? "" : `<div class="card" style="padding:12px 14px;display:flex;align-items:center;gap:12px"><span style="flex-grow:1;font-size:13px;color:var(--t3)">Сейчас выбрана другая игра. Чтобы обвести области этой, переключитесь на неё.</span><button class="btnp" style="padding:6px 14px" data-a="gsel">Настроить эту</button></div>`}
    <div class="card" style="padding:14px;display:flex;flex-direction:column;gap:10px">
      <div class="hdr">${ico("frame")}<span style="display:flex;flex-direction:column;flex-grow:1"><span style="font-weight:600">Области</span><span class="d" style="font-size:12px;color:var(--m)">Где читать текст · ${n} из ${g.regions.length} обведены</span></span></div>
      <div class="lst">${g.regions.map(regRow).join("")}</div>
      <button class="btn" data-act="layout" title="Двигать области и окна перевода прямо поверх игры" style="padding:3px 16px">Расставить на экране</button></div>
    <div class="card" style="padding:14px;display:flex;flex-direction:column;gap:10px">
      <div class="hdr">${ico("eye", g.menu)}<span style="display:flex;flex-direction:column;flex-grow:1"><span style="font-weight:600">Экраны без перевода</span><span style="font-size:12px;color:var(--m)">На них автоперевод встаёт на паузу</span></span></div>
      <div class="lst">${g.menu ? `<div class="r"><span class="thumb" style="${g.menu_thumb ? `background:#000 url(${g.menu_thumb}) center/contain no-repeat` : ""}"></span><span class="tx"><span>Меню игры</span><span class="d">пока оно на экране — перевод и озвучка на паузе</span></span><button class="btn" data-a="scrnew">Заменить</button><button class="ib" title="Забыть" data-a="scrdel">${svg("x", 14)}</button></div>` : `<div class="empty">Пока нет.</div>`}</div>
      ${g.menu ? "" : `<button class="btn" style="height:32px;display:flex;align-items:center;justify-content:center;gap:6px" data-a="scrnew">${svg("plus", 13)}Запомнить экран</button>`}</div>
    <div class="grid3" style="grid-template-columns:1fr 1fr">
      <div class="card tc" style="gap:10px"><div class="hdr">${ico("font")}<span style="flex-grow:1"></span>${lnk("изменить", 'data-go="win"')}</div><div><div style="font-weight:600">Вид перевода</div><div style="font-size:12px;color:var(--m)">Шрифт, размер, фон</div></div></div>
      <div class="card tc" style="gap:10px"><div class="hdr">${ico("people")}<span style="flex-grow:1"></span>${lnk("открыть", 'data-a="gochars"')}</div><div><div style="font-weight:600">Имена и голоса</div><div style="font-size:12px;color:var(--m)">${g.chars} персонажей · ${g.gloss} в словаре</div></div></div></div>
    ${g.free ? "" : `<div class="card" style="padding:14px;display:flex;flex-direction:column;gap:8px">
      <div class="hdr">${ico("info")}<span style="display:flex;flex-direction:column;flex-grow:1"><span style="font-weight:600">Об игре</span><span style="font-size:12px;color:var(--m)">Помогает ИИ переводить точнее</span></span>${g.facts_ok ? lnk(g.facts_busy ? "собираю…" : (g.about ? "собрать заново" : "собрать"), 'data-a="gfacts"') : ""}</div>
      <span style="font-size:13px;color:var(--t3);line-height:1.5">${esc(g.about) || "Пока пусто."}</span></div>
    <div class="card" style="padding:14px;display:flex;align-items:center;gap:10px">${ico("start", g.auto_start)}<span style="display:flex;flex-direction:column;flex-grow:1"><span style="font-weight:600">Включать автоперевод при запуске</span><span style="font-size:12px;color:var(--m)">Когда эта игра открывается</span></span>${sw(g.auto_start, 'data-a="gauto"')}</div>`}</div>`;
  return `<h1>Игры</h1><div style="display:flex;gap:16px;align-items:flex-start">${list}${detail}</div>`;
};
HANDLERS.scrnew = () => modal(`<h3 style="font-size:16px">Запомнить экран без перевода</h3>
  <ol style="font-size:13px;color:var(--m);line-height:1.7;padding-left:18px;margin:10px 0">
    <li>Перейдите в игру и откройте экран, где переводить не нужно — меню, карту, инвентарь.</li>
    <li>Нажмите <span class="key">${esc(S.keys ? S.keys.menu_learn || "Ctrl+Shift+M" : "Ctrl+Shift+M")}</span> прямо в игре.</li>
    <li>Обведите мышкой кусочек, который на этом экране всегда одинаковый: заголовок или строку вкладок.</li></ol>
  <span style="font-size:12px;color:var(--f)">Сейчас запоминается один экран на игру — новый заменит прежний.</span>
  <div class="row" style="justify-content:flex-end;margin-top:14px"><button class="btnp" style="padding:6px 16px" onclick="closeModal()">Понятно</button></div>`);
HANDLERS.scrdel = () => confirmDlg("Забыть экран?", "Автоперевод больше не будет вставать на паузу на этом экране.", "Забыть", () => act("menu_forget"));
HANDLERS.gpick = b => { SUB.game = b.dataset.id; render(); };
HANDLERS.gq = b => { SUB.gq = b.value; render(); const i = document.querySelector('[data-i="gq"]'); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } };
HANDLERS.gadd = () => pickDlg("Добавить игру", "Выберите игру из запущенных сейчас программ. Название потом можно исправить.", exe => act("pick_game", exe), true);
HANDLERS.gsel = () => act("game_select", {id: SUB.game});
HANDLERS.grename = b => act("game_rename", {id: SUB.game, name: b.value});
HANDLERS.gexadd = () => { const id = SUB.game; pickDlg("Ещё файл для игры", "Пригодится, если игра запускается через лаунчер или файл переименовали после обновления.", exe => act("pick_exe", {id, v: exe}), false); };
HANDLERS.gexrm = b => act("game_remove_exe", {id: SUB.game, exe: b.dataset.exe});
HANDLERS.glock = () => { const g = D.games.find(x => x.id == SUB.game); act("game_lock", {id: g && g.locked ? null : SUB.game}); };
HANDLERS.gdel = () => { const g = D.games.find(x => x.id == SUB.game); confirmDlg(`Удалить «${g.name}»?`, "Пропадут её области; словарь, персонажи и кэш уйдут в папку backups. Сама игра не затронута.", "Удалить", () => { act("game_delete", {id: SUB.game}); SUB.game = null; }); };
HANDLERS.gauto = b => act("game_auto_start", {id: SUB.game, v: b.getAttribute("aria-checked") != "true"});
HANDLERS.gfacts = () => act("game_facts", {id: SUB.game});
HANDLERS.adraw = b => act("area_draw", {id: SUB.game, key: b.dataset.k});
HANDLERS.aclear = b => act("area_clear", {id: SUB.game, key: b.dataset.k});
HANDLERS.unng = b => act("unmark_not_game", b.dataset.v);
HANDLERS.gochars = () => { SUB.voice = "chars"; go("voice"); };

// ---------- переводчики ----------
R.tr = () => {
  if (!D) return null;
  const P = D.providers, name = id => (P.find(p => p.id == id) || {name: id}).name;
  const opts = (cur, skip) => P.filter(p => !skip.includes(p.id)).map(p => `<option value="${p.id}" ${p.id == cur ? "selected" : ""}>${esc(p.name)}${p.need_key && !p.has ? " (нет ключа)" : ""}</option>`).join("");
  const fb = D.fallback.map((f, i) => `<span class="chip" style="height:36px;background:var(--side)"><span class="c">${i + 1}</span>${esc(name(f))}<a data-a="fbrm" data-v="${f}" title="Убрать из запасных" style="color:var(--f)">${svg("x", 13)}</a></span>`).join("");
  const left = P.filter(p => p.id != D.main && !D.fallback.includes(p.id));
  const row = p => `<div class="r"><span class="av" style="border-radius:9px;background:#30302E;color:var(--t3)">${p.name.slice(0, p.name.length > 5 ? 2 : 1)}</span>
    <span class="tx"><span style="font-weight:500;color:${p.need_key && !p.has ? "var(--f)" : "var(--t)"}">${esc(p.name)}</span><span class="d">${esc(p.desc)}</span>
    ${p.frac != null ? `<div style="display:flex;align-items:center;gap:8px;margin-top:6px;max-width:340px"><div class="bar" style="flex-grow:1;margin:0"><i style="width:${Math.round(p.frac * 100)}%"></i></div><span class="d" style="white-space:nowrap">${esc(p.limit)}</span></div>` : ""}</span>
    ${!p.need_key ? `<span class="d">без ключа и лимитов</span>` : p.has ? `<span class="d">ключ ${esc(p.masked)}</span>${lnk("изменить", `data-a="key" data-id="${p.id}"`)}` : p.can_key ? lnk("добавить ключ", `data-a="key" data-id="${p.id}"`) : ""}</div>`;
  const flag = (k, ic, t, d, foot, footA) => { const on = D.flags[k]; return `<div class="mode${on ? " on" : ""}" style="cursor:default">
    <div class="row">${ico(ic, on)}<span style="flex-grow:1"></span>${sw(on, `data-a="flag" data-n="${k}"`)}</div>
    <div style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:600">${t}</span><span style="font-size:12px;color:var(--m)">${d}</span></div>
    ${foot ? `<div class="row" style="margin-top:auto;font-size:12px;color:var(--m)"><span style="flex-grow:1">${foot}</span>${footA || ""}</div>` : ""}</div>`; };
  const ed = D.editors, st = D.editor_stats;
  return `<div style="display:flex;flex-direction:column;gap:4px"><h1>Переводчики</h1><span class="subt">Кто переводит текст. Если основной упрётся в лимит, сразу подхватит запасной.</span></div>
  <div class="card" style="padding:14px;display:grid;grid-template-columns:220px minmax(0,1fr);gap:14px">
    <div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Основной</span><select class="sel" data-c="pmain">${opts(D.main, [])}</select></div>
    <div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Запасные — по порядку, если основной упрётся в лимит</span>
      <div style="display:flex;gap:6px;flex-wrap:wrap">${fb}${left.length ? `<select class="sel" style="width:auto;height:36px" data-c="fbadd"><option value="">+ Добавить</option>${left.map(p => `<option value="${p.id}">${esc(p.name)}</option>`).join("")}</select>` : ""}</div></div></div>
  <div class="card" style="padding:14px;display:flex;gap:12px;align-items:flex-start;${D.editor_on ? "background:rgba(88,101,242,.10)" : ""}">
    <span style="flex-shrink:0;display:flex">${ico("spark", D.editor_on)}</span>
    <div style="display:flex;flex-direction:column;gap:12px;flex-grow:1;min-width:0">
      <div class="row" style="gap:12px;align-items:flex-start"><div style="display:flex;flex-direction:column;gap:3px;flex-grow:1"><span style="font-weight:600">ИИ-редактор</span><span style="font-size:12px;color:var(--m);line-height:1.5">Проверяет перевод любого переводчика: род говорящего, падежи, имена по словарю, «ты»/«вы». Готовит реплику для озвучки: ударения, цифры словами, интонация. Не успел — покажет обычный перевод.</span></div>${sw(D.editor_on, 'data-a="edon"')}</div>
      ${D.editor_on ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
        <label style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Кто редактирует</span><select class="sel" data-c="ed">${ed.map(e => `<option value="${e.id}" ${e.id == D.editor ? "selected" : ""} ${e.has ? "" : "disabled"}>${esc(e.name)}${e.has ? "" : " — нужен ключ"}</option>`).join("")}</select></label>
        <label style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Запасной — на случай лимита</span><select class="sel" data-c="ed2"><option value="">Нет</option>${ed.filter(e => e.id != D.editor).map(e => `<option value="${e.id}" ${e.id == D.editor2 ? "selected" : ""} ${e.has ? "" : "disabled"}>${esc(e.name)}${e.has ? "" : " — нужен ключ"}</option>`).join("")}</select></label></div>
      <div class="row" style="gap:12px"><span style="display:flex;flex-direction:column;gap:2px;flex-grow:1"><span style="font-size:13px">Смотреть на экран игры</span><span style="font-size:12px;color:var(--m)">Раз в несколько реплик редактор видит скриншот — точнее понимает, кто говорит и какого он пола</span></span>${sw(D.ed_shot, 'data-a="flag" data-n="ed_shot"')}</div>
      <span style="font-size:12px;color:var(--f)">Поправил: ${st.edited} · без правок: ${st.same} · не успел: ${st.late}${st.voice_up ? " · озвучка дочитала его вариантом: " + st.voice_up : ""}${st.skipped ? " · короткие без проверки: " + st.skipped : ""}${st.failed ? " · ошибок: " + st.failed : ""}</span>
      ${D.bad.length ? `<details><summary style="cursor:pointer;font-size:13px;color:var(--m)">Отмечено «плохой перевод» (Ctrl+Shift+B): ${D.bad.length} — редактор учитывает последние 4</summary>
        <div class="lst" style="margin-top:6px">${D.bad.map((x, i) => `<div class="row" style="padding:6px 0;gap:10px;align-items:flex-start"><div style="flex-grow:1;display:flex;flex-direction:column;gap:2px;min-width:0"><span style="font-size:13px">${esc(x.ru)}</span><span style="font-size:12px;color:var(--f)">${esc(x.en)}</span></div><button class="ib" title="Удалить" data-a="badd" data-i="${i}">${svg("x", 14)}</button></div>`).reverse().join("")}</div>
        <button class="btn" style="margin-top:6px" data-a="badc">Очистить все</button></details>` : ""}` : ""}
    </div></div>
  <div class="card" style="padding:14px 18px"><div style="display:flex;align-items:baseline;gap:10px"><span style="font-weight:600;font-size:15px;flex-grow:1">Все переводчики</span><span style="font-size:12px;color:var(--f)">ключи хранятся в Windows, не в файлах программы</span></div>
    <div class="sec">Машинный перевод <span style="font-weight:400;color:var(--f)">быстро, без понимания сцены</span></div><div class="lst">${P.filter(p => p.group == "mt").map(row).join("")}</div>
    <div class="sec">Нейросети <span style="font-weight:400;color:var(--f)">понимают сцену и прошлые реплики</span></div><div class="lst">${P.filter(p => p.group == "ai").map(row).join("")}</div>
    ${P.some(p => p.own) ? `<div class="sec">Свои</div><div class="lst">${P.filter(p => p.own).map(p => `<div class="r"><span class="av" style="border-radius:9px;background:#30302E;color:var(--t3)">${esc(p.name.slice(0, 2))}</span>
      <span class="tx"><span style="font-weight:500;color:${p.has ? "var(--t)" : "var(--f)"}">${esc(p.name)}</span><span class="d">${esc(p.model)} · ${esc(p.url)}</span></span>
      <span class="d">${p.local ? "на этом ПК" : p.has ? "ключ " + esc(p.masked) : "нет ключа"}</span>${lnk("изменить", `data-a="own" data-id="${p.id}"`)}</div>`).join("")}</div>` : ""}
    <button class="btn" style="height:34px;margin-top:12px;width:100%;display:flex;align-items:center;justify-content:center;gap:6px" data-a="own">${svg("plus", 13)}Свой переводчик</button></div>
  <h2 style="font-size:15px;padding-top:6px">Как переводить</h2>
  <div class="grid3" style="grid-template-columns:1fr 1fr">
    ${flag("cache","db","Кэш переводов","Повторы — мгновенно и без запросов",`${D.cache_size} фраз`,lnk("очистить",'data-a="cclear"'))}
    ${flag("gloss_auto","book","Пополнять словарь","Имена, предметы и места из переводов",`${D.gloss_count} записей`,lnk("открыть",'data-go="gloss"'))}
    ${flag("save_history","hist","История в файл","По файлу на каждый день","папка history",lnk("открыть",'data-a="hfolder"'))}
    ${flag("skip_system","mute","Пропускать системные","Сообщения игры не переводить и не озвучивать")}
</div>
  <h2 style="font-size:15px;padding-top:6px">Вид для новых игр</h2>
  <span class="subt" style="margin-top:-10px">Его получает каждая новая игра и режим «Без игры». У игры, которой вы уже настроили вид, он свой — меняется в «Играх».</span>
  ${styleBlock(D.ds, true)}${extrasCard(D.ds, true)}`;
};
HANDLERS.pmain = b => act("provider_main", b.value);
HANDLERS.fbadd = b => { if (b.value) act("provider_fallbacks", D.fallback.concat([b.value])); };
HANDLERS.fbrm = b => act("provider_fallbacks", D.fallback.filter(f => f != b.dataset.v));
HANDLERS.edon = b => act("editor_on", b.getAttribute("aria-checked") != "true");
HANDLERS.ed = b => act("editor", b.value);
HANDLERS.strs = b => act("stress_set", {k: b.dataset.k, v: b.value});
HANDLERS.strp = b => act("stress_play", {v: b.dataset.v});
HANDLERS.strd = b => act("stress_del", {k: b.dataset.k});
HANDLERS.badd = b => act("bad_del", {i: +b.dataset.i});
HANDLERS.badc = () => act("bad_clear");
HANDLERS.ed2 = b => act("editor2", b.value);
HANDLERS.flag = b => act("flag", {name: b.dataset.n, v: b.getAttribute("aria-checked") != "true"});
HANDLERS.cclear = () => confirmDlg("Очистить кэш переводов?", "Готовые переводы фраз забудутся — следующие повторы снова пойдут к переводчику.", "Очистить", () => act("cache_clear"));
HANDLERS.hfolder = () => act("hist_folder");
HANDLERS.key = b => keyDlg(b.dataset.id);
HANDLERS.own = b => ownDlg(b.dataset.id);
function ownDlg(id) {
  const p = id ? D.providers.find(x => x.id == id) : null;
  const PRE = [["OpenRouter","https://openrouter.ai/api/v1","deepseek/deepseek-chat-v3-0324:free"],["DeepSeek","https://api.deepseek.com/v1","deepseek-chat"],["LM Studio","http://localhost:1234/v1",""],["Ollama","http://localhost:11434/v1","qwen2.5:7b"]];
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">${p ? "Изменить «" + esc(p.name) + "»" : "Свой переводчик"}</span><button class="ib" data-close="1">${svg("x", 16)}</button></div>
    <span style="font-size:13px;color:var(--t3)">Любая нейросеть с адресом, совместимым с OpenAI. Текст читается на ПК, нейросеть получает только текст.</span>
    ${p ? "" : `<div style="display:flex;gap:6px;flex-wrap:wrap">${PRE.map((x, i) => `<button class="chip" data-pre="${i}">${x[0]}</button>`).join("")}</div>`}
    ${[["on","Название","DeepSeek",p ? p.name : ""],["ou","Адрес","https://api.deepseek.com/v1",p ? p.url : ""],["om","Модель","deepseek-chat",p ? p.model : ""]].map(([i, t, ph, v]) => `<label style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${t}</span><input class="inp" id="${i}" placeholder="${ph}" value="${esc(v)}"></label>`).join("")}
    <label style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Ключ ${p && p.has && !p.local ? "(сохранён " + esc(p.masked) + " — оставьте пустым, чтобы не менять)" : "(для программ на этом ПК не нужен)"}</span><input class="inp" id="ok" type="password" autocomplete="off" placeholder="Вставьте ключ"></label>
    <span id="ores" style="font-size:13px;min-height:18px"></span>
    <div style="display:flex;gap:8px">${p ? `<button class="btnd" id="odel">Удалить</button>` : ""}<span style="flex-grow:1"></span><button class="btn" style="height:36px;padding:0 16px;font-size:13px" id="otest">Проверить</button><button class="btnp" id="osave">Сохранить</button></div>`);
  const val = () => ({id: id || null, name: $("on").value, url: $("ou").value, model: $("om").value, key: $("ok").value});
  $("dlg").querySelectorAll("[data-pre]").forEach(b => b.onclick = () => { const x = PRE[+b.dataset.pre]; $("on").value = x[0]; $("ou").value = x[1]; $("om").value = x[2]; $("om").focus(); });
  $("otest").onclick = async () => { $("ores").style.color = "var(--m)"; $("ores").textContent = "Проверяю…"; const r = (await act("custom_test", val())).data || {};
    $("ores").style.color = r.ok ? "var(--ok)" : "var(--err)"; $("ores").textContent = (r.ok ? "✓ Работает: " : "✗ ") + (r.text || ""); };
  $("osave").onclick = async () => { const r = (await act("custom_save", val())).data || {};
    if (r.error) { $("ores").style.color = "var(--err)"; $("ores").textContent = r.error; return; } closeModal(); };
  if ($("odel")) $("odel").onclick = () => { closeModal(); confirmDlg(`Удалить «${p.name}»?`, "Переводчик пропадёт из списка, его ключ удалится из Windows. Если он был основным или запасным — его место займёт Google.", "Удалить", () => act("custom_remove", {id})); };
}

// ---------- озвучка ----------
R.voice = () => {
  if (!D) return null;
  const tabs = `<div class="tabs" role="tablist"><button data-a="vtab" data-v="voice" ${SUB.voice == "voice" ? 'aria-current="page"' : ""}>Голос</button><button data-a="vtab" data-v="chars" ${SUB.voice == "chars" ? 'aria-current="page"' : ""}>Персонажи <span style="font-size:12px;color:var(--f)">${D.chars.length}</span></button></div>`;
  return `<h1>Озвучка</h1>${tabs}<div style="height:4px"></div>` + (SUB.voice == "chars" ? chars() : voiceTab());
};
function voiceTab() {
  const F = D.flags;
  const eng = (id, ic, t, d) => `<button class="eng" role="radio" aria-checked="${D.engine == id}" data-a="veng" data-v="${id}">${ico(ic, D.engine == id)}<div style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:600">${t}</span><span style="font-size:12px;color:var(--m)">${d}</span></div></button>`;
  const fl = (k, ic, t, d, foot) => { const on = F[k]; return `<div class="mode${on ? " on" : ""}" style="cursor:default"><div class="row">${ico(ic, on)}<span style="flex-grow:1"></span>${sw(on, `data-a="flag" data-n="${k}"`)}</div>
    <div style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:600">${t}</span><span style="font-size:12px;color:var(--m)">${d}</span></div>${foot || ""}</div>`; };
  const rate = D.rate, rt = rate == 0 ? "обычная" : (rate > 0 ? "+" : "") + rate;
  const vp = D.engine == "silero" && !D.silero_installed;
  return `<div class="card" style="padding:14px;display:flex;align-items:center;gap:12px;${D.on ? "background:rgba(88,101,242,.10)" : ""}">${ico("voice", D.on)}<div style="display:flex;flex-direction:column;gap:2px;flex-grow:1"><span style="font-weight:600">Озвучивать перевод субтитров</span><span style="font-size:12px;color:var(--m)">Читать вслух каждую новую реплику</span></div><span class="key">${esc(D.key)}</span>${sw(D.on, 'data-a="von"')}</div>
  <h2 style="font-size:15px;padding-top:6px">Чем озвучивать</h2>
  <div class="grid3">${eng("neural","cloud","Нейроголоса Microsoft","Звучат живее всего. Нужен интернет")}${eng("silero","cpu","Silero","Без интернета, на вашем ПК")}${eng("windows","win","Голос Windows","Встроенный, самый простой")}</div>
  ${vp ? `<div class="card" style="padding:12px 14px;display:flex;align-items:center;gap:12px"><span style="flex-grow:1;font-size:13px;color:var(--t3)">${D.voicepack.busy ? `Устанавливаю офлайн-голоса: ${esc(D.voicepack.progress || "…")}` : `Офлайн-голоса ещё не установлены${D.frozen ? " (около 250 МБ, один раз)" : ""}. Пока читает голос Windows.`}</span><button class="btnp" style="padding:6px 14px;white-space:nowrap;flex-shrink:0" data-a="vpack" ${D.voicepack.busy ? "disabled" : ""}>${D.voicepack.busy ? "Устанавливаю…" : "Установить"}</button></div>` : ""}
  <div class="card" style="padding:14px;display:grid;grid-template-columns:1fr 1fr;gap:16px 20px">
    <div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Основной голос</span><select class="sel" data-c="vvoice">${D.voices.map(v => `<option value="${esc(v.id)}" ${v.id == D.voice ? "selected" : ""}>${esc(v.name)}</option>`).join("") || "<option>загружаю…</option>"}</select><span style="font-size:12px;color:var(--f)">${D.mode == "one" ? "Им читаются все реплики" : "Для реплик без имени говорящего"}</span></div>
    <div style="display:flex;flex-direction:column;gap:14px">
      <label style="display:flex;flex-direction:column;gap:4px"><span class="row"><span class="lbl" style="flex-grow:1">Скорость</span><span style="font-size:12px">${rt}</span></span><input type="range" min="-5" max="6" step="1" value="${rate}" data-c="vrate"></label>
      <label style="display:flex;flex-direction:column;gap:4px"><span class="row"><span class="lbl" style="flex-grow:1">Громкость</span><span style="font-size:12px">${D.volume}%</span></span><input type="range" min="10" max="100" step="5" value="${D.volume}" data-c="vvol"></label></div>
    <div style="grid-column:1/-1;border-top:.5px solid var(--line);padding-top:14px;display:flex;align-items:center;gap:14px"><div style="display:flex;flex-direction:column;gap:4px;flex-grow:1"><span class="lbl">Проверить на фразе</span><input class="inp" style="background:none;padding:0;height:24px;font-size:14px" id="vtest" value="${esc(SUB.vtest || "Реналь: Держись рядом! Ты слышал это?..")}" data-i="vtesti"></div><button class="btnp" style="display:flex;align-items:center;gap:8px" data-a="vplay">${svg("play", 13)}Прослушать</button></div></div>
  <h2 style="font-size:15px;padding-top:6px">Кто каким голосом</h2>
  <div class="card" style="padding:14px;display:flex;flex-direction:column;gap:14px">
    <div class="grid3">${[["one","mon","Один голос для всех","Все реплики — основным голосом"],["gender","people","По полу","Мужчинам мужской голос, женщинам женский"],["each","mix","Каждому свой","У каждого персонажа свой голос, мужской или женский"]].map(([id, ic, t, d]) => `<button class="eng" role="radio" aria-checked="${D.mode == id}" data-a="vmode" data-v="${id}">${ico(ic, D.mode == id)}<div style="display:flex;flex-direction:column;gap:2px"><span style="font-weight:600">${t}</span><span style="font-size:12px;color:var(--m)">${d}</span></div></button>`).join("")}</div>
    ${D.engine == "windows" && D.mode != "one" ? `<span style="font-size:12px;color:var(--warn)">С голосом Windows разные голоса не работают — выберите нейроголоса или Silero.</span>` : ""}
    ${D.mode == "gender" && D.engine != "windows" ? `<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px 20px">${[["m","Мужской голос"],["f","Женский голос"]].map(([g, t]) => `<div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${t}</span><div class="row" style="gap:6px"><select class="sel" data-c="gvoice" data-g="${g}">${D.gender_pool[g].map(v => `<option value="${esc(v.id)}" ${v.id == D.gender_voice[g] ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select><button class="ib" style="color:var(--acc2);flex-shrink:0" title="Прослушать" data-a="gtest" data-g="${g}">${svg("play", 14)}</button></div></div>`).join("")}</div>` : ""}
    ${D.mode == "each" ? `<div class="row" style="font-size:12px;color:var(--m)"><span style="flex-grow:1">Голос подбирается сам по полу. Поменять пол или голос конкретному персонажу — во вкладке «Персонажи» (${D.chars.length}).</span>${lnk("открыть",'data-a="vtab" data-v="chars"')}</div>` : ""}
  </div>
  <h2 style="font-size:15px;padding-top:6px">Как читать</h2>
  <div class="grid3" style="grid-template-columns:1fr 1fr">
    ${fl("tts_expressive","wave","Интонация","«!» — живее, «?» — выше, «…» — медленнее")}
    ${fl("tts_finish","end","Дочитывать реплику","Следующая начнётся сразу после, чуть быстрее")}
    ${fl("tts_read_name","lines","Читать имя говорящего","«Коллекционер: …» перед репликой")}
    ${fl("tts_russian_only","ru","Только русские голоса","Без иностранных голосов с акцентом")}
    ${fl("tts_skip","end","Не отставать при пролистывании","Листаете быстро — сразу читается свежая реплика")}
    ${fl("tts_nowait","wave","Без задержки","Не ждать ИИ-редактора: голос начинает сразу, остальное — уже в его варианте")}
    ${fl("tts_duck","voice","Приглушать игру","Пока звучит озвучка, звук игры тише — потом громкость возвращается")}
    ${fl("tts_cache","hist","Запоминать озвученное","Повторы фраз звучат сразу, без синтеза")}</div>
  <h2 style="font-size:15px;padding-top:6px">Ударения</h2>
  <div class="card" style="padding:14px 18px;display:flex;flex-direction:column;gap:8px">
    <span style="font-size:12px;color:var(--m)">ИИ-редактор запоминает ударения в именах и редких словах — дальше они звучат так всегда. Неверное — поправьте: «+» ставится перед ударной гласной. Работает для голосов Silero.</span>
    ${D.stress.length ? `<div class="lst">${D.stress.map(x => `<div class="row" style="padding:6px 0;gap:10px"><span style="flex-grow:1;font-size:14px">${esc(x.v.replace(/\+(.)/, (m, c) => c.toUpperCase()))}</span><input class="inp" style="width:170px;height:32px" value="${esc(x.v)}" data-c="strs" data-k="${esc(x.k)}"><button class="ib" style="color:var(--acc2)" title="Прослушать" data-a="strp" data-v="${esc(x.v)}">${svg("play", 14)}</button><button class="ib" title="Забыть" data-a="strd" data-k="${esc(x.k)}">${svg("x", 14)}</button></div>`).join("")}</div>` : `<span style="font-size:13px;color:var(--f)">Пока пусто — появятся, когда редактор встретит имена в игре.</span>`}
  </div>`;
}
function chars() {
  const C = D.chars, q = SUB.charQ.toLowerCase(), G = SUB.charG;
  const n = {all: C.length, f: C.filter(c => c.g == "f").length, m: C.filter(c => c.g == "m").length};
  const list = C.filter(c => (G == "all" || c.g == G) && (!q || (c.name + " " + c.en).toLowerCase().includes(q)));
  const seg = c => `<div class="seg" role="group" aria-label="Пол">${[["f","Ж"],["m","М"],["","авто"]].map(([v, t]) => `<button class="${v ? "m" : ""}" aria-pressed="${c.manual_g == v}" data-a="cg" data-k="${esc(c.key)}" data-v="${v}">${t}</button>`).join("")}</div>`;
  const vs = c => `<select class="sel" style="width:160px;height:32px;font-size:13px" data-c="cv" data-k="${esc(c.key)}"><option value="">авто${c.auto ? " · " + esc(c.auto) : ""}</option>${D.char_voices.map(v => `<option value="${esc(v.id)}" ${v.id == c.voice ? "selected" : ""}>${esc(v.name)}</option>`).join("")}</select>`;
  const row = c => `<div class="r" style="padding:9px 0"><span class="av" style="background:${c.g == "f" ? "#d16ba5" : "#5865F2"}">${esc(c.name[0])}</span>
    <span class="tx"><span style="font-weight:500">${esc(c.name)}</span><span class="d" style="color:var(--f);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${c.en && c.en != c.name ? esc(c.en) + " · " : ""}${c.g == "f" ? "женский" : "мужской"}, ${esc(c.how)}${c.type ? " · " + esc(c.type) : ""}${c.addr ? " · на «" + esc(c.addr) + "»" : ""}</span></span>
    ${seg(c)}${vs(c)}<button class="ib" style="color:var(--acc2)" title="Прослушать" data-a="cplay" data-k="${esc(c.key)}" data-n="${esc(c.name)}">${svg("play", 14)}</button><button class="ib" style="color:var(--f)" title="Забыть" data-a="cforget" data-k="${esc(c.key)}" data-n="${esc(c.name)}">${svg("x", 14)}</button></div>`;
  return `<div class="row" style="gap:8px"><span class="subt" style="flex-grow:1">Имена берутся из субтитров, пол угадывается по речи и по имени. Поправьте, если ошиблось.</span><span class="chip" style="height:32px">${esc(D.game || "")}</span></div>
  <div class="row" style="gap:8px"><label style="display:flex;align-items:center;gap:8px;height:34px;padding:0 10px;border-radius:8px;background:var(--card);color:var(--f);flex-grow:1">${svg("search", 15)}<input class="inp" style="background:none;padding:0;height:auto" placeholder="Найти персонажа" data-i="cq" value="${esc(SUB.charQ)}"></label>
    ${[["all","Все"],["f","Женщины"],["m","Мужчины"]].map(([k, t]) => `<button class="chip" style="height:34px" aria-pressed="${G == k}" data-a="cgf" data-v="${k}">${t}<span class="c">${n[k]}</span></button>`).join("")}</div>
  ${D.engine == "windows" ? `<div style="font-size:12px;color:var(--warn)">Сейчас выбран голос Windows — свои голоса персонажей работают только с нейроголосами или Silero.</div>` : ""}
  <div class="card" style="padding:4px 14px">${list.length ? `<div class="lst">${list.map(row).join("")}</div>` : `<div class="empty">${C.length ? "Никого не нашлось." : "Пока никого — персонажи появятся, когда заговорят в субтитрах."}</div>`}</div>`;
}
HANDLERS.vtab = b => { SUB.voice = b.dataset.v; D && render(); };
HANDLERS.von = b => act("tts_on", b.getAttribute("aria-checked") != "true");
HANDLERS.veng = b => act("tts_engine", b.dataset.v);
HANDLERS.vvoice = b => act("tts_voice", b.value);
HANDLERS.vrate = b => act("tts_rate", +b.value);
HANDLERS.vvol = b => act("tts_volume", +b.value);
HANDLERS.vtesti = b => { SUB.vtest = b.value; };
HANDLERS.vplay = () => act("tts_test", $("vtest") ? $("vtest").value : "");
HANDLERS.vmode = b => act("voice_mode", b.dataset.v);
HANDLERS.gvoice = b => act("gender_voice", {g: b.dataset.g, v: b.value});
HANDLERS.gtest = b => act("gender_test", {g: b.dataset.g});
HANDLERS.vpack = () => act("voicepack_install");
HANDLERS.cg = b => act("char_gender", {key: b.dataset.k, v: b.dataset.v});
HANDLERS.cv = b => act("char_voice", {key: b.dataset.k, v: b.value});
HANDLERS.cplay = b => act("char_play", {key: b.dataset.k, name: b.dataset.n});
HANDLERS.cforget = b => confirmDlg(`Забыть «${b.dataset.n}»?`, "Пол и голос сбросятся; если персонаж снова заговорит, программа угадает их заново.", "Забыть", () => act("char_forget", {key: b.dataset.k}));
HANDLERS.cq = b => { SUB.charQ = b.value; render(); refocus('[data-i="cq"]'); };
HANDLERS.cgf = b => { SUB.charG = b.dataset.v; render(); };
function refocus(sel) { const i = document.querySelector(sel); if (i) { i.focus(); i.setSelectionRange(i.value.length, i.value.length); } }

// ---------- история ----------
const KC = {"Субтитры":"#949cf7","Ответы":"#23a55a","Задание":"#f0b232","Чат":"#d16ba5"};
R.hist = () => {
  if (!D) return null;
  const all = D.items, kinds = ["Все", ...new Set(all.map(e => e.kind))], K = SUB.histKind, q = SUB.histQ.toLowerCase();
  const list = all.filter(e => (K == "Все" || e.kind == K) && (!q || (e.tr + " " + e.orig).toLowerCase().includes(q)));
  const ent = e => `<div class="r" style="align-items:flex-start"><div class="tx" style="gap:3px"><div style="display:flex;gap:8px;font-size:11px"><span style="font-family:var(--mono);color:var(--f)">${esc(e.t)}</span><span style="color:${KC[e.kind] || "var(--acc2)"};font-weight:600">${esc(e.kind)}</span></div>
    <span style="white-space:pre-wrap;user-select:text">${esc(e.tr)}</span>${e.orig ? `<span style="font-size:12px;color:var(--f);white-space:pre-wrap;user-select:text">${esc(e.orig)}</span>` : ""}</div>
    <button class="ib" style="color:var(--acc2)" title="Прослушать" data-a="hplay" data-v="${esc(e.tr)}">${svg("play", 14)}</button></div>`;
  return `<div style="display:flex;flex-direction:column;gap:4px"><h1>История</h1><span class="subt">Всё, что переведено за этот запуск. Каждый день ещё и сохраняется в свой файл.</span></div>
  <div class="row" style="gap:8px"><label style="display:flex;align-items:center;gap:8px;height:34px;padding:0 10px;border-radius:8px;background:var(--card);color:var(--f);flex-grow:1">${svg("search", 15)}<input class="inp" style="background:none;padding:0;height:auto" placeholder="Поиск по переводу и оригиналу" data-i="hq" value="${esc(SUB.histQ)}"></label>
    <button class="btn" style="height:34px;display:flex;align-items:center;gap:6px" data-a="hfolder">${svg("folder", 14)}Папка</button></div>
  <div style="display:flex;gap:6px;flex-wrap:wrap">${kinds.map(k => `<button class="chip" aria-pressed="${K == k}" data-a="hk" data-v="${esc(k)}">${esc(k)}<span class="c">${k == "Все" ? all.length : all.filter(e => e.kind == k).length}</span></button>`).join("")}</div>
  <div class="card" style="padding:4px 14px">${list.length ? `<div class="lst">${list.map(ent).join("")}</div>` : `<div class="empty">${all.length ? "Ничего не найдено." : "Пока пусто — здесь появится всё, что переведено."}</div>`}</div>`;
};
HANDLERS.hq = b => { SUB.histQ = b.value; render(); refocus('[data-i="hq"]'); };
HANDLERS.hk = b => { SUB.histKind = b.dataset.v; render(); };
HANDLERS.hplay = b => act("hist_play", b.dataset.v);

// ---------- клавиши ----------
R.start = () => {
  if (!D) return null;
  const step = (n, st, t, d, acts) => `<div class="card" style="padding:14px 18px;display:flex;gap:14px;align-items:flex-start">
    <span style="flex-shrink:0;width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:600;font-size:13px;${st.ok ? "background:var(--ok,#3ba55d);color:#fff" : "background:var(--line)"}">${st.ok ? "✓" : n}</span>
    <div style="display:flex;flex-direction:column;gap:6px;flex-grow:1"><div class="row"><span style="font-weight:600;flex-grow:1">${t}</span><span style="font-size:12px;color:${st.ok ? "var(--ok,#3ba55d)" : "var(--f)"}">${esc(st.txt)}</span></div>
    <span style="font-size:13px;color:var(--m);line-height:1.5">${d}</span>${acts ? `<div class="row" style="gap:8px;flex-wrap:wrap">${acts}</div>` : ""}</div></div>`;
  const T = D.tr;
  return `<div style="display:flex;flex-direction:column;gap:4px"><h1>Начало работы</h1><span class="subt">Пять шагов — и игра на русском. Шаги отмечаются сами.</span></div>
  ${step(1, T, "Выберите переводчик", "Google работает сразу и без ключа. Нейросеть Groq бесплатна, переводит живее и понимает сцену, но ей нужен ключ — получить его можно за пару минут.",
    `<button class="btn" data-a="wzp" data-v="google">Google — без ключа</button><button class="btn" data-a="wzp" data-v="groq_ocr">Groq — нейросеть</button>${T.main.startsWith("groq") && !T.groq_key ? `<button class="btnp" style="padding:6px 14px;font-size:13px" data-a="key" data-id="groq">Добавить ключ Groq</button>` : ""}`)}
  ${step(2, D.game, "Запустите игру", "Программа сама узнает игру и заведёт ей свои области, словарь и персонажей. Ничего нажимать не нужно.", "")}
  ${step(3, D.area, "Обведите субтитры", "Обведите мышкой место на экране, где в игре появляются реплики персонажей. Можно нажать клавишу прямо в игре.",
    `<button class="btnp" style="padding:6px 14px;font-size:13px" data-act="select">Обвести субтитры · ${esc(D.area.key)}</button>`)}
  ${step(4, D.auto, "Включите автоперевод", "Дальше программа сама переводит каждую новую реплику.",
    `<button class="btnp" style="padding:6px 14px;font-size:13px" data-act="auto">Включить · ${esc(D.auto.key)}</button>`)}
  ${step(5, D.voice, "Озвучка — по желанию", "Реплики будут читаться вслух, у каждого персонажа свой голос.",
    `<button class="btn" data-go="voice">Настроить озвучку</button>`)}
  <div class="row" style="justify-content:flex-end;gap:8px"><button class="btn" data-a="wzdone">Пропустить</button><button class="btnp" style="padding:6px 14px;font-size:13px" data-a="wzdone">Готово</button></div>`;
};
HANDLERS.wzp = b => act("wizard_provider", b.dataset.v);
HANDLERS.wzdone = () => { act("wizard_done"); go("home"); };

R.keys = () => {
  if (!D) return null;
  const row = (k, first) => `<div class="r" style="padding:7px 0;${first ? "" : "border-top:.5px solid var(--line)"}"><span class="tx"><span>${esc(k.desc)}</span>${k.risk ? `<span style="font-size:12px;color:var(--warn)">⚠ ${esc(k.risk)}</span>` : ""}</span>
    <button class="key" style="border:0;min-width:120px;text-align:center;font-size:12px;padding:4px 10px;${D.capturing == k.id ? "color:var(--warn)" : ""}" title="Нажмите, затем новую клавишу" data-a="kcap" data-v="${k.id}">${D.capturing == k.id ? "нажмите…" : esc(k.key)}</button></div>`;
  return `<div class="row" style="gap:12px;align-items:flex-end"><div style="display:flex;flex-direction:column;gap:4px;flex-grow:1"><h1>Клавиши</h1><span class="subt">Нажмите на клавишу, потом новую. Подходят и кнопки мыши. Esc — отмена.</span></div><button class="btn" style="height:32px" data-a="kdef">Вернуть по умолчанию</button></div>
  <div class="card" style="padding:12px 16px;display:flex;align-items:center;gap:12px"><span class="tx" style="display:flex;flex-direction:column;flex-grow:1"><span>Клавиши программы не доходят до игры</span><span style="font-size:12px;color:var(--m)">Нажали F9 — сработает только программа, игра нажатия не увидит. Кнопки мыши не перехватываются.</span></span>${sw(D.suppress, 'data-a="flag" data-n="suppress"')}</div>
  <div class="card" style="padding:10px 16px 12px">${D.groups.map((g, i) => `<div class="sec" style="${i ? "" : "padding-top:4px"}">${esc(g.title)}</div>${g.items.map((k, j) => row(k, j == 0)).join("")}`).join("")}</div>`;
};
HANDLERS.kcap = b => act("key_capture", b.dataset.v);
HANDLERS.kdef = () => confirmDlg("Вернуть клавиши по умолчанию?", "Все назначения станут как при установке программы.", "Вернуть", () => act("keys_default"));

// ---------- настройки ----------
R.settings = () => {
  if (!D) return null;
  const row = (t, d, right, first) => `<div class="r" style="${first ? "" : "border-top:.5px solid var(--line)"}"><span class="tx"><span>${t}</span>${d ? `<span class="d">${d}</span>` : ""}</span>${right}</div>`;
  const ab = D.autobackups.map((n, i) => row(esc(n), "", `<button class="btn" data-a="bres" data-v="${esc(n)}">Вернуть</button>`, i == 0)).join("");
  return `<div class="row"><h1 style="flex-grow:1">Настройки</h1><button class="btn" data-go="start">Мастер первого запуска</button></div>
  <div class="card" style="padding:0 16px 6px">
    <div class="sec">Обновления</div>${row("Версия " + esc(D.version), S && S.update ? "Доступна " + esc(S.update) : "Проверяется при запуске", `<button class="btn" data-act="update_check">Проверить</button>`, true)}
    ${row("Обновлять автоматически", "Новая версия ставится сразу при запуске программы", sw(D.update_auto, 'data-a="updauto"'))}
    <div class="sec">Поверх игры</div>${row("Значок поверх игры", "Маленькое «● AAC: перевод вкл», пока идёт автоперевод", sw(D.indicator, 'data-a="flag" data-n="indicator"'), true)}
    <div class="sec">Резервная копия</div>${row("Сохранить в файл", "Настройки, области, голоса персонажей, словарь и кэш. Ключи не сохраняются — они в Windows", `<button class="btn" data-a="bexp">Сохранить…</button>`, true)}
    ${row("Загрузить из файла", "Текущие настройки сначала сохранятся в папку backups. Программа перезапустится", `<button class="btn" data-a="bimp">Выбрать файл…</button>`)}
    ${ab ? `<div class="sec">Автокопии перед восстановлением</div>${ab}` : ""}
    <div class="sec">Папка программы</div>${row(esc(D.app_dir), "", `<button class="btn" data-a="ofold">Открыть</button>`, true)}
    <div class="sec">Удаление</div>${row("Удалить программу", "Удаляются только файлы программы. Игры и ваши папки не трогаются", `<button class="btnd" data-a="unins">Удалить…</button>`, true)}</div>`;
};
HANDLERS.updauto = b => act("update_auto", b.getAttribute("aria-checked") != "true");
HANDLERS.bexp = async () => { if (!window.pywebview) return; const p = await pywebview.api.save_file(D.backup_name); if (p) act("backup_save_to", p); };
HANDLERS.bimp = async () => { if (!window.pywebview) return; const p = await pywebview.api.open_file(); if (p) restoreDlg(p); };
HANDLERS.bres = b => restoreDlg(b.dataset.v);
HANDLERS.ofold = () => act("open_folder");
HANDLERS.unins = () => {
  modal(`<span style="font-size:18px;font-weight:600">Удалить AAC Translator?</span><span style="font-size:13px;color:var(--t3)">Удалится программа из папки ${esc(D.app_dir)} — только её файлы, чужие файлы в этой папке останутся. Вместе с ней: настройки, игры и их области, словари, персонажи, история, офлайн-голоса и ярлыки.</span>
    <label class="row" style="gap:10px;font-size:13px"><input type="checkbox" id="ub" checked style="accent-color:var(--acc)">Сначала сохранить резервную копию на рабочий стол</label>
    <label class="row" style="gap:10px;font-size:13px"><input type="checkbox" id="uk" checked style="accent-color:var(--acc)">Удалить сохранённые ключи переводчиков из Windows</label>
    <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Отмена</button><button class="btnp" style="background:#c0392b" id="ugo">Удалить</button></div>`);
  $("ugo").onclick = () => { const a = {backup: $("ub").checked, keys: $("uk").checked}; closeModal(); act("uninstall_run", a); };
};
async function restoreDlg(path) {
  const r = await act("backup_info", path), i = r.data || {};
  if (i.error) return confirmDlg("Не получилось открыть файл", i.error, "Понятно", () => {});
  confirmDlg("Загрузить резервную копию?", `Копия от ${i.created} (версия ${i.version}). В ней: ${i.what}. Текущие настройки сохранятся в папку backups. Программа перезапустится.`, "Загрузить", () => act("backup_restore_from", path));
}
async function pickDlg(title, text, fn, hideKnown) {
  const r = await get("/api/screen?name=programs") || {items: []};
  const items = r.items.filter(x => !(hideKnown && x.known));
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">${esc(title)}</span><button class="ib" data-close="1">${svg("x", 16)}</button></div><span style="font-size:13px;color:var(--t3)">${esc(text)}</span>
    <div style="display:flex;flex-direction:column;gap:4px;max-height:360px;overflow-y:auto">${items.map((x, i) => `<button class="gi" style="background:var(--side);flex-direction:column;align-items:flex-start;gap:0;padding:8px 12px" data-pick="${i}"><span style="font-weight:600">${esc(x.exe)}</span><span style="font-size:12px;color:var(--f)">${esc(x.title)}</span></button>`).join("") || '<span style="color:var(--warn);font-size:13px">Не нашёл открытых программ. Запустите игру и откройте этот список снова.</span>'}</div>
    <div style="display:flex;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Отмена</button></div>`);
  $("dlg").querySelectorAll("[data-pick]").forEach(b => b.onclick = () => { closeModal(); fn(items[+b.dataset.pick].exe); });
}

// ---------- вид перевода ----------
const back = (to, t) => `<a data-go="${to}" style="font-size:13px;display:inline-flex;align-items:center;gap:4px">← ${t}</a>`;
function ansBox(D, fam, sz, out, docked) {
  const bg = out ? "transparent" : "rgba(20,20,26," + D.alpha / 100 + ")";
  const sh = out ? "text-shadow:0 0 2px #000,0 0 2px #000,0 0 3px #000;" : "";
  return `<div style="${docked ? "margin-top:6px;padding-top:6px;border-top:.5px solid rgba(255,255,255,.12)" : "background:" + bg + ";border-radius:6px;padding:8px 10px"};font-family:'${esc(fam)}';text-align:left">
    <div style="font-size:11px;color:#9C9A92;margin-bottom:2px">Варианты ответа</div>
    <div style="font-size:${sz}px;color:${D.color};${sh}">1. Я пойду первым.</div><div style="font-size:${sz}px;color:${D.color};${sh}">2. Что там может быть?</div></div>`;
}
const rowC = (label, ctrl, desc) => `<div class="r rc"><span class="tx"><span>${label}</span>${desc ? `<span class="d">${desc}</span>` : ""}</span><div class="rcc">${ctrl}</div></div>`;
const slC = (k, min, max, step, v, fmt) => `<input type="range" min="${min}" max="${max}" step="${step}" value="${v}" data-c="st" data-k="${k}"><span class="rv">${fmt(v)}</span>`;
function extrasCard(D, DEF) {
  const t = (k, on) => sw(on, `data-a="stt" data-k="${k}"`);
  return `<div class="card grp"><div class="gh">Показ</div><div class="lst">
    ${DEF ? "" : rowC("Прошлых реплик над текущей", slC("history", 0, 3, 1, D.history, v => v)) + rowC("Убирать через", slC("delay", 0, 30, 0.5, D.delay, v => v + " с"), "После того как реплика исчезла с экрана")}
    ${rowC("Не убирать, пока нет новой реплики", t("keep", D.keep))}${rowC("Показывать оригинал под переводом", t("orig", D.orig))}
    ${rowC("Ответы под субтитрами", t("docked", D.docked), "Одним окном: варианты ответа сразу под репликой, двигаются вместе")}</div></div>`;
}
function styleBlock(D, DEF) {
  const sl = (k, t, min, max, step, v, fmt) => `<label style="display:flex;flex-direction:column;gap:4px"><span class="row"><span class="lbl" style="flex-grow:1">${t}</span><span style="font-size:12px">${fmt(v)}</span></span><input type="range" min="${min}" max="${max}" step="${step}" value="${v}" data-c="st" data-k="${k}"></label>`;
  const sws = (k, list, cur) => list.map(c => `<button title="${c}" data-a="stc" data-k="${k}" data-v="${c}" style="width:24px;height:24px;border-radius:6px;background:${c};border:2px solid ${c.toLowerCase() == cur.toLowerCase() ? "#fff" : "transparent"};padding:0"></button>`).join("") + `<label title="Другой цвет" style="width:24px;height:24px;border-radius:6px;overflow:hidden;border:.5px solid var(--line2);position:relative;display:flex;align-items:center;justify-content:center;color:var(--t3);box-sizing:border-box">${svg("plus", 14)}<input type="color" value="${cur}" data-c="stcol" data-k="${k}" style="position:absolute;inset:0;opacity:0;cursor:pointer"></label>`;
  const tg = (k, t, d, on) => `<div class="r"><span class="tx"><span>${t}</span>${d ? `<span class="d">${d}</span>` : ""}</span>${sw(on, `data-a="stt" data-k="${k}"`)}</div>`;
  const out = D.mode == "outline", fam = D.font, sz = D.size;
  const prev = `<div style="background:linear-gradient(160deg,#3a2c20,#1d1712);border-radius:14px;padding:12px 16px 16px;display:flex;flex-direction:column;align-items:center;gap:8px;min-height:150px"><span style="font-size:12px;color:#c9b9a6;align-self:flex-start;flex-grow:1">Образец</span>
    <div style="max-width:520px;background:${out ? "transparent" : "rgba(20,20,26," + D.alpha / 100 + ")"};border-radius:6px;padding:8px 10px;font-family:'${esc(fam)}'">
      ${D.history ? `<div style="font-size:${sz - 2}px;color:#9C9A92">Кеспер: Принеси кости — и я расскажу.</div>` : ""}
      <div style="font-size:${sz}px;font-weight:700;color:${D.color};${out ? "text-shadow:0 0 2px #000,0 0 2px #000,0 0 3px #000" : ""}">Ренальд: Держись рядом! Ты слышал это?</div>
      ${D.orig ? `<div style="font-size:11px;color:#9C9A92">Renald: Stay close! Did you hear that?</div>` : ""}
      ${D.docked ? ansBox(D, fam, sz, out, true) : ""}</div>${D.docked ? "" : `<div style="align-self:flex-end;margin-top:4px">${ansBox(D, fam, sz, out, false)}</div>`}</div>`;
  return `${prev}
    <div class="card grp"><div class="gh">Текст</div><div class="lst">
      ${rowC("Шрифт", `<select class="sel" style="width:220px" data-c="stf">${D.fonts.map(f => `<option ${f == fam ? "selected" : ""}>${esc(f)}</option>`).join("")}</select>`)}
      ${rowC("Цвет", sws("color", D.colors, D.color))}
      ${rowC("Подложка", `<div class="seg"><button aria-pressed="${!out}" class="m" data-a="stm" data-v="box" style="height:30px;padding:0 14px">Плашка</button><button aria-pressed="${out}" class="m" data-a="stm" data-v="outline" style="height:30px;padding:0 14px">Обводка букв</button></div>`)}
      ${rowC("Размер шрифта", slC("size", 10, 26, 1, sz, v => v))}
      ${rowC("Непрозрачность", slC("alpha", 40, 100, 5, D.alpha, v => v + "%"))}</div></div>`;
}
R.win = () => {
  if (!D) return null;
  const sl = (k, t, min, max, step, v, fmt) => `<label style="display:flex;flex-direction:column;gap:4px"><span class="row"><span class="lbl" style="flex-grow:1">${t}</span><span style="font-size:12px">${fmt(v)}</span></span><input type="range" min="${min}" max="${max}" step="${step}" value="${v}" data-c="st" data-k="${k}"></label>`;
  const sws = (k, list, cur) => list.map(c => `<button title="${c}" data-a="stc" data-k="${k}" data-v="${c}" style="width:24px;height:24px;border-radius:6px;background:${c};border:2px solid ${c.toLowerCase() == cur.toLowerCase() ? "#fff" : "transparent"};padding:0"></button>`).join("") + `<label title="Другой цвет" style="width:24px;height:24px;border-radius:6px;overflow:hidden;border:.5px solid var(--line2);position:relative;display:flex;align-items:center;justify-content:center;color:var(--t3);box-sizing:border-box">${svg("plus", 14)}<input type="color" value="${cur}" data-c="stcol" data-k="${k}" style="position:absolute;inset:0;opacity:0;cursor:pointer"></label>`;
  const tg = (k, t, d, on) => `<div class="r"><span class="tx"><span>${t}</span>${d ? `<span class="d">${d}</span>` : ""}</span>${sw(on, `data-a="stt" data-k="${k}"`)}</div>`;
  const out = D.mode == "outline", fam = D.font, sz = D.size;
  const prev = `<div style="background:linear-gradient(160deg,#3a2c20,#1d1712);border-radius:14px;padding:12px 16px 16px;display:flex;flex-direction:column;align-items:center;gap:8px;min-height:150px"><span style="font-size:12px;color:#c9b9a6;align-self:flex-start;flex-grow:1">Образец</span>
    <div style="max-width:520px;background:${out ? "transparent" : "rgba(20,20,26," + D.alpha / 100 + ")"};border-radius:6px;padding:8px 10px;font-family:'${esc(fam)}'">
      ${D.history ? `<div style="font-size:${sz - 2}px;color:#9C9A92">Кеспер: Принеси кости — и я расскажу.</div>` : ""}
      <div style="font-size:${sz}px;font-weight:700;color:${D.color};${out ? "text-shadow:0 0 2px #000,0 0 2px #000,0 0 3px #000" : ""}">Ренальд: Держись рядом! Ты слышал это?</div>
      ${D.orig ? `<div style="font-size:11px;color:#9C9A92">Renald: Stay close! Did you hear that?</div>` : ""}
      ${D.docked ? ansBox(D, fam, sz, out, true) : ""}</div>${D.docked ? "" : `<div style="align-self:flex-end;margin-top:4px">${ansBox(D, fam, sz, out, false)}</div>`}</div>`;
  const DEF = !!D.default;
  return `${DEF ? back("tr", "Переводчики") : back("games", "Игры")}<div style="display:flex;flex-direction:column;gap:4px"><h1>${DEF ? "Вид для новых игр" : "Вид перевода"}</h1><span class="subt">${DEF ? "Его получает каждая новая игра и режим «Без игры». У игры, которой вы уже настроили вид, он свой." : D.owner ? "Для игры «" + esc(D.owner) + "». У каждой игры свой вид." : "Вид по умолчанию — игра не выбрана."} Образец меняется сразу.</span></div>
  ${styleBlock(D, DEF)}${DEF ? "" : extrasCard(D, false) + `
  <h2 style="font-size:15px;padding-top:6px">Окно чата</h2>
  <div style="background:linear-gradient(160deg,#3a2c20,#1d1712);border-radius:14px;padding:12px 16px 16px;display:flex;flex-direction:column;gap:8px"><span style="font-size:12px;color:#c9b9a6">Образец</span>
    <div style="align-self:flex-start;width:340px;background:rgba(20,20,26,${D.chat_alpha / 100});border-radius:6px;padding:8px 10px;font-size:13px;display:flex;flex-direction:column;gap:3px;color:${D.chat_fg}">
      <div><span style="color:#9C9A92">[Гильдия] Nox:</span> кто идёт в подземелье?</div><div><span style="color:#9C9A92">[Мир] Lira:</span> продам кристаллы, недорого</div><div><span style="color:#9C9A92">[Группа] Ash:</span> жду у портала</div></div></div>
  <div class="card grp"><div class="lst">
    ${rowC("Перевод прямо поверх чата игры", sw(D.chat_cover, 'data-a="stt" data-k="chat_cover"'), "Та же область, что и чат")}
    ${rowC("Высота", slC("chat_height", 0, 600, 20, D.chat_height, v => v ? v + " px" : "авто"), "0 — по числу сообщений")}
    ${rowC("Хранить сообщений", slC("chat_history", 20, 1000, 10, D.chat_history, v => v))}
    ${rowC("Непрозрачность", slC("chat_alpha", 20, 100, 5, D.chat_alpha, v => v + "%"))}
    ${rowC("Цвет", sws("chat_fg", D.chat_colors, D.chat_fg))}</div></div>`}`;
};
const scope = () => (SCR == "win_default" || SCR == "tr") ? "default" : "game";
HANDLERS.st = b => act("style", {k: b.dataset.k, v: +b.value, scope: scope()});
HANDLERS.stf = b => act("style", {k: "font", v: b.value, scope: scope()});
HANDLERS.stc = b => act("style", {k: b.dataset.k, v: b.dataset.v, scope: scope()});
HANDLERS.stcol = b => act("style", {k: b.dataset.k, v: b.value, scope: scope()});
HANDLERS.stm = b => act("style", {k: "mode", v: b.dataset.v, scope: scope()});
R.win_default = () => R.win();
HANDLERS.stt = b => act("style", {k: b.dataset.k, v: b.getAttribute("aria-checked") != "true"});

// ---------- словарь ----------
R.gloss = () => {
  if (!D) return null;
  const it = D.items, q = (SUB.glQ || "").toLowerCase(), f = SUB.glF || "all";
  const n = {all: it.length, man: it.filter(x => !x.auto).length, auto: it.filter(x => x.auto).length};
  const list = it.filter(x => (f == "all" || (f == "auto") == x.auto) && (!q || (x.en + " " + x.ru).toLowerCase().includes(q)));
  const row = (x, i) => `<div class="r" style="padding:8px 0;cursor:pointer" data-a="gledit" data-i="${it.indexOf(x)}"><span style="flex:1;min-width:0">${esc(x.en)}</span><span style="color:var(--f)">→</span><span style="flex:1;min-width:0">${esc(x.ru)}</span>
    <span style="font-size:11px;padding:1px 8px;border-radius:6px;${x.auto ? "background:var(--side);color:var(--f)" : "background:rgba(88,101,242,.16);color:var(--acc2)"}">${x.auto ? "авто" : "вручную"}</span>
    <button class="ib" style="color:var(--f);width:26px;height:26px" title="Удалить" data-a="glrm" data-v="${esc(x.en)}">${svg("x", 13)}</button></div>`;
  return `${back("tr", "Переводчики")}<div class="row" style="gap:12px;align-items:flex-end"><div style="display:flex;flex-direction:column;gap:4px;flex-grow:1"><h1>Словарь${D.game ? " · " + esc(D.game) : ""}</h1><span class="subt">Имена и названия, которые всегда переводятся одинаково. Нажмите на строку, чтобы исправить.</span></div><span style="font-size:13px;color:var(--t3)">Пополнять сам</span>${sw(D.auto, 'data-a="flag" data-n="gloss_auto"')}</div>
  <div class="card" style="padding:12px 14px;display:flex;align-items:center;gap:10px"><input class="inp" style="background:var(--side)" id="glen" placeholder="Оригинал, например Renald" value="${esc(SUB.glEn || "")}" data-i="glen"><span style="color:var(--f)">→</span><input class="inp" style="background:var(--side)" id="glru" placeholder="Перевод, например Ренальд" value="${esc(SUB.glRu || "")}" data-i="glru"><button class="btnp" style="padding:7px 16px;flex-shrink:0" data-a="gladd">Добавить</button></div>
  <div class="row" style="gap:8px"><label style="display:flex;align-items:center;gap:8px;height:34px;padding:0 10px;border-radius:8px;background:var(--card);color:var(--f);flex-grow:1">${svg("search", 15)}<input class="inp" style="background:none;padding:0;height:auto" placeholder="Найти в словаре" data-i="glq" value="${esc(SUB.glQ || "")}"></label>
    ${[["all","Все"],["man","Вручную"],["auto","Авто"]].map(([k, t]) => `<button class="chip" style="height:34px" aria-pressed="${f == k}" data-a="glf" data-v="${k}">${t}<span class="c">${n[k]}</span></button>`).join("")}${lnk("Открыть файл", 'data-a="glfile"')}</div>
  <div class="card" style="padding:4px 16px">${list.length ? `<div class="lst">${list.slice(0, 400).map(row).join("")}</div>` : `<div class="empty">${it.length ? "Ничего не нашлось." : "Пусто."}</div>`}</div>
  <div class="card" style="padding:14px 16px;display:flex;flex-direction:column;gap:10px"><div class="row" style="gap:10px"><span style="font-weight:600">Не переводить</span><span style="font-size:12px;color:var(--m)">слова интерфейса, которые программа пропускает</span></div>
    <div style="display:flex;flex-wrap:wrap;gap:6px">${D.ignore.map(w => `<span class="chip" style="height:26px;font-size:12px;${w.builtin ? "color:var(--f)" : ""}">${esc(w.w)}${w.builtin ? "" : `<a data-a="igrm" data-v="${esc(w.w)}" style="color:var(--f)">${svg("x", 12)}</a>`}</span>`).join("")}</div>
    <div class="row" style="gap:8px"><input class="inp" style="background:var(--side);max-width:260px" id="igw" placeholder="Слово или фраза" data-i="igw" value="${esc(SUB.igW || "")}"><button class="btn" style="height:32px" data-a="igadd">Добавить</button></div></div>`;
};
HANDLERS.glen = b => { SUB.glEn = b.value; };
HANDLERS.glru = b => { SUB.glRu = b.value; };
HANDLERS.igw = b => { SUB.igW = b.value; };
HANDLERS.gladd = () => { const en = (SUB.glEn || "").trim(), ru = (SUB.glRu || "").trim(); if (!en || !ru) return; SUB.glEn = SUB.glRu = ""; $("glen").value = $("glru").value = ""; act("gloss_set", {en, ru}); };
HANDLERS.gledit = (b, e) => { if (e.target.closest('[data-a="glrm"]')) return; const x = D.items[+b.dataset.i]; SUB.glEn = x.en; SUB.glRu = x.ru; render(); refocus("#glru"); };
HANDLERS.glrm = (b, e) => { e.stopPropagation(); act("gloss_remove", b.dataset.v); };
HANDLERS.glq = b => { SUB.glQ = b.value; render(); refocus('[data-i="glq"]'); };
HANDLERS.glf = b => { SUB.glF = b.dataset.v; render(); };
HANDLERS.glfile = () => act("gloss_file");
HANDLERS.igadd = () => { const w = (SUB.igW || "").trim(); if (!w) return; SUB.igW = ""; $("igw").value = ""; act("ignore_add", w); };
HANDLERS.igrm = b => act("ignore_remove", b.dataset.v);
document.addEventListener("keydown", e => {
  if (e.key != "Enter") return;
  if (e.target.id == "glru" || e.target.id == "glen") HANDLERS.gladd();
  if (e.target.id == "igw") HANDLERS.igadd();
});

// ---------- окна поверх панели ----------
function modal(html) { $("dlg").innerHTML = html; $("modal").classList.add("on"); }
function closeModal() { $("modal").classList.remove("on"); render(); }
$("modal").addEventListener("click", e => { if (e.target.id == "modal" || e.target.closest("[data-close]")) closeModal(); });
document.addEventListener("keydown", e => { if (e.key == "Escape" && $("modal").classList.contains("on")) closeModal(); });
function confirmDlg(title, text, yes, fn) {
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">${esc(title)}</span></div><span style="font-size:13px;color:var(--t3)">${esc(text)}</span>
    <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Отмена</button><button class="btnp" id="yes">${esc(yes)}</button></div>`);
  $("yes").onclick = () => { closeModal(); fn(); };
}
function keyDlg(pid) {
  const p = D.providers.find(x => x.id == pid);
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">Ключ ${esc(p.name)}</span><button class="ib" data-close="1">${svg("x", 16)}</button></div>
    ${p.has ? `<span style="font-size:13px;color:var(--t3)">Сейчас сохранён ключ ${esc(p.masked)}. Вставьте новый, чтобы заменить.</span>` : ""}
    <input class="inp" type="password" id="kv" placeholder="Вставьте ключ" autocomplete="off">
    <span style="font-size:12px;color:var(--f)">Ключ сохранится в Windows — не в настройках программы, не в резервных копиях и не на GitHub. Перезапуск не нужен.</span>
    <div style="display:flex;gap:8px">${p.has ? `<button class="btnd" id="krm">Удалить ключ</button>` : ""}<span style="flex-grow:1"></span><button class="btn" style="height:36px;padding:0 16px;font-size:13px" data-close="1">Отмена</button><button class="btnp" id="ksave">Сохранить</button></div>`);
  $("kv").focus();
  const save = () => { const v = $("kv").value.trim(); if (!v) return; $("kv").value = ""; closeModal(); act("key_save", {id: pid, v}); };
  $("ksave").onclick = save; $("kv").onkeydown = e => { if (e.key == "Enter") save(); };
  if ($("krm")) $("krm").onclick = () => { closeModal(); act("key_remove", {id: pid}); };
}
async function reportDlg() {
  const r = await get("/api/screen?name=report") || {can: false, why: ""};
  modal(`<div class="row"><span style="font-size:18px;font-weight:600;flex-grow:1">Сообщить о проблеме</span><button class="ib" data-close="1">${svg("x", 16)}</button></div>
    <div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Что случилось</span><textarea class="inp" id="rt" placeholder="Например: в Dead Cells перестали переводиться ответы после обновления"></textarea></div>
    <div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">Как с вами связаться (необязательно)</span><input class="inp" id="rc"></div>
    <label class="row" style="gap:10px;font-size:13px;color:var(--t2)"><input type="checkbox" id="rs" checked style="accent-color:var(--acc)">Приложить снимок экрана (панель на время спрячется)</label>
    <div style="display:flex;flex-direction:column;gap:6px;background:var(--bg);border-radius:10px;padding:12px 14px"><span class="lbl">Что уйдёт вместе с сообщением</span>
      ${["Журнал этого запуска и ошибки программы","Версия, Windows, мониторы","Настройки игр и их области"].map(t => `<div class="row" style="gap:8px;font-size:13px;color:var(--t2)"><span style="color:var(--ok);display:flex">${svg("check", 14)}</span>${t}</div>`).join("")}
      <span style="font-size:12px;color:var(--f);margin-top:4px">${r.can ? "Без ключей, имён и личных файлов." : "Отправка недоступна: " + esc(r.why) + ". Сохраню архив — его можно передать автору вручную."}</span></div>
    <div style="display:flex;gap:8px;justify-content:flex-end"><button class="btn" style="height:36px;padding:0 16px;font-size:13px" id="rsave">Сохранить архив</button>${r.can ? `<button class="btnp" id="rsend">Отправить</button>` : ""}</div>`);
  $("rt").focus();
  const go = send => { const text = $("rt").value.trim(); if (send && !text) { $("rt").style.outline = "1px solid var(--err)"; return; }
    const a = {text, contact: $("rc").value, shot: $("rs").checked, send}; closeModal(); act("report", a); };
  $("rsave").onclick = () => go(false); if ($("rsend")) $("rsend").onclick = () => go(true);
}

// ---------- журнал ----------
let F = "all"; const LC = {ok: "var(--ok)", warn: "var(--warn)", error: "var(--err)", info: "var(--f)"};
function addLog(e, scroll = true) {
  const tr = /→|:\s/.test(e.msg) && e.level == "info";
  const d = document.createElement("div"); d.className = "e"; d.dataset.k = e.level == "error" || e.level == "warn" ? "err" : tr ? "tr" : "other";
  d.innerHTML = `<div class="m"><i class="dot" style="width:6px;height:6px;background:${LC[e.level] || LC.info}"></i><span>${esc(e.t)}</span></div><div>${esc(e.msg)}</div>`;
  d.style.display = F == "all" || d.dataset.k == F ? "" : "none";
  const L = $("log"), atEnd = L.scrollHeight - L.scrollTop - L.clientHeight < 40; L.appendChild(d);
  while (L.children.length > 500) L.firstChild.remove();
  if (scroll && atEnd) L.scrollTop = L.scrollHeight;
}
$("flt").onclick = e => { const b = e.target.closest("button"); if (!b) return; F = b.dataset.f;
  for (const x of $("flt").children) x.setAttribute("aria-pressed", x == b);
  for (const d of $("log").children) d.style.display = F == "all" || d.dataset.k == F ? "" : "none"; };
(() => { let x0, w0; const g = $("grip"), j = $("jr"); try { const w = localStorage.getItem("jw"); if (w) j.style.width = w + "px"; } catch (e) {}
  g.onmousedown = e => { x0 = e.clientX; w0 = j.offsetWidth; document.onmousemove = m => { j.style.width = Math.max(260, Math.min(700, w0 + x0 - m.clientX)) + "px"; };
    document.onmouseup = () => { document.onmousemove = null; try { localStorage.setItem("jw", j.offsetWidth); } catch (e) {} }; }; })();

// ---------- заставка при запуске: проверка обновлений ----------
const bootT0 = Date.now();
function bootView(b) {
  const el = $("boot"); if (!el || el.classList.contains("off")) return;
  b = b || {phase: "done"};
  const bar = $("bootbar");
  if (b.phase == "checking") $("boots").textContent = "Проверяю обновления…";
  else if (b.phase == "downloading") { $("boots").textContent = `Скачиваю версию ${b.to || ""}… ${b.pct || 0}%`; bar.classList.add("det"); bar.style.width = (b.pct || 0) + "%"; }
  else if (b.phase == "installing") { $("boots").textContent = `Ставлю версию ${b.to || ""} — программа сейчас перезапустится`; bar.classList.remove("det"); bar.style.width = "30%"; }
  if (b.phase == "done" || (b.phase == "checking" && Date.now() - bootT0 > 8000)) el.classList.add("off");
}
setTimeout(() => { const el = $("boot"); if (el && S && S.boot && S.boot.phase == "checking") el.classList.add("off"); }, 9000);

// ---------- новая версия — в боковой колонке ----------
let updShown = null;
function updNav() {
  const st = S && S.staged || "", v = st || (S && S.update) || "";
  if (v + st === updShown) return; updShown = v + st;
  $("updnav").innerHTML = st ? `<div class="uc"><span>Версия ${esc(st)} скачана — поставится, когда закроете программу</span><button data-act="restart">Перезапустить сейчас</button></div>
    <button class="ui" data-act="restart" title="Версия ${esc(st)} скачана — перезапустить сейчас" aria-label="Перезапустить в версию ${esc(st)}">${svg("end", 16, 2).replace("M5 12h14M13 6l6 6-6 6", "M12 19V5M6 11l6-6 6 6")}</button>` : v ? `<div class="uc"><span>Доступна версия ${esc(v)}</span><button data-act="update_install">Обновить</button></div>
    <button class="ui" data-act="update_install" title="Доступна версия ${esc(v)} — обновить" aria-label="Обновить до ${esc(v)}">${svg("end", 16, 2).replace("M5 12h14M13 6l6 6-6 6", "M12 19V5M6 11l6-6 6 6")}</button>` : "";
}

function lastLog(e) {
  const el = $("jrlast"); if (!el) return;
  el.innerHTML = `<i class="dot" style="width:7px;height:7px;background:${LC[e.level] || LC.info}"></i><span class="t">${esc(e.t)}</span><span class="m">${esc(e.msg)}</span>`;
  el.title = e.msg;
}

// ---------- свернуть меню и журнал ----------
let unread = 0;
function layout(save) {
  const nc = document.body.classList.contains("nav-c"), jc = document.body.classList.contains("jr-c");
  $("navc").title = nc ? "Развернуть меню" : "Свернуть меню"; $("navc").setAttribute("aria-label", $("navc").title);
  $("ver").textContent = S ? "v " + S.version : "v";
  $("gear").title = nc && S ? `Настройки · версия ${S.version}` : "Настройки";
  if (!jc) { unread = 0; }
  $("jrn").textContent = unread > 99 ? "99+" : unread; $("jrn").style.display = jc && unread ? "inline-block" : "none";
  if (save) try { localStorage.setItem("lay", JSON.stringify({nc, jc})); } catch (e) {}
}
try { const l = JSON.parse(localStorage.getItem("lay") || "{}"); if (l.nc) document.body.classList.add("nav-c"); if (l.jc) document.body.classList.add("jr-c"); } catch (e) {}
$("navc").onclick = () => { document.body.classList.toggle("nav-c"); layout(true); };
$("jrc").onclick = () => { document.body.classList.add("jr-c"); layout(true); };
$("jrlast").onclick = () => $("jro").click();
$("jro").onclick = () => { document.body.classList.remove("jr-c"); layout(true); const L = $("log"); L.scrollTop = L.scrollHeight; };
$("jrc").title = "Скрыть журнал";

async function start() {
  nav();
  try { await fetch("/api/hello", {method: "POST", headers: H, body: "{}"}); } catch (e) {}
  const lg = await get("/api/log"); if (lg) { lg.forEach(e => addLog(e, false)); if (lg.length) lastLog(lg[lg.length - 1]); $("log").scrollTop = 1e9; }
  const es = new EventSource("/api/events?t=" + encodeURIComponent(T));
  es.addEventListener("log", m => { lastLog(JSON.parse(m.data)); addLog(JSON.parse(m.data)); if (document.body.classList.contains("jr-c")) { unread++; layout(); } refresh(); });
  es.addEventListener("toggle", () => { window.pywebview && pywebview.api.toggle(); });
  es.addEventListener("hide", () => { window.pywebview && pywebview.api.hide(); });
  es.addEventListener("show", () => { window.pywebview && pywebview.api.show(); });
  es.addEventListener("quit", () => { window.pywebview && pywebview.api.quit(); });
  refresh(true); setInterval(refresh, 1200);
}
$("main").addEventListener("scroll", () => document.body.classList.toggle("scrolled", $("main").scrollTop > 4));
layout();
start();
