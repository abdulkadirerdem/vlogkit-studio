# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Sürümleme: [SemVer](https://semver.org/).

## [0.14.2] - 2026-10-07

### Düzeltildi
- **Masaüstü uygulaması yenilenemeyince kurulum duruyordu.** macOS, başka bir işlemin oluşturduğu uygulamayı değiştirmeye izin vermiyor (uygulama koruması); kurulum satırı tekrar çalıştırılınca kısayol adımı hata verip kurulumu durduruyordu. Artık açık bir mesaj verir ("çöpe at, sonra tekrar") ve kurulum sürer.

## [0.14.1] - 2026-10-07

### Değişti
- **Kurulum iki adım:** Terminal'deki satır artık yalnız Stüdyo'yu kurar (uv, vlogkit, Python: ~150 MB, şifre sormaz) ve tarayıcıda açar. Apple geliştirici araçları ve Homebrew, video ve ses araçları, konuşma modeli, müzik kütüphanesi ve ajan Stüdyo'nun kurulum ekranından kurulur: her satırda boyut, arka planda ilerleme, **Hepsini kur**. Geliştirici araçları yoksa vlogkit git yerine sürüm arşivinden iner; araçlar gelince kopya kendiliğinden git'e bağlanır ve güncellemeler aynı yoldan sürer (git yokken yeni sürüm ve notlar GitHub'dan okunur).
- **Masaüstü uygulamasının ikonu:** macOS 26'da derlenmiş varsayılan betik ikonu (`Assets.car`) bizimkinin önüne geçiyordu; kısayol artık onu kaldırıp paketi yeniden imzalıyor, "vk" ikonu görünüyor. Güncelleme masaüstündeki uygulamayı da yeniler.
- **Herkese açık sayfa:** Logo, Stüdyo ekran görüntüsü, kısa tanıtım, iki adımlı kurulum ve bilgisayara neyin, ne boyutta kurulduğu tablosu (`docs/public/README.md`, yayında README olur). `KURULUM.md` sadeleşti. Marka görselleri `scripts/brand.py` ile üretilir (`assets/brand/`).

## [0.14.0] - 2026-10-07

### Eklendi
- **Herkese açık kurulum ve güncelleme:** Apple Silicon Mac'e tek satırla kurulum (`install.sh`: Homebrew, ffmpeg-full, whisper ve modeli, aubio, uv, vlogkit, medya kütüphanesi, masaüstü uygulaması) ve adım adım `KURULUM.md`. Dağıtım ayrı, herkese açık `vlogkit-studio` reposundan; geliştirme bu repoda kalır. `scripts/release.py` her sürümde yalnız araç kodunu yayınlar (projeler, tarifler, sözlük, testler ve CHANGELOG'daki proje maddeleri hariç; ev klasörü yolu ya da git e-postası bir dosyada geçerse durur) ve `v<sürüm>` etiketi koyar.
- **Stüdyo'dan güncelleme (`vlogkit/update.py`):** Kurulu kopya (`.release` dosyası) 6 saatte bir yeni etiketi sorar; sol altta "Güncelleme var", tıklayınca o sürümün notları ve **Güncelle**. Güncelleme etikete geçer, `uv sync` ve `assets fetch` çalıştırır, Stüdyo'yu yeniden başlatır. Kullanıcının projeleri, derlemeleri, sözlüğü ve `assets/manifest.local.toml` git dışında; elle değişmiş araç dosyaları `git stash`'e gider. İş çalışırken güncellenmez.
- **İlk açılış ekranı:** Claude Code ya da Codex kurulu ve girişli değilse: **Kur** (Claude Code'un resmi kurucusu, Codex için Homebrew), **Giriş yap** (Terminal'de giriş komutu; ekran girişi kendisi görür), eksik temel araçlar.
- **Yerel video modeli seçimi:** Ayarlarda aynı modelin üç boyutu (Qwen3.5 2B / 4B / 9B, MLX 4-bit); Mac'in belleği ve hangisinin uyduğu, ilerlemeli kurulum, seçim ve kaldırma. Model şart değil; "Yok" seçilirse kullanılmaz. Seçim `build/vlm.json`'da, eski kurulum seçim yapılmadıysa indirilmiş en iyi modeli kullanır.
- **Lisanslar:** Her derleme adımı kullandığı kütüphane dosyalarını kaydeder (`assets.recording`, iş klasöründe `assets.json`); teslimde videonun yanına `<video>.lisans.md` (parça, yazar, lisans, sayfa, Content ID kontrol tarihi, İngilizce itiraz metni) yazılır ve aynı veri Stüdyo'da sağ üstteki **Lisanslar** kartında görünür (**İtiraz metnini kopyala**). Eski derlemeler için `vlogkit licenses PROJE -v VARYANT`. Manifest'te müziklere `checked` tarihi eklendi.
- **Zaman çizelgesinde yakınlaştırma:** +/−, ⌘ + tekerlek ya da sıkıştırma, izde çift tık; Shift + tekerlek ya da yana kaydırma ile gezinme; yakınken üstte bütün videoyu gösteren sürüklenebilir özet şerit; oynarken pencere oynatma başlığını izler. Planlar okunamayacak kadar sıksa çizelge ilk dakikayla açılır.
- **Lisans:** PolyForm Noncommercial 1.0.0 ve ek izin: kendi videolarını yapıp yayınlamak (para kazanan kanallar dahil) serbest; satmak, hizmet olarak sunmak ya da ticari bir ürüne katmak yazılı izin ister.

### Düzeltildi
- **`SoftText` çok satırda satırları üst üste bindiriyordu** (gölgesiz satırın boşluğu yok, aralık negatifti). Satır aralığı artık yazı boyunun %30'u.

### Değişti
- Kurulu kopyada ajan vlogkit'in kendi dosyalarını değiştirmez (`CLAUDE.md` ve Stüdyo sistem talimatı); "vlogkit'i geliştir" görevleri ve "Commit + push" eki gizli, öneriler "Kopyala" ile geliştiriciye iletilir. Yeni lisanslı medya `assets/manifest.local.toml`'a yazılır (`assets.manifest()` ikisini birleştirir).
- Depodan yanlışlıkla girmiş tarayıcı anlık görüntüleri (`.playwright-mcp`) çıkarıldı ve git dışında tutuluyor.

