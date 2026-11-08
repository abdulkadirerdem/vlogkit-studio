"""CI: the studio answers, its token works, the setup rows are the Windows ones (or the Mac ones)."""

import json
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:8765"
html = urllib.request.urlopen(BASE + "/", timeout=20).read().decode("utf-8")
token = re.search(r'name="vlogkit-token" content="([^"]+)"', html).group(1)


def get(path: str) -> dict:
    req = urllib.request.Request(BASE + path, headers={"X-Vlogkit-Token": token})
    return json.load(urllib.request.urlopen(req, timeout=60))


status = get("/api/status")
setup = get("/api/setup")
print("vlogkit", status["vlogkit"], "claude:", status["claude"])
for r in setup["steps"]:
    print(f"  {r['id']:<10} done={r['done']} optional={bool(r.get('optional'))}")
ids = [r["id"] for r in setup["steps"]]
want = (
    ["ffmpeg", "git", "library"]
    if sys.platform == "win32"
    else ["homebrew", "tools", "speech", "library"]
)
assert ids[: len(want)] == want, ids
assert [r["id"] for r in setup["steps"] if r.get("optional")] == ["blender", "lib3d", "voice"], ids
print("studio ok")
