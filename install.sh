#!/bin/bash
# vlogkit kurulumu: Apple Silicon Mac (M1 ve sonrası), macOS 14 ya da sonrası.
#
# Terminal'e yapıştır ve Enter'a bas:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/abdulkadirerdem/vlogkit-studio/main/install.sh)"
#
# Burada yalnız Stüdyo kurulur (uv, vlogkit ve Python; ~150 MB, bir iki dakika) ve tarayıcıda açılır.
# Video araçları, konuşma modeli, müzik kütüphanesi ve yapay zekâ ajanı Stüdyo'nun kurulum
# ekranından, boyutları görünerek kurulur. Tekrar çalıştırmak güvenli.
set -euo pipefail

REPO="${VLOGKIT_REPO_SLUG:-abdulkadirerdem/vlogkit-studio}"
ROOT="${VLOGKIT_ROOT:-$HOME/yt-vlogs}"   # videoların ve vlogkit burada durur
DEST="$ROOT/vlogkit"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mKurulum durdu: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'fail "beklenmedik bir hata oldu (satır $LINENO). Aynı satırı tekrar çalıştırmayı dene."' ERR

[ "$(uname -s)" = "Darwin" ] || fail "vlogkit yalnız macOS'ta çalışır."
[ "$(uname -m)" = "arm64" ] || fail "vlogkit Apple Silicon (M1 ve sonrası) bir Mac ister."
major="$(sw_vers -productVersion | cut -d. -f1)"
[ "$major" -ge 14 ] || fail "macOS 14 (Sonoma) ya da sonrası gerekli: önce macOS'u güncelle."

# 1. uv: Python'u ve vlogkit'in ortamını kurar (~40 MB, şifre istemez)
if ! command -v uv >/dev/null 2>&1; then
  step "uv kuruluyor"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# 2. vlogkit
mkdir -p "$ROOT"
if [ -f "$DEST/.release" ]; then
  step "vlogkit zaten kurulu (güncellemeler Stüdyo'nun sol altından gelir)"
elif [ -e "$DEST" ]; then
  fail "$DEST var ama bir vlogkit kurulumu değil. Başka bir yere taşı, sonra tekrar çalıştır."
elif xcode-select -p >/dev/null 2>&1; then
  step "vlogkit indiriliyor"
  git clone --quiet "https://github.com/$REPO.git" "$DEST"
else
  # Apple geliştirici araçları henüz yok (git onlarla gelir): son sürümün arşivi. Stüdyo, araçlar
  # kurulunca kopyayı git'e bağlar; güncellemeler o zaman da aynı yerden gelir.
  step "vlogkit indiriliyor"
  mkdir -p "$DEST"
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/main.tar.gz" | tar -xz -C "$DEST" --strip-components 1
fi
cd "$DEST"
step "Python ortamı hazırlanıyor"
uv sync --frozen --quiet

# 3. Masaüstü uygulaması ve ilk açılış
step "Masaüstüne 'vlogkit Stüdyo' ekleniyor"
uv run --frozen --quiet vlogkit shortcut >/dev/null
uv run --frozen --quiet vlogkit open >/dev/null
printf '\n\033[32mvlogkit Stüdyo kuruldu ve tarayıcıda açıldı.\033[0m Kalan parçaları oradaki kurulum ekranından kur.\n'
printf 'Sonraki seferlerde masaüstündeki "vlogkit Stüdyo"ya çift tıkla. Videolarını %s içine koy.\n' "$ROOT"
