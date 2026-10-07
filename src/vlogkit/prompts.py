"""The prompt guide (docs/prompts.md) as data: used by the artifact page and by `vlogkit ui`.

Markdown dialect (keep it when editing docs/prompts.md):
  # Title / <!-- meta: vlogkit=X; updated=YYYY-MM-DD; artifact=URL --> / intro paragraphs
  ## Section {#id}                 generic markdown
  ```slate``` fence                 the prompt skeleton ("KEY: hint" lines)
  ## ... {#promptlar} > ### Stage {#id} > #### Prompt title, then "Ne zaman: …", a ```text```
     fence, "Claude ne yapar: …", "Not: …", "Varyasyonlar:" + "- " lines
  ## ... {#ekler}                   "- " lines = add-on instructions
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from vlogkit.config import REPO_ROOT

GUIDE = REPO_ROOT / "docs" / "prompts.md"

_HEAD = re.compile(r"^(#{1,4})\s+(.*?)(?:\s+\{#([\w-]+)\})?\s*$")
STAGE_CODE = {"kesif": "K", "short": "S", "uzun": "U", "revizyon": "R", "yayin": "Y", "sistem": "G"}
PLACEHOLDER = re.compile(r"<[^<>\n]+>")


@dataclass
class Prompt:
    title: str
    when: str = ""
    text: str = ""
    does: str = ""
    note: str = ""
    variations: list[str] = field(default_factory=list)
    code: str = ""
    stage: str = ""


@dataclass
class Stage:
    id: str
    title: str
    prompts: list[Prompt] = field(default_factory=list)


@dataclass
class Section:
    id: str
    title: str
    lines: list[str] = field(default_factory=list)


@dataclass
class Guide:
    title: str
    meta: dict[str, str]
    intro: list[str]
    sections: list[Section]
    stages: list[Stage]
    skeleton: list[tuple[str, str]]  # (KEY, hint)
    addons: list[str]

    def prompt(self, code: str) -> Prompt:
        for st in self.stages:
            for p in st.prompts:
                if p.code == code:
                    return p
        raise KeyError(code)

    def to_json(self) -> dict:
        return {
            "title": self.title,
            "meta": self.meta,
            "skeleton": [{"key": k, "hint": h} for k, h in self.skeleton],
            "addons": self.addons,
            "stages": [
                {"id": s.id, "title": s.title, "prompts": [asdict(p) for p in s.prompts]}
                for s in self.stages
            ],
        }


def parse(md: str) -> tuple[str, dict[str, str], list[str], list[Section]]:
    title, meta, intro, sections = "", {}, [], []
    cur: Section | None = None
    in_fence = False
    for line in md.splitlines():
        fence = line.startswith("```")
        if fence:
            in_fence = not in_fence
        m = None if (in_fence or fence) else _HEAD.match(line)
        if m and len(m.group(1)) == 1:
            title = m.group(2)
        elif m and len(m.group(1)) == 2:
            cur = Section(m.group(3) or re.sub(r"\W+", "-", m.group(2).lower()), m.group(2))
            sections.append(cur)
        elif line.startswith("<!-- meta:"):
            body = line.removeprefix("<!-- meta:").removesuffix("-->")
            meta = dict(kv.strip().split("=", 1) for kv in body.split(";") if "=" in kv)
        elif cur is None:
            intro.append(line)
        else:
            cur.lines.append(line)
    return title, meta, intro, sections


def parse_prompts(lines: list[str]) -> list[Stage]:
    stages: list[Stage] = []
    p: Prompt | None = None
    i, in_vars = 0, False
    while i < len(lines):
        line = lines[i]
        m = _HEAD.match(line)
        if m and len(m.group(1)) == 3:
            stages.append(Stage(m.group(3), m.group(2)))
            p, in_vars = None, False
        elif m and len(m.group(1)) == 4:
            st = stages[-1]
            code = f"{STAGE_CODE.get(st.id, st.id[:1].upper())}{len(st.prompts) + 1}"
            p = Prompt(m.group(2), code=code, stage=st.id)
            st.prompts.append(p)
            in_vars = False
        elif p is not None:
            if line.startswith("```"):
                j = i + 1
                while not lines[j].startswith("```"):
                    j += 1
                p.text = "\n".join(lines[i + 1 : j])
                i = j
            elif line.startswith("Ne zaman:"):
                p.when = line.split(":", 1)[1].strip()
            elif line.startswith("Claude ne yapar:"):
                p.does = line.split(":", 1)[1].strip()
            elif line.startswith("Not:"):
                p.note = line.split(":", 1)[1].strip()
            elif line.startswith("Varyasyonlar:"):
                in_vars = True
            elif in_vars and line.startswith("- "):
                p.variations.append(line[2:])
            elif line.strip():
                in_vars = False
        i += 1
    return stages


def _fence(lines: list[str], lang: str) -> list[str]:
    out, inside = [], False
    for line in lines:
        if line.startswith("```"):
            if inside:
                return out
            inside = line[3:].strip() == lang
            continue
        if inside:
            out.append(line)
    return out


def load(path: Path = GUIDE) -> Guide:
    title, meta, intro, sections = parse(path.read_text())
    by_id = {s.id: s for s in sections}
    stages = parse_prompts(by_id["promptlar"].lines) if "promptlar" in by_id else []
    skeleton = []
    if "iskelet" in by_id:
        for line in _fence(by_id["iskelet"].lines, "slate"):
            key, _, hint = line.partition(":")
            skeleton.append((key.strip(), hint.strip()))
    addons = [x[2:] for x in by_id["ekler"].lines if x.startswith("- ")] if "ekler" in by_id else []
    return Guide(title, meta, intro, sections, stages, skeleton, addons)


def placeholders(text: str) -> list[str]:
    """Unfilled <slots> left in a prompt."""
    return PLACEHOLDER.findall(text)
