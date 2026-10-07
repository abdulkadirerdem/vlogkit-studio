"""Publish a version of vlogkit to the public release repo, where installed copies update from.

    uv run python scripts/release.py             # main's version -> release repo + tag v<version>
    uv run python scripts/release.py --dry-run   # only build the snapshot and show what goes out

The snapshot is the tool only. The developer's own work stays out: projects (except the
template), recipes, the channel vocabulary and the tests (they load those projects). The public
CHANGELOG starts at the first public version, without the items about those projects. A leak
check stops the release when a file names this machine's home folder, the git email or a term
from scripts/private-terms.txt (people, private details; the list itself is not published). The
commits are made as the GitHub account's noreply address, never this machine's name. The release
repo's .gitignore keeps an installed copy's own work (projects, recipes, vocabulary, local
manifest) out of git, so updates never touch it. A version already on the remote is not
published again; a failed push leaves nothing behind.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "abdulkadirerdem/vlogkit-studio"
DESCRIPTION = "vlogkit Stüdyo: Claude Code ya da Codex ile video kurgusu (Apple Silicon Mac)"
DROP = ("tests", "recipes", ".playwright-mcp", "assets/vocab.txt", "scripts/private-terms.txt")
FIRST_PUBLIC = (0, 14, 0)  # the public CHANGELOG starts here
TERMS = ROOT / "scripts" / "private-terms.txt"
KEEP_PROJECT = "_template"
IGNORE_EXTRA = """
# Your own work: never part of vlogkit's updates
/projects/*
!/projects/_template/
/recipes/
/assets/vocab.txt
/assets/manifest.local.toml
"""


def git(*args: str, cwd: Path = ROOT, check: bool = True) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def version_of(ref: str) -> str:
    text = git("show", f"{ref}:src/vlogkit/__init__.py")
    m = re.search(r'__version__\s*=\s*"([^"]+)"', text)
    if not m:
        raise SystemExit("sürüm bulunamadı")
    return m.group(1)


def export(ref: str, dest: Path) -> None:
    data = subprocess.run(["git", "archive", ref], cwd=ROOT, capture_output=True, check=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(dest, filter="data")


def _words(terms: list[str]) -> re.Pattern:
    """Whole words, any case ("ali" finds "Ali" and "ali-vlog", not "alive")."""
    alts = "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alts})(?!\w)", re.I)


def private_terms(path: Path = TERMS) -> list[str]:
    if not path.exists():
        return []
    lines = (ln.split("#", 1)[0].strip() for ln in path.read_text(encoding="utf-8").splitlines())
    return [ln for ln in lines if ln]


def public_changelog(text: str, names: list[str]) -> str:
    """The sections from the first public version on, without the developer's project items."""
    out, keep = [], True
    for line in text.splitlines():
        m = re.match(r"^## \[(\d+)\.(\d+)\.(\d+)\]", line)
        if m:
            keep = tuple(int(x) for x in m.groups()) >= FIRST_PUBLIC
        if keep:
            out.append(line)
    return drop_project_bullets("\n".join(out) + "\n", names)


def drop_project_bullets(changelog: str, names: list[str]) -> str:
    """Remove list items (with their indented children) and plain lines about the dropped
    projects; headings stay."""
    if not names:
        return changelog
    hit = _words(names)
    out, skip_indent = [], None
    for line in changelog.splitlines():
        m = re.match(r"^(\s*)[-*] ", line)
        indent = len(m.group(1)) if m else None
        if skip_indent is not None:
            if line.strip() and (indent is None or indent > skip_indent) and line.startswith(" "):
                continue  # a child or continuation of the dropped item
            skip_indent = None
        if hit.search(line) and not line.startswith("#"):  # an item, or a plain line about it
            skip_indent = indent if m else None
            continue
        out.append(line)
    text = "\n".join(out) + "\n"
    return re.sub(r"\n{3,}", "\n\n", text)


def filter_snapshot(snap: Path, version: str, repo_url: str) -> list[str]:
    """Drop the developer's own work; returns the project names that were dropped."""
    names = sorted(
        p.name for p in (snap / "projects").iterdir() if p.is_dir() and p.name != KEEP_PROJECT
    )
    for name in names:
        shutil.rmtree(snap / "projects" / name)
    for rel in DROP:
        p = snap / rel
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    cl = snap / "CHANGELOG.md"
    text = cl.read_text(encoding="utf-8")
    cl.write_text(public_changelog(text, names + private_terms()), encoding="utf-8")
    with (snap / ".gitignore").open("a", encoding="utf-8") as f:
        f.write(IGNORE_EXTRA)
    shutil.copy2(snap / "scripts" / "install.sh", snap / "install.sh")
    (snap / ".release").write_text(json.dumps({"repo": repo_url, "version": version}) + "\n")
    return names


def leaks(snap: Path, terms: list[str] | None = None) -> list[str]:
    email = git("config", "user.email", check=False).strip()
    needles = [n for n in (str(Path.home()), email) if n]
    words = terms if terms is not None else private_terms()
    pattern = _words(words) if words else None
    found = []
    for p in snap.rglob("*"):
        if not p.is_file() or p.suffix in (".ttf", ".png", ".jpg", ".icns"):
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        found += [f"{p.relative_to(snap)}: {n}" for n in needles if n in text]
        if pattern:
            found += [f"{p.relative_to(snap)}: {m}" for m in sorted(set(pattern.findall(text)))]
    return found


def identity() -> list[str]:
    """Commit as the GitHub account's noreply address (not this machine's user and host)."""
    r = subprocess.run(["gh", "api", "user", "--jq", ".id, .login"], capture_output=True, text=True)
    uid, login = [*r.stdout.split(), "", ""][:2] if r.returncode == 0 else ("", "")
    if not login:
        raise SystemExit("gh ile GitHub hesabı okunamadı: `gh auth login`")
    return ["-c", f"user.name={login}", "-c", f"user.email={uid}+{login}@users.noreply.github.com"]


def ensure_remote(repo: str) -> None:
    if subprocess.run(["gh", "repo", "view", repo], capture_output=True).returncode == 0:
        return
    subprocess.run(
        ["gh", "repo", "create", repo, "--public", "--description", DESCRIPTION], check=True
    )


def publish(snap: Path, version: str, repo: str, work: Path) -> None:
    url = f"https://github.com/{repo}.git"
    ensure_remote(repo)
    if git("ls-remote", "--tags", url, f"refs/tags/v{version}", check=False).strip():
        raise SystemExit(f"v{version} zaten yayında: önce sürümü artır")
    # the work repo always starts from what the remote has (an empty remote: from nothing), so a
    # deleted and recreated public repo never gets old local history back
    shutil.rmtree(work, ignore_errors=True)
    work.parent.mkdir(parents=True, exist_ok=True)
    if git("ls-remote", "--heads", url, "main", check=False).strip():
        git("clone", "--quiet", "--branch", "main", url, str(work), cwd=work.parent)
    else:
        work.mkdir()
        git("init", "--quiet", "-b", "main", cwd=work)
        git("remote", "add", "origin", url, cwd=work)
    for p in work.iterdir():  # the snapshot replaces everything but the git data
        if p.name != ".git":
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
    for p in snap.iterdir():
        dest = work / p.name
        if p.is_dir() and not p.is_symlink():
            shutil.copytree(p, dest, symlinks=True)
        else:
            shutil.copy2(p, dest, follow_symlinks=False)  # AGENTS.md stays a link
    who = identity()
    git("add", "-A", cwd=work)
    git(*who, "commit", "--quiet", "-m", f"vlogkit {version}", cwd=work)
    git(*who, "tag", "-a", f"v{version}", "-m", f"vlogkit {version}", cwd=work)
    try:
        git("push", "--quiet", "origin", "main", f"v{version}", cwd=work)
    finally:  # pushed or not, the next run starts from the remote again
        shutil.rmtree(work, ignore_errors=True)
    print(f"yayında: https://github.com/{repo}/releases/tag/v{version}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--ref", default="main")
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", type=Path, help="kuru çalıştırmada anlık görüntüyü buraya kopyala")
    a = ap.parse_args()
    version = version_of(a.ref)
    with tempfile.TemporaryDirectory() as tmp:
        snap = Path(tmp) / "snap"
        snap.mkdir()
        export(a.ref, snap)
        dropped = filter_snapshot(snap, version, f"https://github.com/{a.repo}.git")
        bad = leaks(snap)
        files = [p for p in snap.rglob("*") if p.is_file()]
        print(f"vlogkit {version} ({a.ref}): {len(files)} dosya; dışarıda: {', '.join(dropped)}")
        if bad:
            print("Kişisel bilgi bulundu, yayınlanmadı:\n  " + "\n  ".join(bad))
            sys.exit(1)
        if a.dry_run:
            if a.keep:
                shutil.rmtree(a.keep, ignore_errors=True)
                shutil.copytree(snap, a.keep, symlinks=True)
                print(f"anlık görüntü: {a.keep}")
            return
        publish(snap, version, a.repo, ROOT / "build" / "release" / a.repo.split("/")[-1])


if __name__ == "__main__":
    main()
