#!/bin/bash
# vlogkit kurulumu: Apple Silicon Mac (M1 ve sonrası), macOS 14 ya da sonrası.
#
# Terminal'e yapıştır ve Enter'a bas:
#   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/abdulkadirerdem/vlogkit-studio/main/install.sh)"
#
# Tekrar çalıştırmak güvenli: kurulu olanı geçer, eksik olanı kurar. Kurulum bitince Stüdyo
# tarayıcıda açılır; Claude Code ya da Codex'e girişi orada yaparsın. Güncellemeler Stüdyo'dan gelir.
set -euo pipefail

REPO_URL="${VLOGKIT_REPO:-https://github.com/abdulkadirerdem/vlogkit-studio.git}"
ROOT="${VLOGKIT_ROOT:-$HOME/yt-vlogs}"   # videoların ve vlogkit burada durur
DEST="$ROOT/vlogkit"
WHISPER_MODEL="$HOME/.cache/whisper-cpp/ggml-large-v3-turbo.bin"
WHISPER_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }
fail() { printf '\n\033[31mKurulum durdu: %s\033[0m\n' "$*" >&2; exit 1; }
trap 'fail "beklenmedik bir hata oldu (satır $LINENO). Aynı satırı tekrar çalıştırmayı dene."' ERR

[ "$(uname -s)" = "Darwin" ] || fail "vlogkit yalnız macOS'ta çalışır."
[ "$(uname -m)" = "arm64" ] || fail "vlogkit Apple Silicon (M1 ve sonrası) bir Mac ister."
major="$(sw_vers -productVersion | cut -d. -f1)"
[ "$major" -ge 14 ] || fail "macOS 14 (Sonoma) ya da sonrası gerekli: önce macOS'u güncelle."

# 1. Homebrew (Mac için paket yöneticisi; Apple'ın geliştirici araçlarını da kurar)
if [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
else
  dseditgroup -o checkmember -m "$USER" admin >/dev/null 2>&1 \
    || fail "Homebrew kurmak için bu Mac'te yönetici hesabı gerekli. Yönetici hesabıyla tekrar dene."
  step "Homebrew kuruluyor: Mac şifren sorulacak (yazarken görünmez, yazıp Enter'a bas)"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
grep -qs 'brew shellenv' "$HOME/.zprofile" || echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> "$HOME/.zprofile"

# 2. Araçlar
step "Araçlar kuruluyor: ffmpeg, whisper, aubio, uv (ilk seferde 10-20 dakika sürebilir)"
brew install ffmpeg-full whisper-cpp aubio uv
brew install terminal-notifier >/dev/null 2>&1 || true   # bildirime tıklayınca işi açmak için

# 3. Konuşma modeli (whisper)
if [ ! -s "$WHISPER_MODEL" ]; then
  step "Konuşma modeli indiriliyor (~1,6 GB)"
  mkdir -p "$(dirname "$WHISPER_MODEL")"
  curl -fL --retry 3 -C - --progress-bar -o "$WHISPER_MODEL.part" "$WHISPER_URL"  # resumes
  mv "$WHISPER_MODEL.part" "$WHISPER_MODEL"
fi

# 4. vlogkit
mkdir -p "$ROOT"
if [ -f "$DEST/.release" ]; then
  step "vlogkit zaten kurulu (güncellemeler Stüdyo'nun sol altından gelir)"
elif [ -e "$DEST" ]; then
  fail "$DEST var ama bir vlogkit kurulumu değil. Başka bir yere taşı, sonra tekrar çalıştır."
else
  step "vlogkit indiriliyor"
  git clone --quiet "$REPO_URL" "$DEST"
fi
cd "$DEST"
step "Python ortamı hazırlanıyor"
uv sync --frozen --quiet
step "Lisanslı ses ve müzik kütüphanesi indiriliyor"
uv run --frozen --quiet vlogkit assets fetch || echo "  Bazı dosyalar inmedi; kurulumu sonra tekrar çalıştırınca yeniden denenir."

# 5. Masaüstü uygulaması ve ilk açılış
step "Masaüstüne 'vlogkit Stüdyo' ekleniyor"
uv run --frozen --quiet vlogkit shortcut >/dev/null
uv run --frozen --quiet vlogkit open >/dev/null
printf '\n\033[32mvlogkit kuruldu.\033[0m Stüdyo tarayıcıda açıldı: Claude Code ya da Codex ile giriş yap.\n'
printf 'Sonraki seferlerde masaüstündeki "vlogkit Stüdyo"ya çift tıkla. Videolarını %s içine koy.\n' "$ROOT"
