"""3B proje: video scene.json'da; bu dosya yalnız projeyi vlogkit'e tanıtır.

uv run vlogkit 3d plan <proje>              # anlatımı seslendir, beat zamanlarını gör
uv run vlogkit 3d preview <proje> -t 2 -t 9 # birkaç kareye bak
uv run vlogkit build <proje>                 # Blender render + altyazı + ses -> mp4
"""

from vlogkit.scene3d.edit import Scene3DEdit

EDIT = Scene3DEdit.for_project(__file__)
