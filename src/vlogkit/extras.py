"""Optional external tools: vlogkit uses them when installed, never requires them.

- deepfilter: DeepFilterNet 3 command line (`deep-filter`, MIT / Apache-2.0). The official prebuilt
  macOS arm64 binary from the GitHub release, kept in ~/.cache/vlogkit/bin. The model is built in.
- demucs: Demucs v4 source separation (htdemucs, MIT), installed as an isolated `uv tool`: torch is
  big and must never become a dependency of the project itself.
- vlm: the local video-language model (mlx-vlm as an isolated `uv tool` + Qwen3.5-9B 4-bit MLX,
  Apache-2.0, ~6 GB in the Hugging Face cache). `find` gives the tool's python.

`find(name)` gives the executable or None; `install(name)` fetches it and checks that it runs.
Override the location with VLOGKIT_DEEPFILTER / VLOGKIT_DEMUCS.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.request
from pathlib import Path

BIN_DIR = Path(os.environ.get("VLOGKIT_TOOLS_BIN") or Path.home() / ".cache" / "vlogkit" / "bin")

DEEPFILTER_VERSION = "0.5.6"
DEEPFILTER_URL = (
    "https://github.com/Rikorose/DeepFilterNet/releases/download/"
    f"v{DEEPFILTER_VERSION}/deep-filter-{DEEPFILTER_VERSION}-aarch64-apple-darwin"
)
# demucs 4.1.0 imports numpy without declaring it; Python 3.12 and torch/torchaudio < 2.9 keep
# the audio I/O on the code paths demucs was written against (torchaudio 2.9 moved to torchcodec).
DEMUCS_INSTALL = [
    "tool", "install", "demucs", "--python", "3.12", "--with", "numpy",
    "--with", "torch<2.9", "--with", "torchaudio<2.9",
]  # fmt: skip

TOOLS = ("deepfilter", "demucs", "vlm")


def _uv_bin_dir() -> Path:
    uv = shutil.which("uv")
    if uv:
        r = subprocess.run([uv, "tool", "dir", "--bin"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return Path(r.stdout.strip())
    return Path.home() / ".local" / "bin"


def find(name: str) -> str | None:
    if name not in TOOLS:
        raise ValueError(f"bilinmeyen araç: {name} ({', '.join(TOOLS)})")
    env = os.environ.get(f"VLOGKIT_{name.upper()}")
    if env:
        return env
    if name == "deepfilter":
        local = BIN_DIR / "deep-filter"
        if local.is_file() and os.access(local, os.X_OK):
            return str(local)
        return shutil.which("deep-filter")
    if name == "vlm":
        from vlogkit.analysis import localvlm

        py = localvlm.tool_python()
        return str(py) if py and localvlm.model_cached() else None
    exe = shutil.which("demucs") or str(_uv_bin_dir() / "demucs")
    return exe if Path(exe).is_file() else None


def _runs(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=120).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def install(name: str) -> str:
    """Fetch the tool if it is missing; return its path. Raises if it cannot run here."""
    found = find(name)
    if found:
        return found
    if name == "deepfilter":
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise RuntimeError("hazır deep-filter sadece macOS arm64 için indiriliyor")
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        part, dest = BIN_DIR / "deep-filter.part", BIN_DIR / "deep-filter"
        urllib.request.urlretrieve(DEEPFILTER_URL, part)
        part.chmod(0o755)
        if not _runs([str(part), "--version"]):
            part.unlink(missing_ok=True)
            raise RuntimeError("indirilen deep-filter çalışmadı")
        part.replace(dest)
        return str(dest)
    uv = shutil.which("uv")
    if not uv:
        raise RuntimeError(f"uv bulunamadı ({name} `uv tool install` ile kurulur)")
    if name == "vlm":
        return _install_vlm(uv)
    subprocess.run([uv, *DEMUCS_INSTALL], check=True)
    found = find("demucs")
    if not found or not _runs([found, "--help"]):
        raise RuntimeError("demucs kuruldu ama çalışmıyor")
    return found


def _install_vlm(uv: str) -> str:
    """mlx-vlm in its own tool environment, then the model weights (~6 GB) into the HF cache."""
    from vlogkit.analysis import localvlm

    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise RuntimeError("yerel video modeli (MLX) sadece Apple silicon Mac'te çalışır")
    if not localvlm.tool_python():
        subprocess.run([uv, "tool", "install", "mlx-vlm"], check=True)
    py = localvlm.tool_python()
    if not py:
        raise RuntimeError("mlx-vlm kuruldu ama python'u bulunamadı")
    repo = localvlm.current() or localvlm.CHOICES["qwen3.5-9b"].repo
    if not localvlm.model_cached(repo):
        subprocess.run(download_cmd(py, repo), check=True)
    if not localvlm.chosen():  # asked for a local model: use this one (also after "Yok")
        key = next((k for k, c in localvlm.CHOICES.items() if c.repo == repo), None)
        if key:
            localvlm.choose(key)
    found = find("vlm")
    if not found:
        raise RuntimeError("model indirilemedi")
    return found


def download_cmd(py: Path, repo: str) -> list[str]:
    """Download a model into the Hugging Face cache with the tool environment's own client."""
    hf = py.parent / "hf"
    if hf.exists():
        return [str(hf), "download", repo]
    code = f"from huggingface_hub import snapshot_download; snapshot_download({repo!r})"
    return [str(py), "-c", code]


def status() -> dict[str, str | None]:
    """{tool: path or None}, for `vlogkit doctor`."""
    return {name: find(name) for name in TOOLS}
