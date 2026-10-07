"use strict";
/* vlogkit Stüdyo: attach a video, say what you want, watch Claude Code do it. */

const TOKEN = document.querySelector('meta[name="vlogkit-token"]').content;
const $ = (s, r = document) => r.querySelector(s);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat()) if (k != null) n.append(k);
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const media = (p) => `/media?path=${encodeURIComponent(p)}&token=${encodeURIComponent(TOKEN)}`;
const base = (p) => String(p).split("/").pop();

async function api(path, opts = {}) {
  const r = await fetch(path, { ...opts, headers: { "X-Vlogkit-Token": TOKEN, "Content-Type": "application/json" } });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(d.error || r.statusText);
  return d;
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
let toastT;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2200);
}
const saved = {
  get(k, d) { try { const v = localStorage.getItem("vk-" + k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem("vk-" + k, JSON.stringify(v)); } catch { /* private mode */ } },
};

/* Short names for the guide's tasks (full titles live in docs/prompts.md). */
const LABEL = {
  K1: "Klasörü keşfet", K2: "Hızlı bakış", S1: "Short'u parlat", S2: "Ham çekimden Short",
  S3: "Uzun videodan Short'lar", S4: "Short serisi planla", S5: "Meme varyantı", S6: "Hook A/B", S7: "Müziğe göre Reels",
  S8: "Trend şarkı varyantları", S9: "Beğendiğin kurgunun tarzıyla", U5: "Konuşma denemelerinden", U6: "Anlatım ekle", U7: "Açılış konuşması",
  U1: "Yatay vlog kur", U2: "Uzun videoyu cilala", U3: "Resolve'a aktar", U4: "Boşlukları kes", R1: "Düzeltme yap",
  R2: "Varyantları karşılaştır", R3: "Varyantları birleştir", R4: "Müzik seç", Y1: "Yayın paketi", Y2: "Teslim kontrolü",
  G1: "vlogkit'e özellik ekle", G2: "Öğrenileni kaydet", G3: "Rehberi güncelle", G4: "Öneriyi uygula",
};
const HOME_TASKS = ["K1", "K2", "S1", "S2", "S3", "S7", "Y1"];
const PLAN_ADDON = "Önce plan göster, onaylamadan derleme.";

const S = {
  guide: null, video: null, task: null, plan: saved.get("plan", true), addons: new Set(saved.get("addons", [])),
  jobs: [], job: null, es: null, seen: 0, turns: [], att: [],
  cut: { level: "dengeli", captions: true, music: true, sfx: true, note: "", ...saved.get("cut", {}) },
};

/* ------------------------------------------------------------------ markdown */
function inline(s) {
  let o = esc(s);
  o = o.replace(/`([^`]+)`/g, "<code>$1</code>");
  o = o.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  o = o.replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*(?!\w)/g, "$1<em>$2</em>");
  o = o.replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return o;
}
// items: [{ indent, ol, n, text }] -> nested <ul>/<ol> (a deeper indent nests in the open <li>)
function listHtml(items) {
  let i = 0;
  const build = (indent) => {
    const f = items[i], tag = f.ol ? "ol" : "ul";
    let html = `<${tag}${f.ol && f.n > 1 ? ` start="${f.n}"` : ""}>`, open = false;
    while (i < items.length && items[i].indent >= indent) {
      const it = items[i];
      if (it.indent > indent) { html += build(it.indent); continue; }
      if ((it.ol ? "ol" : "ul") !== tag) break;
      if (open) html += "</li>";
      html += `<li>${inline(it.text)}`; open = true; i++;
    }
    return html + (open ? "</li>" : "") + `</${tag}>`;
  };
  let html = "";
  while (i < items.length) html += build(items[i].indent);
  return html;
}
function md(src) {
  const L = String(src || "").replace(/\r/g, "").split("\n"); const out = [];
  let i = 0, para = [], list = null;
  const flush = () => {
    if (para.length) { out.push(`<p>${inline(para.join(" "))}</p>`); para = []; }
    if (list) { out.push(listHtml(list)); list = null; }
  };
  while (i < L.length) {
    const line = L[i];
    if (/^```/.test(line)) {
      flush(); const b = []; i++;
      while (i < L.length && !/^```/.test(L[i])) b.push(L[i++]);
      out.push(`<pre><code>${esc(b.join("\n"))}</code></pre>`); i++; continue;
    }
    if (/^\s*\|.*\|\s*$/.test(line) && /^\s*\|?\s*:?-{2,}/.test(L[i + 1] || "")) {
      flush(); const rws = [];
      while (i < L.length && /^\s*\|.*\|\s*$/.test(L[i])) rws.push(L[i++]);
      const cells = (r) => r.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
      out.push(`<table><thead><tr>${cells(rws[0]).map((h) => `<th>${inline(h)}</th>`).join("")}</tr></thead><tbody>${
        rws.slice(2).map((r) => `<tr>${cells(r).map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("")}</tbody></table>`);
      continue;
    }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    if (h) { flush(); out.push(`<h${h[1].length + 2}>${inline(h[2])}</h${h[1].length + 2}>`); i++; continue; }
    const li = line.match(/^(\s*)(?:[-*]|(\d+)\.)\s+(.*)$/);
    if (li) {
      if (para.length) flush();
      (list = list || []).push({ indent: li[1].replace(/\t/g, "    ").length, ol: !!li[2], n: li[2] ? +li[2] : 1, text: li[3] });
      i++; continue;
    }
    if (!line.trim()) {  // a blank line ends the list unless the list continues right after it
      if (list && /^\s*(?:[-*]|\d+\.)\s+/.test(L[i + 1] || "")) { i++; continue; }
      flush(); i++; continue;
    }
    if (list && /^\s{2,}\S/.test(line)) { list[list.length - 1].text += " " + line.trim(); i++; continue; }
    if (list) flush();
    para.push(line.trim()); i++;
  }
  flush();
  return out.join("");
}
/* The file list at the end of an answer is shown as a gallery instead. */
const stripOutputs = (t) => String(t || "").replace(/\n+\s*(\*\*)?Çıktılar:?(\*\*)?\s*\n[\s\S]*$/i, "").trim();
// "Öneri: …" lines are vlogkit improvement ideas: shown as a card with a one-click follow-up
const SUGGEST = /^[ \t>*_-]*(?:\*\*)?Öneri:(?:\*\*)?[ \t]*(.+?)[ \t*_]*$/gim;
function splitSuggestions(text) {
  const ideas = [];
  const rest = text.replace(SUGGEST, (_, idea) => { ideas.push(idea.trim()); return ""; }).replace(/\n{3,}/g, "\n\n").trim();
  return { rest, ideas };
}
function suggestion(idea) {
  // an installed copy does not change vlogkit itself: the idea goes to its developer
  const act = S.release
    ? el("button", { class: "tool", type: "button", text: "Kopyala", title: "vlogkit'in geliştiricisine gönder",
      onclick: () => navigator.clipboard.writeText(`vlogkit önerisi: ${idea}`).then(() => toast("Öneri kopyalandı"), () => toast("Kopyalanamadı")) })
    : el("button", { class: "tool", type: "button", text: "Öneriyi uygula", title: "Yazma kutusuna ekler",
      onclick: () => { input.value = `Öneriyi uygula: ${idea}`; autosize(); checkFill(); input.focus(); } });
  return el("div", { class: "suggest" }, el("span", { class: "k", text: "Öneri" }), el("span", { class: "v", html: inline(idea) }), act);
}

// "Seçim: soru" and "N. etiket — /yol" lines under it: options the user judges by ear or eye
// (music under the scene from `vlogkit music`, cover or grade variants). Shown as cards with the
// media; "Bunu seç" writes "Seçim: N. etiket" into the input.
const CHOICE = /^[ \t>*_]*(?:\*\*)?Seçim:(?:\*\*)?[ \t]*(.+)\n(?:[ \t]*\n)?((?:[ \t]*\d+[.)][ \t]+.+(?:\n|$))+)/gim;
// the path runs to the end of the line: file names can have spaces ("Full Copy V1.3.mp4")
const OPTION = /^[ \t]*(\d+)[.)][ \t]+(.+?)(?:[ \t]+[—–][ \t]+`?((?:\/|~\/)[^`\n]+?)`?)?[ \t]*$/;
function splitChoices(text) {
  const choices = [];
  const rest = text.replace(CHOICE, (_, q, body) => {
    const items = body.split("\n").map((l) => l.match(OPTION)).filter(Boolean)
      .map((m) => ({ n: m[1], label: m[2].trim(), path: m[3] }));
    choices.push({ q: q.trim(), items });
    return "";
  }).replace(/\n{3,}/g, "\n\n").trim();
  return { rest, choices };
}
const kindOf = (p) => /\.(mp4|mov|m4v|webm)$/i.test(p) ? "video" : /\.(mp3|wav|m4a)$/i.test(p) ? "audio"
  : /\.(png|jpe?g|gif|webp)$/i.test(p) ? "image" : "";
function choiceCard(c) {
  const grid = el("div", { class: "opts" });
  for (const it of c.items) {
    const kind = it.path ? kindOf(it.path) : "";
    let body = null;
    if (kind === "video") body = el("video", { src: media(it.path), controls: true, preload: "metadata", playsinline: true, onloadedmetadata: toBottom });
    else if (kind === "audio") body = el("audio", { src: media(it.path), controls: true, preload: "none" });
    else if (kind === "image") body = el("img", { src: media(it.path), alt: "", onload: toBottom, onclick: () => openLight(media(it.path)) });
    // one at a time: comparing by ear needs silence around each
    if (body && kind !== "image") body.onplay = () => grid.querySelectorAll("video,audio").forEach((m) => { if (m !== body) m.pause(); });
    const opt = el("div", { class: "opt", title: it.path || "" }, body,
      el("div", { class: "row" }, el("span", { class: "n", text: it.n }), el("span", { class: "v", html: inline(it.label) }),
        el("button", { class: "tool", type: "button", text: "Bunu seç", onclick: () => {
          for (const o of grid.children) o.classList.toggle("picked", o === opt);
          input.value = input.value.split("\n").filter((l) => !/^Seçim:/.test(l)).join("\n").trimEnd();
          addLine(`Seçim: ${it.n}. ${it.label.replace(/`|\*\*/g, "")}`); checkFill();
        } })));
    grid.append(opt);
  }
  return el("div", { class: "choice" }, el("div", { class: "q", html: inline(c.q) }), grid);
}

/* ------------------------------------------------------------------ popovers */
let openPop = null;
function showPop(pop, anchor) {
  if (openPop === pop) return closePop();
  closePop();
  pop.hidden = false; openPop = pop;
  const r = anchor.getBoundingClientRect();
  const w = pop.offsetWidth;
  pop.style.left = `${Math.max(8, Math.min(r.left, innerWidth - w - 8))}px`;
  const below = innerHeight - r.bottom - 16, above = r.top - 16;
  if (above > below) { pop.style.top = ""; pop.style.bottom = `${innerHeight - r.top + 8}px`; pop.style.maxHeight = `${above}px`; }
  else { pop.style.bottom = ""; pop.style.top = `${r.bottom + 8}px`; pop.style.maxHeight = `${below}px`; }
  pop.scrollTop = 0;
}
function closePop() { if (openPop) openPop.hidden = true; openPop = null; }
document.addEventListener("click", (e) => {
  if (openPop && !openPop.contains(e.target) && !e.target.closest("[aria-haspopup]")) closePop();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") { closePop(); $("#lightbox").hidden = true; }
});

/* ------------------------------------------------------------------ composer */
const input = $("#input");
function autosize() { input.style.height = "auto"; input.style.height = `${Math.min(input.scrollHeight, innerHeight * 0.4)}px`; }
// Every chat keeps its own unsent text (the home screen too); it survives switching and reloads.
const draftKey = () => (S.job ? `draft:${S.job.id}` : "draft");
input.addEventListener("input", () => { autosize(); checkFill(); saved.set(draftKey(), input.value); });
// Enter = send, Shift+Enter = new line; never while an IME is composing
input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.isComposing && !e.shiftKey) { e.preventDefault(); submit(); }
});
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); submit(); });

function checkFill() {
  const left = [...new Set(input.value.match(/<[^<>\n]+>/g) || [])];
  const f = $("#fill"); f.hidden = !left.length || !!S.job;
  f.textContent = left.length ? `Doldur: ${left.join(", ")}` : "";
}

function fillTemplate(text) {
  const v = S.video;
  if (!v) return text;
  const folder = v.folder_display.replace(/\/$/, "");
  let t = text;
  if (!v.is_dir) t = t.replace(/~\/yt-vlogs\/<klasör>\/<(dosya|uzun video)>\.mp4/g, v.display);
  t = t.replace(/~\/yt-vlogs\/<klasör>/g, folder);
  t = t.replace(/<vlog-klasörü>|<klasör>|<vlog>/g, folder.split("/").pop());
  if (!v.is_dir) t = t.replace(/<dosya>|<uzun video>/g, v.name.replace(/\.[^.]+$/, ""));
  return t;
}

function useTask(code) {
  const p = S.guide.stages.flatMap((s) => s.prompts).find((x) => x.code === code);
  if (!p) return;
  S.task = code;
  input.value = fillTemplate(p.text);
  autosize(); checkFill(); saved.set("draft", input.value);
  $("#taskBtn").textContent = LABEL[code] || p.title;
  $("#taskBtn").classList.add("set");
  closePop(); input.focus();
}

function renderTasks() {
  const box = $("#tasks"); box.replaceChildren();
  for (const st of S.guide.stages) {
    box.append(el("h3", { text: st.title }));
    for (const p of st.prompts) {
      box.append(el("button", { class: "opt", type: "button", title: p.when, onclick: () => useTask(p.code) },
        el("span", { text: LABEL[p.code] || p.title }), el("small", { text: p.code })));
    }
  }
  const chips = $("#chips"); chips.replaceChildren();
  for (const c of HOME_TASKS) chips.append(el("button", { class: "chip", type: "button", text: LABEL[c], onclick: () => useTask(c) }));
}

function renderAddons() {
  const box = $("#addons"); box.replaceChildren();
  for (const a of S.guide.addons.filter((x) => x !== PLAN_ADDON)) {
    const id = "ad-" + box.children.length;
    const cb = el("input", { type: "checkbox", id, checked: S.addons.has(a),
      onchange: (e) => { e.target.checked ? S.addons.add(a) : S.addons.delete(a); saved.set("addons", [...S.addons]); } });
    box.append(el("label", { for: id }, cb, a));
  }
}

function setPlan(on) {
  S.plan = on; saved.set("plan", on);
  $("#planBtn").setAttribute("aria-pressed", String(on));
}
$("#planBtn").onclick = () => setPlan(!S.plan);

/* ------------------------------------------------------------------ video */
const fmtDur = (s) => { s = Math.round(s || 0); const m = Math.floor(s / 60); return m ? `${m}:${String(s % 60).padStart(2, "0")}` : `${s} sn`; };

async function setVideo(path) {
  if (!path) return;
  if (openPop === $("#videoPop")) closePop();  // not the delete confirmation, say
  const strip = $("#strip"); strip.hidden = !!S.job; strip.className = "strip loading";
  strip.replaceChildren(el("div", { class: "cap" }, el("span", { text: "Okunuyor…" })));
  try {
    const v = await api(`/api/probe?path=${encodeURIComponent(path)}`);
    S.video = v; saved.set("video", v.path);
    const facts = v.is_dir ? `${v.videos} video` : `${fmtDur(v.duration)} · ${v.width}×${v.height}`;
    const img = el("img", { alt: "" });
    strip.className = v.is_dir ? "strip folder" : "strip loading";
    strip.replaceChildren(img, el("div", { class: "cap" },
      el("b", { text: v.is_dir ? v.display : v.name }), el("span", { text: facts }),
      el("button", { class: "rm", type: "button", title: "Kaldır", text: "✕", onclick: clearVideo })));
    $("#videoBtn").classList.add("set");
    if (!v.is_dir) {
      api(`/api/sheet?path=${encodeURIComponent(v.path)}`).then((d) => {
        img.src = `${d.url}&token=${encodeURIComponent(TOKEN)}`; strip.classList.remove("loading");
      }).catch(() => strip.classList.remove("loading"));
    }
    if (S.task && !S.job) useTask(S.task);
  } catch (e) {
    S.video = null; strip.hidden = true; toast(`Açılamadı: ${e.message}`);
  }
}
function clearVideo() {
  S.video = null; saved.set("video", null); $("#strip").hidden = true; $("#videoBtn").classList.remove("set");
}

async function pick(kind) {
  closePop();
  try { const { path } = await post("/api/pick", { kind }); if (path) setVideo(path); }
  catch (e) { toast(e.message); }
}
$("#pickFile").onclick = () => pick("file");
$("#pickFolder").onclick = () => pick("folder");
$("#pathInput").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); setVideo(e.target.value.trim()); } });

async function loadLibrary() {
  const box = $("#library"); box.replaceChildren();
  try {
    for (const g of await api("/api/library")) {
      box.append(el("h3", { text: g.display }));
      box.append(el("button", { class: "opt", type: "button", onclick: () => setVideo(g.path) }, el("span", { text: "Klasörün tamamı" })));
      for (const f of g.files) box.append(el("button", { class: "opt", type: "button", onclick: () => setVideo(f.path) }, el("span", { text: f.name })));
    }
  } catch { /* the picker still works */ }
}
$("#videoBtn").onclick = (e) => { loadLibrary(); showPop($("#videoPop"), e.currentTarget); };
$("#taskBtn").onclick = (e) => showPop($("#taskPop"), e.currentTarget);
$("#moreBtn").onclick = (e) => showPop($("#morePop"), e.currentTarget);
// Agent: Claude Code or Codex. Each keeps its own model and permission choice.
const PERMS = {
  claude: [{ id: "acceptEdits", label: "Güvenli: izin listesi" }, { id: "auto", label: "Otomatik: auto mode" }],
  codex: [{ id: "acceptEdits", label: "Güvenli: sandbox" }, { id: "bypassPermissions", label: "Tam yetki: sandbox yok" }],
};
const RETENTION_LABEL = (d) => (d ? `${d} gün sonra sil` : "Hep sakla");
const engine = () => $("#engine").value;
const key = (k) => (engine() === "claude" ? k : `${engine()}.${k}`);
function syncEngine() {
  const e = (S.engines || []).find((x) => x.id === engine());
  fillSelect($("#permMode"), PERMS[engine()], saved.get(key("perm"), "acceptEdits"));
  if (e) fillSelect($("#model"), e.models, saved.get(key("model"), e.default_model));
  syncEffort();
}
// The effort list is the chosen model's own (Haiku has none; Codex models go up to "ultra").
function syncEffort() {
  const e = (S.engines || []).find((x) => x.id === engine());
  if (!e) return;
  const m = e.models.find((x) => x.id === $("#model").value);
  const levels = m && Array.isArray(m.efforts) ? m.efforts : e.efforts || ["high", "xhigh", "max"];
  const sel = $("#effort");
  sel.disabled = !levels.length;
  if (!levels.length) { sel.replaceChildren(el("option", { value: "", text: "Bu modelde yok" })); return; }
  const want = saved.get("effort", "xhigh");
  const order = ["low", "medium", "high", "xhigh", "max", "ultra"];
  const fit = levels.includes(want) ? want : levels.filter((x) => order.indexOf(x) <= order.indexOf(want)).pop() || levels[0];
  fillSelect(sel, levels.map((x) => ({ id: x, label: EFFORT_LABEL[x] || x })), fit);
}
$("#engine").value = saved.get("engine", "claude");
$("#engine").onchange = (e) => {
  const ok = (S.engines || []).find((x) => x.id === e.target.value);
  if (ok && !ok.available) toast(`${ok.label} bu bilgisayarda bulunamadı`);
  saved.set("engine", e.target.value); syncEngine();
};
$("#permMode").onchange = (e) => saved.set(key("perm"), e.target.value);
$("#model").onchange = (e) => { saved.set(key("model"), e.target.value); syncEffort(); };
$("#effort").onchange = (e) => saved.set("effort", e.target.value);
// An open job's effort, also while it runs: Claude takes it at its next step, Codex next turn.
function syncJobEffort() {
  const job = S.job, box = $("#effortTool");
  const e = job && (S.engines || []).find((x) => x.id === (job.engine || "claude"));
  const m = e && e.models.find((x) => x.id === (job.model || e.default_model || ""));
  const levels = m && Array.isArray(m.efforts) ? m.efforts : (e && e.efforts) || [];
  box.hidden = !job || !job.effort || !levels.length;  // Haiku has no levels
  if (box.hidden) return;
  const order = ["low", "medium", "high", "xhigh", "max", "ultra"];
  const cur = levels.includes(job.effort) ? job.effort
    : levels.filter((x) => order.indexOf(x) <= order.indexOf(job.effort)).pop() || levels[0];
  fillSelect($("#jobEffort"), levels.map((x) => ({ id: x, label: EFFORT_LABEL[x] || x })), cur);
}
$("#jobEffort").onchange = async (e) => {
  const job = S.job, want = e.target.value;
  if (!job) return;
  try {
    const r = await post(`/api/jobs/${job.id}/effort`, { effort: want });
    job.effort = want;
    toast(`Efor: ${EFFORT_LABEL[want] || want}, ${r.when === "now" ? "bir sonraki adımdan" : "sonraki turdan"} itibaren`);
  } catch (err) { toast(err.message); syncJobEffort(); }
};
$("#retention").onchange = async (e) => {
  try {
    await post("/api/settings", { retention_days: +e.target.value });
    toast(RETENTION_LABEL(+e.target.value)); refreshJobs();
  } catch (err) { toast(err.message); }
};
// Build intermediates (base.mov ...) of variants nobody built for N days: deleted hourly when set,
// or now with the button (two clicks). The footer shows the free space only when it runs low.
const CLEAN_LABEL = (d) => (d ? `${d} gün derlenmeyince sil` : "Elle temizle");
const GB = (n) => `${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)} GB`;
async function loadDisk() {
  let d;
  try { d = await api("/api/disk"); } catch { return; }
  const warn = $("#diskWarn");
  warn.hidden = d.free >= d.low;
  warn.textContent = `Disk: ${GB(d.free)} boş`;
  $("#diskInfo").textContent = `${GB(d.free)} boş. ` + (d.cleanable
    ? `${d.days} gündür derlenmeyen varyantlarda ${GB(d.cleanable)} ara dosya var; teslim videoları kalır.`
    : `${d.days} gündür derlenmeyen varyantta ara dosya yok.`);
  const b = $("#cleanBtn");
  b.hidden = !d.cleanable; b.classList.remove("danger"); b.dataset.armed = "";
  b.textContent = `${GB(d.cleanable)} temizle`;
  b.onclick = async () => {
    if (!b.dataset.armed) { b.dataset.armed = "1"; b.classList.add("danger"); b.textContent = "Emin misin? Tekrar tıkla"; return; }
    b.disabled = true;
    try { const r = await post("/api/disk/clean", { days: d.days }); toast(`${GB(r.freed)} açıldı`); }
    catch (err) { toast(err.message); }
    b.disabled = false; loadDisk();
  };
}
setInterval(loadDisk, 5 * 60 * 1000);
$("#diskWarn").onclick = () => openSettings("storage");
$("#cleanDays").onchange = async (e) => {
  try { await post("/api/settings", { clean_days: +e.target.value }); toast(CLEAN_LABEL(+e.target.value)); loadDisk(); }
  catch (err) { toast(err.message); }
};
const EFFORT_LABEL = { low: "Düşük", medium: "Orta", high: "Yüksek", xhigh: "Extra high", max: "Maks", ultra: "Ultra" };
function fillSelect(sel, items, current) {
  sel.replaceChildren(...items.map((x) => el("option", { value: x.id, text: x.label, title: x.description || null })));
  sel.value = items.some((x) => x.id === current) ? current : items[0].id;
}

/* ------------------------------------------------------------------ send */
// Only what the user chose: a level, the layers turned off ("yok"), a note. A layer left on is
// not an order to add it (a gap cut must not come back with music).
function cutLine() {
  const c = S.cut;
  const parts = c.level === "yok" ? [] : [`kaba kesim ${c.level}`];
  for (const [k, name] of [["captions", "altyazı"], ["music", "müzik"], ["sfx", "ses efekti"]]) if (!c[k]) parts.push(`${name} yok`);
  if (c.note.trim()) parts.push(`ince kesim: ${c.note.trim()}`);
  if (!parts.length) return null;
  return `Kurgu ayarı (kesim içeren işlerde uygula, planda tek satırla teyit et): ${parts.join(", ")}.`;
}
function buildPrompt() {
  let text = input.value.trim();
  const v = S.video;
  if (v && !text.includes(v.display) && !text.includes(v.path)) text += `\n\nKaynak: ${v.display}`;
  const extra = [S.plan ? PLAN_ADDON : null, cutLine(), ...S.addons].filter(Boolean);
  if (extra.length) text += "\n\nEk talimatlar:\n" + extra.map((x) => `- ${x}`).join("\n");
  return text;
}
// Kurgu: the three settling rounds as one saved preset (rough cut, finishes, fine-cut note).
const CUT_LEVELS = [
  { id: "temkinli", label: "Temkinli", hint: "Sadece ölü boşluklar" },
  { id: "dengeli", label: "Dengeli", hint: "Duraklar ve dolgular" },
  { id: "sert", label: "Sert", hint: "Sıkı jump cut" },
  { id: "yok", label: "Belirtme", hint: "Ayar eklenmez" },
];
function syncCut() {
  saved.set("cut", S.cut);
  const lv = CUT_LEVELS.find((x) => x.id === S.cut.level) || CUT_LEVELS[1];
  $("#cutBtn").textContent = S.cut.level === "yok" ? "Kurgu" : `Kurgu: ${lv.label.toLowerCase()}`;
  $("#cutBtn").classList.toggle("set", S.cut.level !== "yok");
  for (const b of $("#cutLevels").children) b.setAttribute("aria-pressed", String(b.dataset.id === S.cut.level));
  for (const k of ["captions", "music", "sfx"]) $(`#cut-${k}`).checked = !!S.cut[k];
  $("#cutNote").value = S.cut.note || "";
}
function renderCut() {
  $("#cutLevels").replaceChildren(...CUT_LEVELS.map((x) => el("button", { class: "seg", type: "button", "data-id": x.id, title: x.hint,
    onclick: () => { S.cut.level = x.id; syncCut(); } }, el("b", { text: x.label }), el("small", { text: x.hint }))));
  for (const k of ["captions", "music", "sfx"]) $(`#cut-${k}`).onchange = (e) => { S.cut[k] = e.target.checked; syncCut(); };
  $("#cutNote").oninput = (e) => { S.cut.note = e.target.value; saved.set("cut", S.cut); };
  syncCut();
}
$("#cutBtn").onclick = (e) => showPop($("#cutPop"), e.currentTarget);
function titleFor() {
  const first = input.value.trim().split("\n")[0];
  const what = S.task ? LABEL[S.task] : first.length > 42 ? first.slice(0, 40) + "…" : first;
  return S.video ? `${what} · ${S.video.name}` : what;
}

async function submit() {
  const files = (S.att || []).map((a) => a.path);
  if (!input.value.trim() && !files.length) return input.focus();
  const btn = $("#sendBtn"); btn.disabled = true;
  try {
    if (S.job) {
      const r = await post(`/api/jobs/${S.job.id}/send`, { prompt: input.value.trim(), attachments: files });
      input.value = ""; saved.set(draftKey(), ""); autosize();
      S.att = []; saveAtts();
      if (r.queued) toast(S.job.engine === "codex" ? "Sıraya eklendi: bu adım bitince gönderilecek" : "İletildi: Claude bir sonraki adımda alacak");
      else { S.job.status = "running"; syncControls(); stream(S.job.id); }
      refreshJobs();
    } else {
      if (!input.value.trim()) input.value = "Ekteki dosyalara bak.";
      const { id } = await post("/api/jobs", { prompt: buildPrompt(), title: titleFor(), video: S.video ? S.video.path : null,
        attachments: files,
        permission_mode: $("#permMode").value, model: $("#model").value || null, effort: $("#effort").value || null,
        engine: engine() });
      input.value = ""; saved.set("draft", ""); S.task = null;
      clearVideo();  // the attachments went with this job: the next new chat starts empty
      S.att = []; saveAtts();
      $("#taskBtn").textContent = "Görev"; $("#taskBtn").classList.remove("set");
      await refreshJobs(); await openJob(id);
    }
  } catch (e) { toast(e.message); }
  finally { btn.disabled = false; checkFill(); }
}
$("#stopBtn").onclick = () => S.job && post(`/api/jobs/${S.job.id}/stop`).catch((e) => toast(e.message));

/* ------------------------------------------------------------------ history */
function dayLabel(ts) {
  const d = new Date(ts * 1000), now = new Date();
  const days = Math.round((new Date(now.toDateString()) - new Date(d.toDateString())) / 864e5);
  return days === 0 ? "Bugün" : days === 1 ? "Dün" : "Daha önce";
}
const cleanTitle = (t) => String(t).replace(/^[A-Z]\d+\s·\s/, "");
const PIN_SVG = '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><path fill="currentColor" d="M10.3 1.3a1 1 0 0 1 1.4 0l3 3a1 1 0 0 1 0 1.4l-.9.9a1 1 0 0 1-1 .25L10.6 9l.2 2.4a1 1 0 0 1-.3.8l-.6.6a.5.5 0 0 1-.7 0L6.7 10.3 3 14a.7.7 0 0 1-1-1l3.7-3.7-2.5-2.5a.5.5 0 0 1 0-.7l.6-.6a1 1 0 0 1 .8-.3l2.4.2 2.1-2.2a1 1 0 0 1 .25-1z"/></svg>';
async function refreshJobs() {
  const before = new Set((S.jobs || []).filter((j) => j.status === "running").map((j) => j.id));
  S.jobs = await api("/api/jobs");
  if (document.hidden && S.jobs.some((j) => before.has(j.id) && j.status !== "running")) finishedUnseen = true;
  syncTitle();
  const nav = $("#history"); nav.replaceChildren();
  let last = "";
  const jobs = [...S.jobs.filter((j) => j.pinned), ...S.jobs.filter((j) => !j.pinned)];
  if (!saved.get("seenInit", false)) {  // first run: what already exists counts as read
    saved.set("seen", Object.fromEntries(S.jobs.map((j) => [j.id, j.updated])));
    saved.set("seenInit", true);
  }
  const seenMap = saved.get("seen", {});
  for (const j of jobs) {
    const day = j.pinned ? "Sabit" : dayLabel(j.updated);
    if (day !== last) { nav.append(el("h2", { text: day })); last = day; }
    const codexTag = j.engine === "codex" ? el("span", { class: "eng", text: "Codex" }) : null;
    const open = S.job && S.job.id === j.id;
    if (open) seenNow(j);
    const unread = !open && j.status !== "running" && j.updated > (seenMap[j.id] || 0) + 1;
    nav.append(el("div", { class: `item${open ? " on" : ""}${j.pinned ? " pinned" : ""}${unread ? " unread" : ""}`, role: "button", tabindex: "0",
      title: j.title, onclick: () => openJob(j.id), onkeydown: (e) => { if (e.key === "Enter") openJob(j.id); } },
      el("span", { class: `dot ${j.status}` }), el("span", { class: "t" }, cleanTitle(j.title), codexTag),
      el("span", { class: "acts" },
        el("button", { class: "pin", type: "button", title: j.pinned ? "Sabitlemeyi kaldır" : "Sabitle: hiç silinmez",
          "aria-pressed": j.pinned ? "true" : "false", html: PIN_SVG, onclick: (e) => { e.stopPropagation(); pinJob(j); } }),
        el("button", { class: "x", type: "button", title: "Sil (özeti video klasöründe kalır)", text: "✕",
          "aria-haspopup": "true", onclick: (e) => { e.stopPropagation(); removeJob(j, e.currentTarget); } }))));
  }
}
async function pinJob(j) {
  try { await post(`/api/jobs/${j.id}/pin`, { pinned: !j.pinned }); refreshJobs(); } catch (e) { toast(e.message); }
}
function removeJob(j, anchor) {
  if (j.status === "running") return toast("Önce durdur");
  const pop = $("#confirmPop");
  $("#confirmText").textContent = `"${cleanTitle(j.title)}" silinsin mi?`;
  $("#confirmYes").onclick = () => { closePop(); deleteJob(j); };
  $("#confirmNo").onclick = closePop;
  showPop(pop, anchor);
  $("#confirmNo").focus();
}
async function deleteJob(j) {
  try {
    const r = await post(`/api/jobs/${j.id}/delete`);
    try { localStorage.removeItem(`vk-draft:${j.id}`); } catch { /* private mode */ }
    if (S.job && S.job.id === j.id) goHome();
    toast(r.note ? "Silindi, özeti VLOGKIT-NOTLAR.md dosyasında" : "Silindi");
    refreshJobs();
  } catch (e) { toast(e.message); }
}

/* ------------------------------------------------------------------ views */
const COMPOSE_TOOLS = ["videoBtn", "taskBtn", "planBtn", "cutBtn", "moreBtn"];
// Licenses of the third-party media in this chat's videos (from each build's timeline data): the
// card at the top right keeps the dispute text one click away when a platform claims the music.
const lic = { byVideo: new Map(), open: null };
function resetLicenses() { lic.byVideo.clear(); drawLicenses(); }
function addLicenses(video, data) {
  const same = lic.byVideo.get(video);
  if (same && JSON.stringify(same) === JSON.stringify(data)) return;  // a poll, nothing new
  lic.byVideo.delete(video);
  lic.byVideo.set(video, data);  // the latest video last
  drawLicenses();
}
function drawLicenses() {
  const box = $("#licPanel");
  const all = [...lic.byVideo.entries()].reverse();
  box.hidden = !all.length;
  if (!all.length) return;
  // open by default only when it fits beside the conversation (820 px) without covering it
  if (lic.open === null) lic.open = ($("#main").clientWidth - 820) / 2 >= 320;
  box.classList.toggle("folded", !lic.open);
  const total = all.reduce((n, [, d]) => n + d.items.length, 0);
  const head = el("button", { class: "lic-head", type: "button", "aria-expanded": String(lic.open),
    onclick: () => { lic.open = !lic.open; drawLicenses(); } },
    el("span", { text: "Lisanslar" }), el("span", { class: "lic-n", text: String(total) }));
  const body = el("div", { class: "lic-body", hidden: !lic.open });
  all.forEach(([video, d], k) => {
    const list = el("ul", {}, d.items.map((x) => el("li", {},
      /^https?:\/\//i.test(x.page || "") ? el("a", { href: x.page, target: "_blank", rel: "noopener", text: x.id, title: x.description || x.id })
        : el("span", { text: x.id, title: x.description || x.id }),
      el("small", { text: `${x.author} · ${x.license}${x.checked ? ` · ${x.checked}` : ""}` }))));
    const acts = el("div", { class: "lic-acts" },
      el("button", { class: "tool", type: "button", text: "İtiraz metnini kopyala", onclick: async () => {
        try { await navigator.clipboard.writeText(d.dispute); toast("İtiraz metni kopyalandı"); }
        catch { toast("Kopyalanamadı: dosyadaki metni kullan"); }
      } }),
      d.file ? el("button", { class: "tool", type: "button", text: "Dosya", title: d.file, onclick: () => reveal(d.file) }) : null);
    const sec = el("details", { open: k === 0 }, el("summary", { text: base(video) }), list, acts);
    body.append(sec);
  });
  box.replaceChildren(head, body);
}
function goHome() {
  resetLicenses();
  if (S.es) { S.es.close(); S.es = null; }
  S.job = null; history.replaceState(null, "", location.pathname);
  showQueue([]);
  loadAtts();
  $("#main").classList.add("home");
  $("#thread").replaceChildren();
  input.value = saved.get("draft", ""); input.placeholder = "Ne yapılsın? Örn: bu videoyu Short'a çevir";
  for (const id of COMPOSE_TOOLS) $("#" + id).hidden = false;
  $("#effortTool").hidden = true;
  $("#strip").hidden = !S.video; $("#stopBtn").hidden = true; $("#sendBtn").disabled = false;
  autosize(); checkFill(); refreshJobs().catch(() => {}); input.focus();
}
$("#newJob").onclick = goHome;

async function openJob(id) {
  if (S.es) { S.es.close(); S.es = null; }
  let job;
  try { job = await api(`/api/jobs/${id}`); } catch { return goHome(); }
  S.job = job; S.seen = 0; S.turns = []; rows.clear(); resetLicenses();
  history.replaceState(null, "", `#${id}`);
  $("#main").classList.remove("home");
  const th = $("#thread"); th.replaceChildren(el("div", { class: "thread-inner", id: "threadInner" }));
  for (const ev of job.events) render(ev);
  S.seen = job.events.length;
  input.value = saved.get(draftKey(), ""); input.placeholder = "Yanıt yaz: onay, düzeltme, yeni istek…";
  seenNow(job);
  showQueue(job.queue || []);
  loadAtts();
  for (const bid of COMPOSE_TOOLS) $("#" + bid).hidden = true;
  syncJobEffort();
  $("#strip").hidden = true; $("#fill").hidden = true;
  autosize(); syncControls(); refreshJobs().catch(() => {});
  stick = true; toBottom();
  if (job.status === "running") stream(id);
}

function syncControls() {
  const running = !!(S.job && S.job.status === "running");
  $("#stopBtn").hidden = !running;
  $("#sendBtn").disabled = false;
  $("#sendLabel").textContent = running ? "Sıraya ekle" : "Gönder";
  $("#sendBtn").title = !running ? "Enter ile gönder · Shift+Enter yeni satır"
    : S.job.engine === "codex" ? "Çalışan adım bitince gönderilir (Enter)" : "Claude bir sonraki adımda alır (Enter)";
  if (S.job) showQueue(S.job.queue || []);
  $("#thread").classList.toggle("busy", running);
  const lastTurn = S.turns[S.turns.length - 1];
  for (const t of S.turns) if (t && t.steps) t.steps.classList.toggle("live", running && t === lastTurn);
}

function stream(id) {
  if (S.es) S.es.close();
  const es = new EventSource(`/api/jobs/${id}/events?after=${S.seen}&token=${encodeURIComponent(TOKEN)}`);
  S.es = es;
  es.onmessage = (m) => {
    if (!S.job || S.job.id !== id) return es.close();
    const ev = JSON.parse(m.data);
    if (ev.i < S.seen) return;
    S.seen = ev.i + 1; render(ev);
  };
  es.addEventListener("end", () => { es.close(); S.es = null; refreshJobs().catch(() => {}); });
  // the job was rewritten elsewhere (a message edited in another tab): draw it again
  es.addEventListener("reset", () => { es.close(); S.es = null; if (S.job && S.job.id === id) openJob(id); });
  es.onerror = () => { es.close(); S.es = null; setTimeout(() => { if (S.job && S.job.id === id && S.job.status === "running") stream(id); }, 2000); };
}

/* ------------------------------------------------------------------ thread rendering */
const rows = new Map();
function turn(i) {
  if (!S.turns[i]) {
    const root = el("div", { class: "turn" });
    $("#threadInner").append(root);
    S.turns[i] = { root, steps: null, list: null, peek: null, n: 0, start: 0, since: 0 };
  }
  return S.turns[i];
}
// A running turn: the folded step list, and under it a "peek" with Claude's latest note and the
// step running right now (replaced in place, so the screen shows progress without scrolling).
function stepsOf(t) {
  if (!t.steps) {
    t.sum = el("span", { class: "sum" });
    t.list = el("div", { class: "step-list" });
    t.steps = el("details", { class: "steps live" }, el("summary", {}, t.sum), t.list);
    t.pnote = el("div", { class: "pnote", hidden: true });
    t.pdot = el("span", { class: "pdot" });
    t.pname = el("span", { class: "pname" });
    t.ptext = el("span", { class: "ptext" });
    t.ptick = el("span", { class: "ptick" });
    t.peek = el("div", { class: "peek", "aria-live": "polite" }, t.pnote,
      el("div", { class: "pstep" }, t.pdot, t.pname, t.ptext, t.ptick));
    t.root.append(t.steps, t.peek);
  }
  return t;
}

// Headless mode hides the thinking text itself, so the peek shows the state and how long it lasts.
const ACTIVITY = { thinking: "Düşünüyor…", writing: "Yazıyor…" };
function setNow(t, name, text, ts, state = "run") {
  stepsOf(t);
  if (!t.peek) return;
  t.pname.textContent = name; t.pname.hidden = !name;
  t.ptext.textContent = text;
  t.peek.dataset.state = state;
  t.since = ts || Date.now() / 1000; t.stepDone = false; tickLive();
}
function setNote(t, text) {
  stepsOf(t);
  if (!t.peek) return;
  const first = text.trim().split("\n").filter(Boolean).slice(0, 3).join(" ");
  t.pnote.textContent = first.length > 260 ? first.slice(0, 260) + "…" : first;
  t.pnote.hidden = !first;
}
function finishTurn(t, label) {
  if (!t.steps || t.done) return;
  t.done = label !== undefined;  // the result's "N adım · 1:39" must survive the status event after it
  t.steps.classList.remove("live");
  if (t.peek) { t.peek.remove(); t.peek = null; }
  if (!t.n && !t.list.childElementCount && !label) { t.steps.remove(); t.steps = null; return; }
  t.sum.textContent = label ?? (t.n ? `${t.n} adım` : "");
}
function liveTurn() {
  if (!S.job || S.job.status !== "running") return null;
  const t = S.turns[S.turns.length - 1];
  return t && t.peek ? t : null;
}
function tickLive() {
  const t = liveTurn();
  if (!t) return;
  const now = Date.now() / 1000;
  t.sum.textContent = [t.n ? `${t.n} adım` : "Çalışıyor", fmtDur(now - (t.start || t.since))].join(" · ");
  const s = now - t.since;
  if (!t.stepDone) t.ptick.textContent = s >= 3 ? fmtDur(s) : "";
}
setInterval(tickLive, 1000);

let stick = true;
$("#thread").addEventListener("scroll", (e) => {
  const th = e.currentTarget; stick = th.scrollHeight - th.scrollTop - th.clientHeight < 120;
});
const toBottom = () => { if (stick) $("#thread").scrollTop = $("#thread").scrollHeight; };

function render(ev) {
  if (!$("#threadInner")) return;
  const t = turn(ev.turn ?? 0);
  switch (ev.kind) {
    case "user": {
      const lines = ev.text.split("\n").length;
      const box = el("div", { class: `me${lines > 5 ? " clamp" : ""}${ev.live ? " live" : ""}` }, el("pre", { text: ev.text }));
      if (ev.live) box.append(el("small", { class: "me-note", text: "İş sürerken eklendi" }));
      if (ev.files && ev.files.length) box.append(el("div", { class: "me-files" }, ev.files.map((f) =>
        f.kind === "image"
          ? el("img", { src: media(f.path), alt: "", title: f.path, onclick: () => openLight(media(f.path)) })
          : el("span", { class: "file-chip", title: f.path, text: f.path.split("/").pop() }))));
      if (lines > 5) box.append(el("button", { class: "more", type: "button", text: "Tamamını göster",
        onclick: (e) => { box.classList.remove("clamp"); e.currentTarget.remove(); } }));
      // a message that started a turn can be rewritten; one added mid-run belongs to that turn
      if (!ev.live) box.append(el("button", { class: "me-edit", type: "button", text: "Düzenle",
        title: "Bu mesajı değiştir ve konuşmayı buradan sürdür", onclick: () => editMessage(box, ev) }));
      t.root.append(box); break;
    }
    case "system":
      if (ev.session_id && S.job) S.job.session_id = ev.session_id;
      if (!ev.label) {  // notices: usage limit, a fresh session after an expired one, Codex errors
        if (ev.text && !ev.session_id) t.root.insertBefore(el("div", { class: "meta", text: ev.text }), t.steps);
        break;
      }
      // right under the user's message, above the live steps
      t.root.insertBefore(el("div", { class: "runinfo", text: [ev.label, EFFORT_LABEL[S.job && S.job.effort] || ""].filter(Boolean).join(" · ") }), t.steps);
      break;
    case "activity":
      if (ev.state === "tool") setNow(t, ev.name || "Araç", "hazırlanıyor…", ev.ts);
      else setNow(t, "", ACTIVITY[ev.state] || "", ev.ts, ev.state);
      return;
    case "text":
      t.lastNote = el("div", { class: "step-note", text: ev.text.length > 280 ? ev.text.slice(0, 280) + "…" : ev.text });
      t.lastText = ev.text;
      stepsOf(t).list.append(t.lastNote);
      setNote(t, ev.text);
      break;
    case "tool": {
      stepsOf(t); t.n += 1;
      const s = el("span", { class: "s", text: "•" });
      const first = (ev.summary || "").split("\n")[0];
      t.list.append(el("div", { class: "step", title: ev.summary || "" }, s, el("span", { class: "n", text: ev.name }), el("code", { text: first })));
      rows.set(ev.id, s);
      t.curTool = ev.id;
      setNow(t, ev.name, first.slice(0, 200) || "…", ev.ts);
      break;
    }
    case "tool_result": {
      const s = rows.get(ev.id);
      if (s) { s.textContent = ev.ok ? "✓" : "✗"; s.className = `s ${ev.ok ? "ok" : "bad"}`; if (!ev.ok) s.parentElement.title = ev.preview; }
      if (t.peek && t.curTool === ev.id) { t.peek.dataset.state = ev.ok ? "ok" : "bad"; t.stepDone = true; }
      return;
    }
    case "result": {
      // the final message also arrives as a normal text event: don't show it twice
      if (t.lastNote && t.lastText && ev.text.trim().startsWith(t.lastText.trim().slice(0, 80))) t.lastNote.remove();
      const dur = ev.duration_ms ? fmtDur(ev.duration_ms / 1000) : "";
      finishTurn(t, [t.n ? `${t.n} adım` : "", dur].filter(Boolean).join(" · "));
      const { rest: text, choices } = splitChoices(stripOutputs(ev.text));
      const { rest, ideas } = splitSuggestions(text);
      t.root.append(el("div", { class: "answer md", html: md(rest) }));
      for (const c of choices) t.root.append(choiceCard(c));
      t.choicePaths = new Set(choices.flatMap((c) => c.items.map((it) => it.path).filter(Boolean)));
      for (const idea of ideas) t.root.append(suggestion(idea));
      if (!ev.ok) t.root.append(el("div", { class: "meta", text: `Bitmedi: ${ev.subtype || "hata"}` }));
      break;
    }
    case "queue":
      if (S.job) S.job.queue = ev.items;
      showQueue(ev.items || []);
      return;
    case "outputs": {  // the previews of a choice are already on its cards
      const files = ev.files.filter((f) => !(t.choicePaths && t.choicePaths.has(f.path)));
      if (files.length) t.root.append(outputs(files));
      break;
    }
    case "error": t.root.append(el("div", { class: "err", text: ev.text })); break;
    case "status":
      if (ev.status === "running") { if (!t.steps) { t.start = ev.ts; setNow(t, "", "Başlıyor…", ev.ts, "thinking"); } }
      else finishTurn(t);
      if (S.job) { S.job.status = ev.status; syncControls(); }
      if (ev.status !== "running") refreshJobs().catch(() => {});
      break;
    default: return;
  }
  toBottom();
}

// Rewriting a sent message: the turns after it are set aside (kept in the job file) and the
// agent goes on from here in a fresh session. Files it changed are not undone; it is told which.
function editMessage(box, ev) {
  if (!S.job || S.job.status === "running") return toast("Önce işi durdur");
  const id = S.job.id;
  const ta = el("textarea", { class: "me-input", rows: 3 });
  ta.value = ev.text;
  const send = async () => {
    const prompt = ta.value.trim();
    if (!prompt) return ta.focus();
    try {
      await post(`/api/jobs/${id}/edit`, { turn: ev.turn, prompt, attachments: (ev.files || []).map((f) => f.path) });
    } catch (e) { return toast(e.message); }
    openJob(id);
  };
  ta.onkeydown = (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
    if (e.key === "Escape") cancel();
  };
  const old = [...box.childNodes];
  const cancel = () => { box.classList.remove("editing"); box.replaceChildren(...old); };
  box.classList.add("editing");
  box.replaceChildren(ta,
    el("small", { class: "me-note", text: "Sonraki mesajlar ayrılır; dosya değişiklikleri geri alınmaz." }),
    el("div", { class: "me-actions" },
      el("button", { type: "button", class: "ghost", text: "Vazgeç", onclick: cancel }),
      el("button", { type: "button", class: "primary", text: "Gönder", onclick: send })));
  ta.style.height = Math.min(ta.scrollHeight + 4, 320) + "px";
  ta.focus(); ta.setSelectionRange(ta.value.length, ta.value.length);
}

// Messages written while a turn runs wait here (like Claude Code); they go out together next.
function showQueue(items) {
  const box = $("#queue");
  box.replaceChildren();
  box.hidden = !items.length;
  if (!items.length) return;
  const running = !!(S.job && S.job.status === "running");
  items.forEach((item, i) => box.append(el("div", { class: `qitem${item.sent ? " sent" : ""}` },
    el("span", { class: "k", text: item.sent ? "İletildi" : "Sırada",
      title: item.sent ? "Claude çalışırken bir sonraki adımda alacak" : "Çalışan adım bitince gönderilecek" }),
    el("span", { class: "v", text: (typeof item === "string" ? item : item.text)
      + ((item.files || []).length ? `  (+${item.files.length} ek)` : "") }),
    // a message already written to Claude cannot be taken back
    item.sent ? null : el("button", { class: "x", type: "button", title: "Sıradan çıkar", text: "✕",
      onclick: () => post(`/api/jobs/${S.job.id}/queue/delete`, { index: i }).catch((e) => toast(e.message)) }))));
  if (!running) box.append(el("div", { class: "qnote" },
    el("span", { text: "Adım bitmeden durdu; sıradakiler bekliyor." }),
    el("button", { class: "tool", type: "button", text: "Şimdi gönder", onclick: async () => {
      try { await post(`/api/jobs/${S.job.id}/queue/send`); S.job.status = "running"; syncControls(); stream(S.job.id); }
      catch (e) { toast(e.message); } } })));
}

// "New answer" dot: a chat whose last activity is newer than the last time it was open.
function seenNow(job) {
  const seen = saved.get("seen", {});
  seen[job.id] = Date.now() / 1000;
  saved.set("seen", seen);
}

function reveal(path) { post("/api/reveal", { path }).catch((e) => toast(e.message)); }
function outputs(files) {
  const wrap = el("div", { style: "display:grid;gap:10px" });
  const isMedia = (f) => ["video", "image", "audio"].includes(f.kind);
  const visual = files.filter(isMedia), docs = files.filter((f) => !isMedia(f));
  if (visual.length) {
    const g = el("div", { class: "outs" });
    for (const f of visual) {
      const url = media(f.path);
      let body;
      if (f.kind === "video") body = el("video", { src: url, controls: true, preload: "metadata", playsinline: true, onloadedmetadata: toBottom });
      else if (f.kind === "audio") body = el("audio", { src: url, controls: true });
      else body = el("img", { src: url, alt: base(f.path), onload: toBottom, onclick: () => openLight(url) });
      const tile = el("div", { class: `tile${f.kind === "video" ? " wide" : ""}`, title: f.path }, body,
        el("div", { class: "row" }, el("a", { href: url, target: "_blank", rel: "noopener", text: base(f.path) }),
          el("button", { class: "rv", type: "button", text: "Finder", title: "Finder'da göster", onclick: () => reveal(f.path) })));
      if (f.kind === "video") tile.append(timelineFor(body, f.path));
      g.append(tile);
    }
    wrap.append(g);
  }
  if (docs.length) {
    wrap.append(el("div", { class: "files" }, docs.map((f) => el("span", { class: "file", title: f.path },
      el("a", { href: media(f.path), target: "_blank", rel: "noopener", text: base(f.path) }),
      el("button", { class: "rv", type: "button", text: "Finder", onclick: () => reveal(f.path) })))));
  }
  return wrap;
}
/* ------------------------------------------------------------------ timeline under a video */
// The edit as tracks (shots, texts, chapters, notes) under the player: a click plays that moment,
// "Bu ana yorum" writes "[01:23.4 · plan 12/40 · ...]" into the message, "Kelimeler" lists the
// spoken words; selected words become "Kes (çıktıda): ..." lines. Claude changes edit.py.
const TRACKS = ["chapters", "shots", "text", "notes"];
// rounded first: 59.96 is "01:00.0", never "00:60.0" (the agent parses these)
const stamp = (t, d = 1) => { const k = 10 ** d; t = Math.round(Math.max(0, t || 0) * k) / k; const m = Math.floor(t / 60); return `${String(m).padStart(2, "0")}:${(t - m * 60).toFixed(d).padStart(3 + d, "0")}`; };
function addLine(text) {
  const v = input.value;
  input.value = v + (v && !v.endsWith("\n") ? "\n" : "") + text;
  autosize(); saved.set(draftKey(), input.value); input.focus();
  input.selectionStart = input.selectionEnd = input.value.length;
}
function timelineFor(video, path) {
  const now = el("span", { class: "tl-now", text: stamp(0) });
  const note = el("span", { class: "tl-note", text: "Zaman çizelgesi hazırlanıyor…" });
  const rowsBox = el("div", { class: "tl-rows" });
  const wordsBox = el("div", { class: "tl-words", hidden: true });
  const wordsBtn = el("button", { class: "tool", type: "button", text: "Kelimeler", "aria-pressed": "false", title: "Konuşmayı kelime kelime göster: seçip kesilecekleri işaretle" });
  // Zoom: the lanes show a window [a, b] of the video; the thin overview above them shows the whole
  // video, the window (drag it) and the playhead. +/−, ⌘/ctrl + wheel or a pinch zoom around the
  // pointer, a double click zooms into that spot, shift + wheel or a sideways swipe pans.
  const fitBtn = el("button", { class: "tl-z", type: "button", text: "Tümü", hidden: true, title: "Bütün videoyu göster", onclick: () => setView(0, Infinity) });
  const zoomBox = el("span", { class: "tl-zoom", hidden: true },
    el("button", { class: "tl-z", type: "button", text: "−", "aria-label": "Uzaklaş", title: "Uzaklaş (⌘ + tekerlek)", onclick: () => zoom(1.6) }),
    el("button", { class: "tl-z", type: "button", text: "+", "aria-label": "Yakınlaş", title: "Yakınlaş (⌘ + tekerlek, çift tık)", onclick: () => zoom(1 / 1.6) }),
    fitBtn);
  const win = el("div", { class: "tl-win" }), miniPlay = el("div", { class: "tl-mini-play" });
  const mini = el("div", { class: "tl-mini", hidden: true, title: "Bütün video: pencereyi sürükle ya da bir yere tıkla" }, win, miniPlay);
  const box = el("div", { class: "tl" },
    el("div", { class: "tl-head" }, now, note, el("span", { class: "tl-acts" }, zoomBox,
      el("button", { class: "tool", type: "button", text: "Bu ana yorum", title: "Videonun şu anki zamanını ve o andaki planı mesaja ekler", onclick: comment }),
      wordsBtn)),
    mini,
    rowsBox,
    wordsBox);
  let data = null, words = null, sel = null, view = null, autoZoomed = false;
  const dur = () => (data && data.duration) || video.duration || 1;
  const span = () => view || [0, dur()];
  function setView(a, b) {
    if (!data) return;  // nothing to draw yet
    const d = dur(), w = Math.min(d, Math.max(4, b - a));
    if (w >= d - 1e-3) view = null;
    else { const s0 = Math.max(0, Math.min(d - w, a)); view = [s0, s0 + w]; }
    draw();
  }
  function zoom(f, at) {  // f < 1 zooms in; `at` (s) stays under the same spot
    const [a, b] = span(), w = Math.min(dur(), Math.max(4, (b - a) * f));
    const c = at ?? Math.min(b, Math.max(a, video.currentTime || 0));
    const k = (c - a) / (b - a || 1);
    setView(c - k * w, c - k * w + w);
  }
  const timeAt = (e, el0) => { const r = el0.getBoundingClientRect(), [a, b] = span(); return a + ((e.clientX - r.left) / r.width) * (b - a); };
  rowsBox.addEventListener("wheel", (e) => {
    if (!data) return;
    const lane = e.target.closest(".tl-lane");
    if ((e.ctrlKey || e.metaKey) && lane) { e.preventDefault(); zoom(Math.exp(e.deltaY * 0.01), timeAt(e, lane)); return; }
    const dx = e.deltaX || (e.shiftKey ? e.deltaY : 0);  // macOS turns shift+wheel into deltaX
    if (view && lane && dx && Math.abs(dx) >= Math.abs(e.shiftKey ? 0 : e.deltaY)) {
      e.preventDefault();
      const [a, b] = span(), r = lane.getBoundingClientRect();
      const dt = (dx / r.width) * (b - a);
      setView(a + dt, b + dt);
    }
  }, { passive: false });
  rowsBox.addEventListener("dblclick", (e) => { const lane = e.target.closest(".tl-lane"); if (lane) zoom(1 / 3, timeAt(e, lane)); });
  mini.addEventListener("pointerdown", (e) => {
    const r = mini.getBoundingClientRect(), d = dur(), [a, b] = span(), w = b - a;
    const at = ((e.clientX - r.left) / r.width) * d;
    const grab = at >= a && at <= b ? at - a : w / 2;  // drag the window by where it was taken
    const move = (ev) => { const t = ((ev.clientX - r.left) / r.width) * d; setView(t - grab, t - grab + w); };
    move(e);
    mini.setPointerCapture(e.pointerId);
    mini.onpointermove = move;
    mini.onpointerup = mini.onpointercancel = () => { mini.onpointermove = null; };
  });

  function find(id, t) {
    const tr = data && data.tracks.find((x) => x.id === id);
    return tr ? tr.items.filter((x) => x.t0 <= t && t < x.t1) : [];
  }
  function comment() {
    const t = video.currentTime || 0;
    const parts = [stamp(t)];
    const shots = data && data.tracks.find((x) => x.id === "shots");
    for (const x of find("shots", t)) parts.push(`plan ${x.label.split(" ")[0]}/${shots.items.length}`);
    for (const x of find("text", t).slice(0, 1)) parts.push(x.label.length > 50 ? x.label.slice(0, 50) + "…" : x.label);
    video.pause();
    addLine(`[${parts.join(" · ")}] `);
  }
  function seekTo(e, lane) {
    video.currentTime = Math.min(dur(), Math.max(0, timeAt(e, lane)));
  }
  // items that overlap in time go to the next sub-row (at most 3; the rest share the last one)
  function pack(items) {
    const ends = [];
    return items.map((x) => {
      let r = ends.findIndex((e) => e <= x.t0 + 1e-3);
      if (r < 0) r = ends.length < 3 ? ends.length : ends.indexOf(Math.min(...ends));
      ends[r] = Math.max(ends[r] ?? 0, x.t1);
      return r;
    });
  }
  function draw() {
    rowsBox.replaceChildren();
    const tracks = TRACKS.map((id) => data.tracks.find((x) => x.id === id)).filter((x) => x && x.items.length);
    const shotsTr = tracks.find((x) => x.id === "shots");
    if (!autoZoomed && !view && shotsTr && video.duration) {  // too many shots to read: start on a minute
      autoZoomed = true;
      const px = Math.max(300, (rowsBox.clientWidth || box.clientWidth || 760) - 72);
      if (px / shotsTr.items.length < 16 && dur() > 90) view = [0, 60];
    }
    const [a, b] = span(), w = b - a;
    for (const tr of tracks) {
      const sub = tr.id === "notes" ? tr.items.map(() => 0) : pack(tr.items);
      const n = Math.max(1, ...sub.map((r) => r + 1));
      const lane = el("div", { class: `tl-lane ${tr.id}`, style: `height:${4 + n * 16}px`, onclick: (e) => seekTo(e, lane) });
      tr.items.forEach((x, i) => {
        if (x.t1 < a || x.t0 > b) return;  // outside the window
        const left = ((x.t0 - a) / w) * 100, width = Math.max(((x.t1 - x.t0) / w) * 100, 0.35);
        const pos = `left:${left}%;top:${2 + sub[i] * 16}px` + (tr.id === "notes" ? "" : `;width:${width}%`);
        lane.append(el("div", { class: `tl-item${tr.id === "notes" ? " pt" : ""}${i % 2 ? " odd" : ""}`, style: pos,
          title: `${x.label} (${stamp(x.t0)}${x.t1 > x.t0 ? "–" + stamp(x.t1) : ""})`,
          text: tr.id === "shots" ? x.label.split(" ")[0] : tr.id === "notes" ? "" : x.label.replace(/^\w+: /, "") }));
      });
      lane.append(el("div", { class: "tl-play" }));
      rowsBox.append(el("div", { class: "tl-row" }, el("div", { class: "tl-label", text: tr.label }), lane));
    }
    rowsBox.hidden = !tracks.length;
    zoomBox.hidden = !tracks.length;
    mini.hidden = !view || !tracks.length;
    fitBtn.hidden = !view;
    if (view) Object.assign(win.style, { left: `${(a / dur()) * 100}%`, width: `${(w / dur()) * 100}%` });
    const shots = data.tracks.find((x) => x.id === "shots");
    note.textContent = data.stale ? "Video sonradan değişmiş: çizelge eski olabilir"
      : shots && shots.detected ? "Planlar videodan bulundu" : "";
    sync(false);
  }
  // Shots the build did not save are found only once the video is played (a full decode each:
  // opening a chat with many outputs must not start them all).
  let detecting = false;
  async function load(detect = false, tries = 0) {
    if (!box.isConnected && tries) return;  // the chat was closed
    try {
      const d = await api(`/api/timeline?path=${encodeURIComponent(path)}${detect ? "&detect=1" : ""}`);
      if (d.licenses && d.licenses.items && d.licenses.items.length && !d.stale && box.isConnected) addLicenses(path, d.licenses);
      if (d.tracks && d.tracks.length) { data = d; draw(); }
      if (d.status === "idle") {
        note.textContent = "Planlar: video oynayınca bulunur";
        if (!detecting) video.addEventListener("play", () => { detecting = true; load(true); }, { once: true });
      }
      if (d.status === "working") { note.textContent = "Planlar bulunuyor…"; return setTimeout(() => load(true, tries + 1), 2500); }
      if (d.status === "error") note.textContent = `Zaman çizelgesi yok: ${d.error}`;
    } catch (e) { note.textContent = ""; }
  }
  // follow: while playing or after a seek the window keeps the playhead in view; a window the user
  // moved by hand while paused stays where it is
  function sync(follow = !video.paused) {
    const t = Math.min(video.currentTime || 0, dur());
    now.textContent = stamp(t);
    if (follow && view && data && (t < view[0] || t > view[1])) {
      const w = view[1] - view[0];
      return setView(t - w * 0.1, t + w * 0.9);
    }
    const [a, b] = span();
    for (const pl of rowsBox.querySelectorAll(".tl-play")) { pl.style.left = `${((t - a) / (b - a)) * 100}%`; pl.hidden = t < a || t > b; }
    miniPlay.style.left = `${(t / dur()) * 100}%`;
    if (words && !wordsBox.hidden) {
      for (const sp of wordsBox.querySelectorAll(".w.cur")) sp.classList.remove("cur");
      const k = words.findIndex((w) => w.t0 <= t && t < w.t1);
      if (k >= 0) wordsBox.querySelector(`[data-k="${k}"]`)?.classList.add("cur");
    }
  }
  let raf = 0;
  const loop = () => { sync(); raf = video.paused ? 0 : requestAnimationFrame(loop); };
  video.addEventListener("play", () => { if (!raf) raf = requestAnimationFrame(loop); });
  video.addEventListener("seeked", () => sync(true));
  video.addEventListener("timeupdate", () => { if (!raf) sync(); });
  video.addEventListener("loadedmetadata", () => { if (data) draw(); });

  // words: click = play from there; click + shift-click = a range; "Seçileni kes" -> a message line
  const cutBtn = el("button", { class: "tool", type: "button", text: "Seçileni kes", disabled: true, onclick: () => {
    if (!sel) return;
    const [a, b] = sel, ws = words.slice(a, b + 1);
    addLine(`Kes (çıktıda): ${stamp(ws[0].t0, 2)}–${stamp(ws[ws.length - 1].t1, 2)} «${ws.map((w) => w.w).join(" ")}»`);
    sel = null; paintSel();
  } });
  function paintSel() {
    for (const sp of wordsBox.querySelectorAll(".w")) {
      const k = +sp.dataset.k;
      sp.classList.toggle("sel", !!sel && k >= sel[0] && k <= sel[1]);
    }
    cutBtn.disabled = !sel;
  }
  let wordsBusy = false;
  async function loadWords(tries = 0) {
    if (!box.isConnected && tries) return;
    if (wordsBusy && !tries) return;  // already polling
    wordsBusy = true;
    try {
      const d = await api(`/api/words?path=${encodeURIComponent(path)}`);
      if (d.status === "working") {
        wordsBox.replaceChildren(el("p", { class: "tl-note", text: "Konuşma yazıya dökülüyor (ilk sefer biraz sürer)…" }));
        return setTimeout(() => loadWords(tries + 1), 3000);
      }
      if (d.status === "error") { wordsBusy = false; return wordsBox.replaceChildren(el("p", { class: "tl-note", text: `Kelimeler alınamadı: ${d.error}` })); }
      wordsBusy = false;
      words = d.words || [];
      const flow = el("div", { class: "w-flow" });
      words.forEach((w, k) => flow.append(el("span", { class: "w", "data-k": k, title: stamp(w.t0, 2), text: w.w,
        onclick: (e) => {
          if (e.shiftKey && sel) sel = [Math.min(sel[0], k), Math.max(sel[0], k)];
          else { sel = sel && sel[0] === k && sel[1] === k ? null : [k, k]; video.currentTime = w.t0; video.play().catch(() => {}); }
          paintSel();
        } }), " "));
      wordsBox.replaceChildren(
        words.length ? flow : el("p", { class: "tl-note", text: "Konuşma bulunamadı." }),
        el("div", { class: "w-bar" }, el("span", { class: "tl-note", text: "Tıkla: oradan oynat · Shift+tıkla: aralık seç" }), cutBtn));
      sync();
    } catch (e) { wordsBusy = false; wordsBox.replaceChildren(el("p", { class: "tl-note", text: e.message })); }
  }
  wordsBtn.onclick = () => {
    const on = wordsBox.hidden;
    wordsBox.hidden = !on; wordsBtn.setAttribute("aria-pressed", String(on));
    if (on && !words) loadWords();
  };
  load();
  return box;
}

function openLight(url) {
  const box = $("#lightbox");
  box.classList.remove("full"); $("#lightImg").src = url; box.hidden = false; box.scrollTo(0, 0);
}
$("#lightbox").onclick = (e) => {
  const box = $("#lightbox");
  if (e.target === $("#lightImg")) { box.classList.toggle("full"); box.scrollTo(0, 0); return; }  // fit <-> full size
  box.hidden = true; box.classList.remove("full");
};

/* ------------------------------------------------------------------ boot */
async function loadStatus() {
  const h = $("#health");
  try {
    const st = await api("/api/status");
    S.release = !!st.release;
    S.version = st.vlogkit;
    $("#verLabel").textContent = `v${st.vlogkit}`;
    const ok = !!st.claude_version;
    const cx = (st.engines || []).find((x) => x.id === "codex");
    h.className = `health ${ok ? "good" : "bad"}`;
    h.title = (ok ? `Claude Code ${st.claude_version.replace(" (Claude Code)", "")} · abonelik` : "claude CLI bulunamadı")
      + (cx && cx.available ? " · Codex hazır" : "") + ` · vlogkit ${st.vlogkit}`;
    if (st.guide && st.guide.artifact) $("#guideLink").href = st.guide.artifact; else $("#guideLink").hidden = true;
    S.engines = st.engines || [{ id: "claude", label: "Claude Code", available: ok, models: st.models, default_model: st.default_model }];
    for (const o of $("#engine").options) {
      const e = S.engines.find((x) => x.id === o.value);
      o.disabled = !e || !e.available;
    }
    if ($("#engine").selectedOptions[0]?.disabled) $("#engine").value = "claude";
    syncEngine();
    if (S.job) syncJobEffort();
    fillSelect($("#retention"), (st.retention_choices || [0]).map((d) => ({ id: String(d), label: RETENTION_LABEL(d) })), String(st.retention_days || 0));
    fillSelect($("#cleanDays"), (st.clean_choices || [0]).map((d) => ({ id: String(d), label: CLEAN_LABEL(d) })), String(st.clean_days || 0));
    loadDisk();
  } catch { h.className = "health bad"; h.title = "Sunucuya ulaşılamıyor"; }
}
$("#quit").onclick = async () => {
  try { await post("/api/shutdown"); } catch { /* already down */ }
  document.body.replaceChildren(el("div", { style: "height:100%;display:grid;place-items:center;color:var(--dim)" },
    el("p", { text: "Stüdyo kapandı. Açmak için masaüstündeki vlogkit Stüdyo'ya tıkla." })));
};

/* ------------------------------------------------------------------ drag & drop */
// Browsers never reveal a dropped file's path: the server finds it by name + size + date under
// ~/yt-vlogs, Desktop, Downloads and Movies. Not found -> offer to copy it into ~/yt-vlogs.
const VIDEO_RE = /\.(mp4|mov|m4v|mkv|webm)$/i;
let dragDepth = 0;
const hasFiles = (e) => [...(e.dataTransfer?.types || [])].includes("Files");
addEventListener("dragenter", (e) => { if (!hasFiles(e)) return; e.preventDefault(); dragDepth++; $("#drop").hidden = false; });
addEventListener("dragover", (e) => { if (hasFiles(e)) e.preventDefault(); });
addEventListener("dragleave", () => { if (--dragDepth <= 0) { dragDepth = 0; $("#drop").hidden = true; } });
addEventListener("drop", async (e) => {
  if (!hasFiles(e)) return;
  e.preventDefault(); dragDepth = 0; $("#drop").hidden = true;
  const items = [...e.dataTransfer.items].filter((x) => x.kind === "file");
  const entries = items.map((x) => (x.webkitGetAsEntry ? x.webkitGetAsEntry() : null));
  const files = items.map((x) => x.getAsFile());
  const dir = entries.findIndex((x) => x && x.isDirectory);
  if (dir >= 0) {  // a folder: the source of a new job
    if (S.job) return toast("Klasör yeni işte eklenir: önce ＋ Yeni iş");
    try {
      const { path } = await post("/api/locate", { name: files[dir].name, dir: true });
      return path ? setVideo(path) : toast("Klasör bulunamadı: Video > Klasör seç ile ekle");
    } catch (err) { return toast(err.message); }
  }
  addFiles(files.filter(Boolean));
});

/* ------------------------------------------------------------------ attachments */
// Files sent with a message: images/documents are uploaded (build/ui/attachments), videos are
// found on disk by name + size (or copied). On the home screen the first video is the job's source.
const IMAGE_RE = /\.(png|jpe?g|gif|webp|heic|heif|tiff?)$/i;
const DOC_RE = /\.(pdf|txt|md|srt|json|csv)$/i;
const attKey = () => `att:${draftKey()}`;
function loadAtts() { S.att = saved.get(attKey(), []); renderAtts(); }
function saveAtts() { saved.set(attKey(), S.att); renderAtts(); }
function renderAtts() {
  const box = $("#atts");
  box.replaceChildren(...(S.att || []).map((a, i) => el("div", { class: `att ${a.kind}`, title: a.path },
    a.kind === "image" ? el("img", { src: media(a.path), alt: "" }) : el("span", { class: "ic", text: a.kind === "video" ? "▶" : "≡" }),
    el("span", { class: "nm", text: a.name }),
    el("button", { class: "x", type: "button", title: "Kaldır", text: "✕",
      onclick: () => { S.att.splice(i, 1); saveAtts(); } }))));
  box.hidden = !(S.att || []).length;
}
async function addFiles(files) {
  for (const file of files) {
    try {
      if (VIDEO_RE.test(file.name)) {
        let { path } = await post("/api/locate", { name: file.name, size: file.size, mtime: file.lastModified / 1000 });
        if (!path) {
          if (!confirm(`${file.name} bilgisayarda bulunamadı. ~/yt-vlogs/studyo-eklenen içine kopyalansın mı? (${fmtSize(file.size)})`)) continue;
          path = await putFile(`/api/upload?name=${encodeURIComponent(file.name)}`, file);
        }
        if (!S.job && !S.video) { await setVideo(path); continue; }  // the new job's source video
        S.att.push({ path, kind: "video", name: file.name });
      } else if (IMAGE_RE.test(file.name) || DOC_RE.test(file.name)) {
        const r = await putFile(`/api/attach?name=${encodeURIComponent(file.name)}`, file, true);
        S.att.push({ path: r.path, kind: r.kind, name: file.name });
      } else { toast(`${file.name}: görsel, video ya da belge ekle`); continue; }
      saveAtts();
    } catch (err) { toast(`${file.name}: ${err.message}`); }
  }
}
$("#attachBtn").onclick = () => $("#filePick").click();
$("#filePick").onchange = (e) => { addFiles([...e.target.files]); e.target.value = ""; };
input.addEventListener("paste", (e) => {
  const images = [...(e.clipboardData?.items || [])].filter((x) => x.kind === "file" && x.type.startsWith("image/"));
  if (!images.length) return;
  e.preventDefault();
  const stamp = new Date().toISOString().slice(11, 19).replace(/:/g, "");
  addFiles(images.map((x, i) => {
    const f = x.getAsFile();
    return new File([f], `yapistirilan-${stamp}${i ? "-" + i : ""}.${(f.type.split("/")[1] || "png").replace("jpeg", "jpg")}`, { type: f.type });
  }));
});
const fmtSize = (b) => (b > 1e9 ? `${(b / 1e9).toFixed(1)} GB` : `${Math.round(b / 1e6)} MB`);
function upload(file) { return putFile(`/api/upload?name=${encodeURIComponent(file.name)}`, file); }
function putFile(url, file, whole = false) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("X-Vlogkit-Token", TOKEN);
    xhr.upload.onprogress = (ev) => { if (ev.lengthComputable) toast(`Kopyalanıyor… %${Math.round((ev.loaded / ev.total) * 100)}`); };
    xhr.onload = () => {
      let body = {};
      try { body = JSON.parse(xhr.responseText); } catch {}
      if (xhr.status === 200 && body.path) { if (!whole) toast("Kopyalandı"); resolve(whole ? body : body.path); }
      else reject(new Error(body.error || "Kopyalanamadı"));
    };
    xhr.onerror = () => reject(new Error("Kopyalanamadı"));
    xhr.send(file);
  });
}

/* ------------------------------------------------------------------ tab title */
// A glance at the tab tells whether a job is still running or has just finished.
const BASE_TITLE = document.title;
let finishedUnseen = false;
function syncTitle() {
  const running = (S.jobs || []).some((j) => j.status === "running");
  document.title = `${running ? "● " : finishedUnseen ? "✓ " : ""}${BASE_TITLE}`;
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) { finishedUnseen = false; syncTitle(); } });

/* ------------------------------------------------------------------ first run, models, updates */
// Setup: install.sh only puts the studio on the Mac; the heavy parts are installed from here,
// each with its size (Homebrew needs Terminal for the Mac password, the rest runs in the
// background with progress). Then an agent: install and sign in. Shown until all is ready.
const AGENTS = { claude: { name: "Claude Code", plan: "Claude Pro ya da Max aboneliği" }, codex: { name: "Codex", plan: "ChatGPT Plus ya da Pro aboneliği" } };
let welcomeTimer = 0, wasReady = null;
const setupDone = (d) => d.steps.every((x) => x.done) && Object.values(d.agents).some((a) => a.ready);
async function checkSetup(fresh = false) {
  let d;
  try { d = await api(`/api/setup${fresh ? "?fresh=1" : ""}`); } catch { return null; }
  S.setup = d;
  const ready = setupDone(d);
  if (wasReady === null) wasReady = ready;
  drawWelcome(d, ready);
  if (!$("#settings").hidden) drawSettingsSetup(d);
  drawModels();
  pollSetup(d, ready);
  return d;
}
function stepState(x) {
  const t = x.task || {};
  if (x.done) return [el("span", { class: "state ok", text: "Kurulu" })];
  if (t.status === "running") return [el("span", { class: "state run", text: `%${Math.round((t.progress || 0) * 100)}` })];
  const go = (label) => el("button", { class: `pop-btn${x.ready ? " primary" : ""}`, type: "button", text: label, disabled: !x.ready,
    title: x.ready ? "" : "Önce bir önceki adım", onclick: () => stepAction(x.id) });
  if (x.terminal) return x.admin ? [go("Terminal'de kur")] : [el("span", { class: "state bad", text: "Yönetici hesabı gerekli" })];
  const out = [go(x.id === "speech" || x.id === "library" ? "İndir" : "Kur")];
  if (t.status === "error") out.unshift(el("span", { class: "state bad", text: "Olmadı", title: t.error || "" }));
  return out;
}
function setupRows(d) {
  const steps = d.steps.map((x) => el("li", { class: `step-row${x.done ? " ok" : ""}` },
    el("div", { class: "s-text" }, el("b", { text: x.label }), el("small", { text: x.detail })),
    el("span", { class: "s-size", text: x.size }), el("div", { class: "s-act" }, ...stepState(x))));
  const agents = Object.entries(AGENTS).map(([id, meta]) => {
    const a = d.agents[id], task = d.tasks[`agent:${id}`];
    let state, act = null;
    if (task && task.status === "running") state = "Kuruluyor…";
    else if (!a.installed) {
      state = task && task.status === "error" ? "Kurulamadı" : "Kurulu değil";
      const needsBrew = id === "codex" && !d.steps[0].done;
      act = el("button", { class: "pop-btn", type: "button", text: "Kur", disabled: needsBrew,
        title: needsBrew ? "Codex Homebrew ile kurulur: önce ilk adım" : "", onclick: () => agentAction(id, "install") });
    } else if (!a.ready) {
      state = "Giriş yapılmadı";
      act = el("button", { class: "pop-btn primary", type: "button", text: "Giriş yap", title: "Terminal açılır; tarayıcıda hesabınla onayla", onclick: () => agentAction(id, "login") });
    } else state = `Hazır${a.plan ? ` · ${a.plan}` : ""}`;
    return el("div", { class: `agent${a.ready ? " ok" : ""}` },
      el("div", {}, el("b", { text: meta.name }), el("small", { text: meta.plan })),
      el("span", { class: "state", text: state }), act);
  });
  return { steps, agents };
}
const setupBusy = (d) => d.steps.some((x) => x.task && x.task.status === "running") || Object.values(d.tasks).some((t) => t.status === "running");
function drawWelcome(d, ready) {
  const box = $("#welcome");
  if (box.hidden && (ready || sessionStorage.getItem("welcomeLater"))) return;
  box.hidden = false;
  const { steps, agents } = setupRows(d);
  $("#setupSteps").replaceChildren(...steps);
  $("#welcomeAgents").replaceChildren(...agents);
  const canRun = d.steps.some((x) => !x.done && x.ready && !x.terminal && !(x.task && x.task.status === "running"));
  $("#setupAll").hidden = !canRun;
  $("#welcomeGo").hidden = !ready;
  if (ready && wasReady === false) { wasReady = true; toast("Hazır: ilk işini yazabilirsin"); }
}
// one poll for both places that show the setup (the welcome screen, Ayarlar > Kurulum)
function pollSetup(d, ready) {
  clearTimeout(welcomeTimer);
  const shown = !$("#welcome").hidden || (!$("#settings").hidden && S.pane === "setup");
  if (!shown) return;
  const busy = setupBusy(d), agentReady = Object.values(d.agents).some((a) => a.ready);
  if (!ready || busy) welcomeTimer = setTimeout(() => checkSetup(!agentReady), busy ? 1500 : 3000);
}
async function stepAction(id) {
  try {
    await post("/api/setup/step", { id });
    if (id === "homebrew") toast("Terminal açıldı: Mac şifreni yaz, bitince buraya dön");
    setTimeout(() => checkSetup(), 600);
  } catch (e) { toast(e.message); }
}
$("#setupAll").onclick = () => stepAction("all");
async function agentAction(id, action) {
  try {
    await post("/api/setup/agent", { name: id, action });
    if (action === "login") toast("Terminal açıldı: tarayıcıda giriş yap, sonra buraya dön");
    setTimeout(() => checkSetup(true), 800);
  } catch (e) { toast(e.message); }
}
$("#welcomeLater").onclick = () => { sessionStorage.setItem("welcomeLater", "1"); $("#welcome").hidden = true; clearTimeout(welcomeTimer); };
$("#welcomeGo").onclick = () => { sessionStorage.setItem("welcomeLater", "1"); $("#welcome").hidden = true; clearTimeout(welcomeTimer); loadStatus(); };

// Local video model: optional; one of three sizes, installed with progress, picked or removed.
let modelTimer = 0;
function drawModels() {
  const m = S.setup && S.setup.models, box = $("#models");
  if (!m) return;
  const mk = (id, label, sub, installed, selected, extra) => el("label", { class: `model${selected ? " on" : ""}` },
    el("input", { type: "radio", name: "vlm", value: id, checked: selected, disabled: !installed,
      onchange: () => modelAction(id || null, "select") }),
    el("span", { class: "m-name", text: label }), el("small", { text: sub }), extra || "");
  const rows = [mk("", "Yok", "yerel model kullanma", true, !m.selected)];
  let busy = false;
  for (const c of m.choices) {
    const t = c.task;
    let extra;
    if (t && t.status === "running") { busy = true; extra = el("span", { class: "m-prog", text: `%${Math.round((t.progress || 0) * 100)}` }); }
    else if (c.installed) extra = el("button", { class: "m-act", type: "button", text: "Kaldır", onclick: (e) => {
      e.preventDefault();
      const b = e.currentTarget;
      if (!b.dataset.armed) { b.dataset.armed = "1"; b.textContent = "Emin misin?"; return; }
      modelAction(c.id, "remove");
    } });
    else extra = el("button", { class: "m-act", type: "button", text: "Kur", title: c.fits ? "" : `Bu Mac'in belleği (${m.memory_gb} GB) bu model için az`,
      onclick: (e) => { e.preventDefault(); modelAction(c.id, "install"); } });
    const sub = `${c.size_gb} GB · ${c.note}${c.fits ? "" : " · bu Mac için ağır"}${t && t.status === "error" ? ` · hata: ${t.error}` : ""}`;
    rows.push(mk(c.id, c.label, sub, c.installed, c.selected, extra));
  }
  box.replaceChildren(...rows);
  $("#modelsHint").textContent = `Bu Mac: ${m.memory_gb} GB bellek. Ham çekimdeki hareketi izler (log --vlm, ask, face). Şart değil: kurulu değilse de her şey çalışır.`;
  clearTimeout(modelTimer);
  if (busy) modelTimer = setTimeout(() => checkSetup(), 1500);
}
async function modelAction(id, action) {
  try { S.setup.models = await post("/api/setup/model", { id, action }); drawModels(); if (action === "install") setTimeout(() => checkSetup(), 1000); }
  catch (e) { toast(e.message); checkSetup(); }
}

// Updates (installed copies): a pill at the bottom left when a newer version is out.
async function checkUpdate(force = false) {
  let u;
  try { u = await api(`/api/update${force ? "?force=1" : ""}`); } catch { return; }
  S.update = u;
  if (!$("#settings").hidden) drawAbout();
  const b = $("#updateBtn");
  b.hidden = !u.available && !(u.upgrading && u.upgrading.status);
  b.textContent = u.upgrading && u.upgrading.status === "running" ? "Güncelleniyor…" : `Güncelleme var · ${u.latest}`;
}
$("#updateBtn").onclick = (e) => {
  const u = S.update || {};
  $("#updateTitle").textContent = `vlogkit ${u.latest} (şu an ${u.current})`;
  $("#updateNotes").innerHTML = md(u.notes || "Bu sürümün notları okunamadı.");
  $("#updateStep").textContent = "Projelerin ve videoların değişmez. Stüdyo kendini yeniden başlatır.";
  $("#updateGo").disabled = false;
  showPop($("#updatePop"), e.currentTarget);
};
async function runUpdate(btn, stepEl) {
  const u = S.update || {};
  try { await post("/api/update", { version: u.latest }); } catch (e) { return toast(e.message); }
  btn.disabled = true;
  const poll = async () => {
    try {
      // the restarted server has a new access token: the page reads it from "/" and reloads
      const html = await (await fetch("/", { cache: "no-store" })).text();
      const m = html.match(/name="vlogkit-token" content="([^"]+)"/);
      if (m && m[1] !== TOKEN) return location.reload();
      const v = await api("/api/update");
      const g = v.upgrading || {};
      if (g.status === "error") { stepEl.textContent = `Olmadı: ${g.error}`; btn.disabled = false; return; }
      stepEl.textContent = g.step || "Güncelleniyor…";
    } catch { stepEl.textContent = "Yeniden başlatılıyor…"; }
    setTimeout(poll, 1200);
  };
  poll();
}
$("#updateGo").onclick = () => runUpdate($("#updateGo"), $("#updateStep"));

/* ------------------------------------------------------------------ settings */
// Ayarlar: installs (the setup steps and the agent), the local model, storage (history, build
// intermediates), and the version with updates and removal. Opened from the bottom left.
S.pane = "setup";
function openSettings(pane = S.pane) {
  closePop();
  $("#settings").hidden = false;
  showPane(pane);
  checkSetup();
  loadDisk();
  drawAbout();
}
function closeSettings() { $("#settings").hidden = true; clearTimeout(welcomeTimer); }
function showPane(pane) {
  S.pane = pane;
  for (const b of document.querySelectorAll(".settings-nav button")) b.classList.toggle("on", b.dataset.pane === pane);
  for (const sec of document.querySelectorAll(".settings .pane")) sec.hidden = sec.dataset.pane !== pane;
  if (pane === "setup" && S.setup) pollSetup(S.setup, setupDone(S.setup));
}
function drawSettingsSetup(d) {
  const { steps, agents } = setupRows(d);
  $("#setStepsList").replaceChildren(...steps);
  $("#setAgents").replaceChildren(...agents);
}
function versionText() {
  const u = S.update || {};
  if (!S.release) return "Geliştirici kopyası";
  if (u.available) return `Güncelleme var: ${u.latest}`;
  return u.error ? "Güncelleme kontrol edilemedi" : "Güncel";
}
function drawAbout() {
  $("#aboutVersion").textContent = S.version || "";
  $("#setVersion").textContent = `Sürüm ${S.version || "?"} · ${versionText()}`;
  $("#aboutUpdate").textContent = versionText();
  const u = S.update || {};
  $("#aboutUpdateBtn").hidden = !u.available;
  $("#aboutUpdateBtn").textContent = `${u.latest} sürümüne güncelle`;
  const devCopy = !S.release;
  for (const b of document.querySelectorAll(".u-acts button")) b.disabled = devCopy;
  $("#uninstallNote").textContent = devCopy
    ? "Bu bir geliştirici kopyası (git ile yönetiliyor): buradan kaldırılmaz."
    : "Videoların ve teslim dosyaların kalır; projelerin ve iş geçmişin önce yedeklenir.";
}
$("#settingsBtn").onclick = () => openSettings();
$("#settingsClose").onclick = closeSettings;
$("#settings").addEventListener("click", (e) => { if (e.target === e.currentTarget) closeSettings(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#settings").hidden) closeSettings(); });
for (const b of document.querySelectorAll(".settings-nav button")) b.onclick = () => showPane(b.dataset.pane);
$("#aboutUpdateBtn").onclick = () => runUpdate($("#aboutUpdateBtn"), $("#aboutUpdate"));
// removal: the plan first (what goes, what stays, where the backup goes), then one confirmation
const GBs = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(n / 1e6))} MB`);
for (const b of document.querySelectorAll(".u-acts button")) b.onclick = async () => {
  const box = $("#uninstallPlan");
  let p;
  try { p = await api(`/api/uninstall?mode=${b.dataset.mode}`); } catch (e) { return toast(e.message); }
  const total = p.remove.reduce((n, x) => n + (x.size || 0), 0);
  box.hidden = false;
  box.replaceChildren(
    el("b", { text: b.dataset.mode === "all" ? "Uygulama ve kurulan paketler kaldırılacak" : "Uygulama kaldırılacak" }),
    el("ul", { class: "u-list" }, p.remove.map((x) => el("li", {}, el("span", { text: x.label }), x.size ? el("small", { text: GBs(x.size) }) : ""))),
    el("small", { class: "hint", text: `Toplam yaklaşık ${GBs(total)}. Kalanlar: ${p.keep.join("; ")}.` }),
    el("small", { class: "hint", text: `Yedek: ${p.backup}` }),
    el("div", { class: "u-confirm" },
      el("button", { class: "pop-btn", type: "button", text: "Vazgeç", onclick: () => { box.hidden = true; } }),
      el("button", { class: "pop-btn danger", type: "button", text: "Kaldır", onclick: async () => {
        let r;
        try { r = await post("/api/uninstall", { mode: b.dataset.mode }); } catch (e) { return toast(e.message); }
        document.body.replaceChildren(el("div", { class: "bye" },
          el("span", { class: "wordmark", text: "vlogkit" }),
          el("p", { text: "vlogkit kaldırılıyor. Bu pencereyi kapatabilirsin." }),
          el("small", { text: `Projelerin ve iş geçmişin: ${r.backup}` })));
      } })));
};

async function boot() {
  setPlan(S.plan);
  renderCut();
  loadStatus();
  try { S.guide = await api("/api/guide"); renderTasks(); renderAddons(); } catch (e) { toast(`Rehber okunamadı: ${e.message}`); }
  const lastVideo = saved.get("video", null);
  if (lastVideo) setVideo(lastVideo);
  await refreshJobs().catch(() => {});
  const id = location.hash.slice(1);
  if (id && S.jobs.some((j) => j.id === id)) openJob(id); else goHome();
  setInterval(() => refreshJobs().catch(() => {}), 4000);
  checkSetup();
  checkUpdate();
  setInterval(() => checkUpdate(), 3600 * 1000);  // an open studio sees a new version within the hour
}
boot();
