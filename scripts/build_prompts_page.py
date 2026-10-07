"""docs/prompts.md -> single-file HTML page (published as the "vlogkit Prompt Rehberi" artifact).

    uv run python scripts/build_prompts_page.py [--out build/prompts/index.html]

docs/prompts.md is the source of truth; keep its small markdown dialect:
  # Title / <!-- meta: vlogkit=X; updated=YYYY-MM-DD --> / intro paragraphs
  ## Section {#id}                     generic markdown (paragraphs, "- " lists, **bold**, `code`)
  ```slate``` fence                     prompt skeleton card; ```text``` fence = copyable prompt
  ## ... {#promptlar} > ### Stage {#id} > #### Prompt title, then
     "Ne zaman: …", a ```text``` fence, "Claude ne yapar: …", "Not: …", "Varyasyonlar:" + "- " lines
  ## ... {#ekler}                       "- " lines become click-to-copy chips
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from vlogkit.prompts import Prompt, Stage, parse, parse_prompts

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "docs" / "prompts.md"
MONTHS = [
    "Ocak",
    "Şubat",
    "Mart",
    "Nisan",
    "Mayıs",
    "Haziran",
    "Temmuz",
    "Ağustos",
    "Eylül",
    "Ekim",
    "Kasım",
    "Aralık",
]


# ---------------------------------------------------------------- markdown (small dialect)
def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", lambda m: f"<code>{placeholders(m.group(1))}</code>", out)
    out = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', out)
    return out


def placeholders(escaped: str) -> str:
    """Highlight <fill-me> slots (already HTML-escaped)."""
    return re.sub(r"&lt;[^&\n]+?&gt;", lambda m: f'<span class="ph">{m.group(0)}</span>', escaped)


def pre_block(code: str, cls: str = "prompt") -> str:
    body = placeholders(html.escape(code.rstrip("\n"), quote=False))
    return (
        f'<div class="{cls}"><button class="copy" type="button" aria-label="Kopyala">'
        f"Kopyala</button><pre>{body}</pre></div>"
    )


def slate(code: str) -> str:
    rows = []
    for line in code.strip("\n").splitlines():
        key, _, val = line.partition(":")
        rows.append(
            f'<div class="slate-row"><dt>{html.escape(key.strip())}</dt>'
            f"<dd>{placeholders(html.escape(val.strip(), quote=False))}</dd></div>"
        )
    raw = html.escape(code.strip("\n"), quote=False)
    return (
        f'<figure class="slate"><div class="clapper" aria-hidden="true"></div>'
        f'<div class="slate-body"><dl>{"".join(rows)}</dl>'
        f'<button class="copy" type="button">İskeleti kopyala</button>'
        f'<pre class="slate-raw" hidden>{raw}</pre></div></figure>'
    )


def render_blocks(lines: list[str]) -> str:
    out, para, items, i = [], [], [], 0

    def flush() -> None:
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()
        if items:
            out.append("<ul>" + "".join(f"<li>{inline(x)}</li>" for x in items) + "</ul>")
            items.clear()

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            lang = line[3:].strip()
            j = i + 1
            while not lines[j].startswith("```"):
                j += 1
            code = "\n".join(lines[i + 1 : j])
            out.append(slate(code) if lang == "slate" else pre_block(code))
            i = j + 1
            continue
        if line.startswith("- "):
            if para:
                flush()
            items.append(line[2:])
        elif not line.strip():
            flush()
        else:
            if items:
                flush()
            para.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


# ---------------------------------------------------------------- page
def card(stage: Stage, n: int, p: Prompt) -> str:
    code = p.code
    search = " ".join([p.title, p.when, p.text, p.does, p.note, *p.variations]).lower()
    parts = [
        f'<article class="card" id="{code.lower()}" data-stage="{stage.id}" '
        f'data-search="{html.escape(search)}">',
        f'<header class="card-head"><span class="pid" title="Konuşmada bu kodla anabilirsin">'
        f"{code}</span><h4>{inline(p.title)}</h4></header>",
    ]
    if p.when:
        parts.append(f'<p class="when"><span class="lbl">Ne zaman</span>{inline(p.when)}</p>')
    parts.append(pre_block(p.text))
    notes = []
    if p.does:
        notes.append(f"<div><dt>Claude ne yapar</dt><dd>{inline(p.does)}</dd></div>")
    if p.note:
        notes.append(f"<div><dt>Not</dt><dd>{inline(p.note)}</dd></div>")
    if notes:
        parts.append(f'<dl class="notes">{"".join(notes)}</dl>')
    if p.variations:
        vs = "".join(f"<li>{inline(v)}</li>" for v in p.variations)
        parts.append(f'<div class="vars"><span class="lbl">Varyasyonlar</span><ul>{vs}</ul></div>')
    parts.append("</article>")
    return "\n".join(parts)


def build(md: str) -> str:
    title, meta, intro, sections = parse(md)
    updated = meta.get("updated", "")
    if updated:
        y, mth, d = updated.split("-")
        updated = f"{int(d)} {MONTHS[int(mth) - 1]} {y}"
    nav, body = [], []
    for s in sections:
        if s.id == "promptlar":
            stages = parse_prompts(s.lines)
            total = sum(len(st.prompts) for st in stages)
            chips = [
                f'<button class="chip" type="button" data-filter="all" aria-pressed="true">'
                f'Tümü <span class="count">{total}</span></button>'
            ]
            groups, sub = [], []
            for st in stages:
                chips.append(
                    f'<button class="chip" type="button" data-filter="{st.id}" '
                    f'aria-pressed="false">{html.escape(st.title)} '
                    f'<span class="count">{len(st.prompts)}</span></button>'
                )
                cards = "\n".join(card(st, i + 1, p) for i, p in enumerate(st.prompts))
                groups.append(
                    f'<section class="stage" id="{st.id}" data-stage="{st.id}">'
                    f"<h3>{html.escape(st.title)}</h3>{cards}</section>"
                )
                sub.append(
                    f'<li><a href="#{st.id}">{html.escape(st.title)}'
                    f'<span class="count">{len(st.prompts)}</span></a></li>'
                )
            nav.append(
                f'<li><a href="#{s.id}">{html.escape(s.title)}</a>'
                f'<ul class="sub">{"".join(sub)}</ul></li>'
            )
            body.append(
                f'<section class="block" id="{s.id}"><h2>{html.escape(s.title)}</h2>'
                f'<div class="filters" role="group" aria-label="Aşamaya göre filtrele">'
                f"{''.join(chips)}</div>"
                f'<p class="empty" hidden>Bu filtreyle eşleşen prompt yok.</p>'
                f"{''.join(groups)}</section>"
            )
        elif s.id == "ekler":
            text = [x for x in s.lines if x.strip() and not x.startswith("- ")]
            items = [x[2:] for x in s.lines if x.startswith("- ")]
            chips = "".join(
                f'<button class="addon" type="button">{inline(x)}</button>' for x in items
            )
            nav.append(f'<li><a href="#{s.id}">{html.escape(s.title)}</a></li>')
            body.append(
                f'<section class="block" id="{s.id}"><h2>{html.escape(s.title)}</h2>'
                f'<p>{inline(" ".join(text))}</p><div class="addons">{chips}</div></section>'
            )
        else:
            nav.append(f'<li><a href="#{s.id}">{html.escape(s.title)}</a></li>')
            body.append(
                f'<section class="block" id="{s.id}"><h2>{html.escape(s.title)}</h2>'
                f"{render_blocks(s.lines)}</section>"
            )
    name = title.replace("vlogkit", "").strip() or title
    return (
        TEMPLATE.replace("{{NAME}}", html.escape(name))
        .replace("{{VERSION}}", html.escape(meta.get("vlogkit", "?")))
        .replace("{{UPDATED}}", html.escape(updated))
        .replace("{{INTRO}}", render_blocks(intro))
        .replace("{{NAV}}", "".join(nav))
        .replace("{{BODY}}", "\n".join(body))
    )


TEMPLATE = r"""<title>vlogkit Prompt Rehberi</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Montserrat:wght@800;900&display=swap">
<style>
:root {
  --bg: #eceef2; --surface: #ffffff; --ink: #15171c; --muted: #586070; --line: #d7dbe2;
  --accent: #ffcf40; --on-accent: #15171c; --accent-ink: #7a5600;
  --panel: #14161b; --panel-ink: #e6e9ee; --panel-muted: #8b92a0; --panel-line: #2a2e36;
  --chip: #e1e4ea; --shadow: 0 1px 0 rgba(21,23,28,.04), 0 6px 18px -12px rgba(21,23,28,.25);
  --display: "Montserrat", "Helvetica Neue", Arial, sans-serif;
  --sans: "IBM Plex Sans", "Helvetica Neue", Arial, sans-serif;
  --mono: "IBM Plex Mono", ui-monospace, "SF Mono", Menlo, monospace;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0f1115; --surface: #171a20; --ink: #e8ebf0; --muted: #99a0ad; --line: #262b34;
    --accent-ink: #ffcf40; --panel: #0a0c0f; --panel-line: #22262e; --chip: #1f232b;
    --shadow: 0 1px 0 rgba(0,0,0,.3); color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0f1115; --surface: #171a20; --ink: #e8ebf0; --muted: #99a0ad; --line: #262b34;
  --accent-ink: #ffcf40; --panel: #0a0c0f; --panel-line: #22262e; --chip: #1f232b;
  --shadow: 0 1px 0 rgba(0,0,0,.3); color-scheme: dark;
}
* { box-sizing: border-box; }
body { background: var(--bg); color: var(--ink); font: 400 16px/1.6 var(--sans); }
a { color: inherit; text-decoration-color: var(--accent); text-underline-offset: 3px; }
:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; border-radius: 4px; }
code { font: 500 .88em var(--mono); background: var(--chip); padding: .1em .35em; border-radius: 4px; }
.page { max-width: 1180px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 80px;
  display: grid; grid-template-columns: 230px minmax(0, 1fr); gap: 56px; }
.masthead { grid-column: 1 / -1; display: grid; gap: 14px; max-width: 760px; }
.wordmark { font: 900 clamp(2.4rem, 6vw, 3.6rem)/1 var(--display); letter-spacing: -.01em;
  color: var(--accent); -webkit-text-stroke: 7px var(--on-accent); paint-order: stroke fill;
  text-shadow: 0 6px 14px rgba(0,0,0,.25); margin: 0; }
.masthead h1 { font: 800 clamp(1.5rem, 3.4vw, 2.1rem)/1.15 var(--display); margin: 0;
  text-wrap: balance; }
.stamp { font: 500 12.5px var(--mono); color: var(--muted); letter-spacing: .02em; }
.stamp b { color: var(--ink); font-weight: 500; }
.intro p { margin: 0; color: var(--muted); max-width: 64ch; }
nav { position: sticky; top: calc(env(safe-area-inset-top, 0px) + 20px); align-self: start;
  display: grid; gap: 18px; }
.search { width: 100%; font: 400 15px var(--sans); color: var(--ink); background: var(--surface);
  border: 1px solid var(--line); border-radius: 8px; padding: 9px 12px; }
nav ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; }
nav a { display: flex; justify-content: space-between; gap: 8px; padding: 5px 8px;
  border-radius: 6px; text-decoration: none; font-weight: 500; }
nav a:hover { background: var(--chip); }
nav .sub { margin: 2px 0 6px 10px; border-left: 2px solid var(--line); padding-left: 6px; }
nav .sub a { font-weight: 400; color: var(--muted); font-size: 14.5px; }
.count { font: 500 12px var(--mono); color: var(--muted); font-variant-numeric: tabular-nums; }
main { min-width: 0; display: grid; gap: 64px; }
.block { display: grid; gap: 18px; max-width: 780px; }
.block h2 { font: 800 1.45rem/1.2 var(--display); margin: 0; text-wrap: balance; }
.block > p, .block > ul { margin: 0; max-width: 66ch; }
.block ul { padding-left: 1.2em; display: grid; gap: 6px; }
.stage { display: grid; gap: 16px; margin-top: 18px; }
.stage h3 { font: 600 12.5px var(--mono); letter-spacing: .14em; text-transform: uppercase;
  color: var(--muted); margin: 0; display: flex; align-items: center; gap: 12px; }
.stage h3::after { content: ""; flex: 1; height: 1px; background: var(--line); }
.filters { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { font: 500 14px var(--sans); color: var(--ink); background: var(--chip); border: 0;
  border-radius: 999px; padding: 6px 12px; cursor: pointer; display: inline-flex; gap: 6px;
  align-items: baseline; }
.chip[aria-pressed="true"] { background: var(--accent); color: var(--on-accent); }
.chip[aria-pressed="true"] .count { color: var(--on-accent); opacity: .7; }
.empty { color: var(--muted); font-style: italic; }
.card { background: var(--surface); border: 1px solid var(--line); border-radius: 12px;
  padding: 20px; display: grid; gap: 14px; box-shadow: var(--shadow); scroll-margin-top: 20px; }
.card-head { display: flex; align-items: baseline; gap: 12px; }
.card-head h4 { margin: 0; font: 600 1.08rem/1.35 var(--sans); text-wrap: balance; }
.pid { font: 500 12px var(--mono); background: var(--panel); color: var(--accent);
  padding: 2px 7px; border-radius: 5px; flex: none; }
.when { margin: 0; color: var(--muted); }
.lbl { display: inline-block; font: 600 11px var(--mono); letter-spacing: .1em;
  text-transform: uppercase; color: var(--accent-ink); margin-right: 10px; }
.prompt { position: relative; background: var(--panel); border-radius: 10px;
  border: 1px solid var(--panel-line); }
.prompt pre { margin: 0; padding: 16px 18px; padding-top: 42px; overflow-x: auto;
  font: 400 13.5px/1.65 var(--mono); color: var(--panel-ink); white-space: pre-wrap;
  word-break: break-word; }
.ph { color: var(--accent); font-weight: 500; }
code .ph { color: var(--accent-ink); }
.copy { position: absolute; top: 8px; right: 8px; font: 500 12.5px var(--sans);
  color: var(--panel-ink); background: rgba(255,255,255,.08); border: 1px solid var(--panel-line);
  border-radius: 6px; padding: 4px 10px; cursor: pointer; }
.copy:hover { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
.copy.done { background: var(--accent); color: var(--on-accent); }
.notes { margin: 0; display: grid; gap: 10px; }
.notes div { display: grid; grid-template-columns: 130px 1fr; gap: 12px; }
.notes dt { font: 600 11px/1.9 var(--mono); letter-spacing: .1em; text-transform: uppercase;
  color: var(--accent-ink); }
.notes dd { margin: 0; color: var(--ink); }
.vars ul { margin: 6px 0 0; }
.vars li { color: var(--muted); }
.slate { margin: 0; border-radius: 12px; overflow: hidden; background: var(--panel);
  border: 1px solid var(--panel-line); box-shadow: var(--shadow); }
.clapper { height: 26px; background: repeating-linear-gradient(-45deg, var(--accent) 0 22px,
  #15171c 22px 44px); }
.slate-body { position: relative; padding: 18px 20px 20px; }
.slate dl { margin: 0; display: grid; gap: 0; }
.slate-row { display: grid; grid-template-columns: 110px 1fr; gap: 14px; padding: 9px 0;
  border-bottom: 1px dashed var(--panel-line); }
.slate-row:last-child { border-bottom: 0; }
.slate dt { font: 500 12.5px/1.6 var(--mono); letter-spacing: .08em; color: var(--accent); }
.slate dd { margin: 0; font: 400 14px/1.6 var(--mono); color: var(--panel-ink); }
.slate .copy { top: 14px; }
.slate-body dl { padding-top: 26px; }
.addons { display: flex; flex-wrap: wrap; gap: 8px; }
.addon { font: 400 14.5px var(--sans); color: var(--ink); background: var(--surface);
  border: 1px dashed var(--line); border-radius: 8px; padding: 7px 12px; cursor: pointer;
  text-align: left; }
.addon:hover, .addon.done { border-style: solid; border-color: var(--accent); }
.addon.done { background: var(--accent); color: var(--on-accent); }
#sinirlar li strong { color: var(--ink); }
.foot { grid-column: 1 / -1; color: var(--muted); font: 400 13px var(--mono);
  border-top: 1px solid var(--line); padding-top: 18px; }
.toast { position: fixed; left: 50%; bottom: calc(env(safe-area-inset-bottom, 0px) + 24px);
  transform: translateX(-50%); background: var(--panel); color: var(--panel-ink);
  border: 1px solid var(--panel-line); border-radius: 8px; padding: 8px 14px;
  font: 500 14px var(--sans); opacity: 0; transition: opacity .2s; pointer-events: none; }
.toast.show { opacity: 1; }
@media (max-width: 900px) {
  .page { grid-template-columns: 1fr; gap: 32px; padding-block: 28px 64px; }
  nav { position: static; }
  nav > ul { display: flex; flex-wrap: wrap; gap: 4px 10px; }
  nav .sub { display: none; }
  .notes div, .slate-row { grid-template-columns: 1fr; gap: 2px; }
}
@media (prefers-reduced-motion: reduce) { .toast { transition: none; } }
</style>

<div class="page">
  <header class="masthead">
    <p class="wordmark">vlogkit</p>
    <h1>{{NAME}}</h1>
    <p class="stamp">vlogkit <b>v{{VERSION}}</b> · güncelleme <b>{{UPDATED}}</b> · kaynak <b>docs/prompts.md</b></p>
    <div class="intro">{{INTRO}}</div>
  </header>
  <nav aria-label="İçindekiler">
    <input class="search" id="q" type="search" placeholder="Prompt ara… (ör. meme, Resolve)" aria-label="Prompt ara">
    <ul>{{NAV}}</ul>
  </nav>
  <main>
{{BODY}}
  </main>
  <footer class="foot">vlogkit geliştikçe docs/prompts.md güncellenir ve bu sayfa aynı adrese yeniden yayınlanır.</footer>
</div>
<div class="toast" role="status" aria-live="polite"></div>

<script>
(function () {
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const toast = document.querySelector(".toast");
  let timer;
  function say(msg) {
    toast.textContent = msg; toast.classList.add("show");
    clearTimeout(timer); timer = setTimeout(() => toast.classList.remove("show"), 1400);
  }
  function selectText(el) {
    const r = document.createRange(); r.selectNodeContents(el);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  }
  function copy(text, btn, fallbackEl) {
    const done = () => { if (btn) { btn.classList.add("done"); setTimeout(() => btn.classList.remove("done"), 1200); } say("Kopyalandı"); };
    const fail = () => { if (fallbackEl) { fallbackEl.hidden = false; selectText(fallbackEl); } say("Metin seçildi, ⌘C ile kopyala"); };
    try { navigator.clipboard.writeText(text).then(done, fail); } catch (e) { fail(); }
  }
  $$(".prompt .copy").forEach(b => b.addEventListener("click", () => {
    const pre = b.parentElement.querySelector("pre"); copy(pre.textContent, b, pre);
  }));
  $$(".slate .copy").forEach(b => b.addEventListener("click", () => {
    const raw = b.parentElement.querySelector(".slate-raw"); copy(raw.textContent, b, raw);
  }));
  $$(".addon").forEach(b => b.addEventListener("click", () => copy(b.textContent.trim(), b, b)));

  const chips = $$(".chip"), cards = $$(".card"), stages = $$(".stage");
  const q = document.getElementById("q"), empty = document.querySelector(".empty");
  let stage = "all";
  try { stage = localStorage.getItem("vlogkit-prompts-stage") || "all"; } catch (e) {}
  if (!chips.some(c => c.dataset.filter === stage)) stage = "all";
  function apply() {
    const term = (q.value || "").trim().toLocaleLowerCase("tr");
    let shown = 0;
    cards.forEach(c => {
      const ok = (stage === "all" || c.dataset.stage === stage) && (!term || c.dataset.search.includes(term));
      c.hidden = !ok; if (ok) shown++;
    });
    stages.forEach(s => { s.hidden = !$$(".card", s).some(c => !c.hidden); });
    chips.forEach(c => c.setAttribute("aria-pressed", String(c.dataset.filter === stage)));
    if (empty) empty.hidden = shown > 0;
  }
  chips.forEach(c => c.addEventListener("click", () => {
    stage = c.dataset.filter;
    try { localStorage.setItem("vlogkit-prompts-stage", stage); } catch (e) {}
    apply();
  }));
  q.addEventListener("input", () => {
    if (q.value && stage !== "all") { stage = "all"; }
    apply();
    if (q.value) document.getElementById("promptlar").scrollIntoView({ block: "start" });
  });
  apply();
})();
</script>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=REPO / "build" / "prompts" / "index.html")
    args = ap.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build(SRC.read_text()))
    print(args.out)


if __name__ == "__main__":
    main()
