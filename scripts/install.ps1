# vlogkit kurulumu: Windows 10 / 11 (64 bit).
#
# PowerShell'i aç (Başlat > "PowerShell"), bu satırı yapıştır ve Enter'a bas:
#   irm https://raw.githubusercontent.com/abdulkadirerdem/vlogkit-studio/main/install.ps1 | iex
#
# Burada yalnız Stüdyo kurulur (uv, vlogkit ve Python; ~150 MB, bir iki dakika) ve tarayıcıda
# açılır. FFmpeg, Git, Blender, Türkçe ses modeli, 3B kütüphane ve yapay zekâ ajanı Stüdyo'nun
# kurulum ekranından, boyutları görünerek kurulur. Tekrar çalıştırmak güvenli.
# Windows'ta bugün 3B animasyon işleri ve Stüdyo çalışır; Apple'a özel analiz araçları (yüz
# gizleme, arka plan değiştirme, yerel video modeli) yalnız Mac'te.

$ErrorActionPreference = "Stop"
$Repo = if ($env:VLOGKIT_REPO_SLUG) { $env:VLOGKIT_REPO_SLUG } else { "abdulkadirerdem/vlogkit-studio" }
$Root = if ($env:VLOGKIT_ROOT) { $env:VLOGKIT_ROOT } else { Join-Path $HOME "yt-vlogs" }
$Dest = Join-Path $Root "vlogkit"

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "`nKurulum durdu: $m" -ForegroundColor Red; exit 1 }

if (-not [Environment]::Is64BitOperatingSystem) { Fail "vlogkit 64 bit Windows ister." }
if ([Environment]::OSVersion.Version.Major -lt 10) { Fail "Windows 10 ya da 11 gerekli." }

# Türkçe metin her Python sürecinde UTF-8 olsun (kalıcı, yalnız bu kullanıcı için)
[Environment]::SetEnvironmentVariable("PYTHONUTF8", "1", "User")
$env:PYTHONUTF8 = "1"
$env:Path = "$HOME\.local\bin;$env:Path"

# 1. uv: Python'u ve vlogkit'in ortamını kurar (~40 MB, yönetici izni istemez)
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Step "uv kuruluyor"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
    $env:Path = "$HOME\.local\bin;$env:Path"
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv kurulamadı" }
}

# 2. vlogkit
New-Item -ItemType Directory -Force -Path $Root | Out-Null
if (Test-Path (Join-Path $Dest ".release")) {
    Step "vlogkit zaten kurulu; son sürüme getiriliyor"
    if (Get-Command git -ErrorAction SilentlyContinue) {
        git -C $Dest fetch --quiet --tags origin
        git -C $Dest pull --quiet --ff-only origin main
    }
} elseif (Test-Path $Dest) {
    Fail "$Dest var ama bir vlogkit kurulumu değil. Başka bir yere taşı, sonra tekrar çalıştır."
} elseif (Get-Command git -ErrorAction SilentlyContinue) {
    Step "vlogkit indiriliyor"
    git clone --quiet "https://github.com/$Repo.git" $Dest
} else {
    # Git henüz yok (Stüdyo'nun kurulum ekranından gelir): son sürümün arşivi
    Step "vlogkit indiriliyor"
    $zip = Join-Path $env:TEMP "vlogkit-main.zip"
    Invoke-WebRequest "https://github.com/$Repo/archive/refs/heads/main.zip" -OutFile $zip -UseBasicParsing
    $tmp = Join-Path $env:TEMP "vlogkit-unpack"
    if (Test-Path $tmp) { Remove-Item -Recurse -Force $tmp }
    Expand-Archive $zip $tmp
    Move-Item (Get-ChildItem $tmp | Select-Object -First 1).FullName $Dest
    Remove-Item -Recurse -Force $tmp, $zip
}
Set-Location $Dest
Step "Python ortamı hazırlanıyor"
uv sync --frozen --quiet
if ($LASTEXITCODE -ne 0) { Fail "Python ortamı kurulamadı (uv sync)" }

# 3. Masaüstü kısayolu ve ilk açılış
Step "Masaüstüne 'vlogkit Stüdyo' ekleniyor"
uv run --frozen --quiet vlogkit shortcut | Out-Null
uv run --frozen --quiet vlogkit open | Out-Null
Write-Host "`nvlogkit Stüdyo kuruldu ve tarayıcıda açıldı. Kalan parçaları oradaki kurulum ekranından kur." -ForegroundColor Green
Write-Host "Sonraki seferlerde masaüstündeki 'vlogkit Stüdyo'ya çift tıkla. Videoların: $Root"
