# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Sürümleme: [SemVer](https://semver.org/).

## [0.18.2] - 2026-11-02

### Değişti
- **Tek kanal sesi:** 3B videolar artık Qwen3-TTS'in Türkçe ince ayarıyla (Apache-2.0), hep aynı referans sesle (`assets/voice/kanal.wav`, Chatterbox'ın kendi sesiyle üretildi, MIT) seslendirilir; video başına ses ve duygu seçimi yok. Pocket TTS ve sistem sesleri yalnız açıkça istenince. Sayılar seslendirmeden önce Türkçe kelimeye çevrilir (`speech/sayilar.py`: "1.250" → "bin iki yüz elli", "%38" → "yüzde otuz sekiz"). Kurulum ekranındaki "Türkçe ses modeli" ve `vlogkit 3d install-voice` bunu kurar (~5 GB, bir kez).

## [0.18.1] - 2026-11-02

### Düzeltildi
- **Windows: her birkaç saniyede bir komut penceresi açılıp kapanıyordu, "Müzik ve ses kütüphanesi" kurulurken `uv.exe` 0xc0000142 hatası veriyordu.** Stüdyo sunucusu hiç konsolu olmadan başlatılıyordu; başlattığı her konsol programı (kurulum ekranının birkaç saniyede bir sorduğu `uv tool dir`, ffprobe, git) kendi penceresini açıyor, bazıları başlayamıyordu. Sunucu artık görünmeyen bir konsolla başlar, başlattığı süreçler pencere açmaz; `uv tool dir` bir kez sorulur.
- **Windows: kurulum satırı güncellerken açık Stüdyo'yu önce kapatır** (açık Stüdyo dosyaları kilitliyordu).
- **3B render oturumdan bağımsız:** `vlogkit 3d render` / `3d progress` (ajanın turu bitince render yarıda kesiliyordu).

## [0.18.0] - 2026-11-02

### Eklendi
- **3B animasyon (`vlogkit 3d`, `scene3d/`, `docs/3d.md`):** "Peki ya...?" tarzı çekimsiz dikey videolar. Ajan yalnız `projects/<proje>/scene.json` yazar (beat'ler: anlatım cümlesi, mekân, oyuncular ve hareketleri, kamera, sayaç, efekt); Blender kitten render eder, vlogkit sayaç, altyazı, bitiş kartı ve sesi ekler, `vlogkit build` ile derlenir. Komutlar: `3d new`, `plan` (seslendirip beat zamanlarını yazar), `preview -t` (tek kare render + grafikler), `kit`, `voice` (sesleri "Seçim:" kartıyla dinletir), `status`, `fetch`, `install-voice`.
  - Gerçekçi iskeletli karakterler (Quaternius Universal Base Characters, CC0) ve hareket kaydı kalitesinde 43 animasyon (Universal Animation Library, CC0); kıyafetler karakterin gövdesinden üretilir (tişört, kapüşonlu, önlük, takım; kot, şort...), spor ayakkabı, ten ve saç rengi, boy ve yapı: her karakter farklı. Kütüphanede olmayan jestler (şok, el sallama, işaret, omuz silkme...) kol kemikleri hedeflenerek animasyonun üstüne katman olarak eklenir.
  - Mekânlar: oda, banyo, sınıf, mutfak, ofis, spor salonu, sokak, şehir, park, uzay, stüdyo fonu, Dünya; Poly Haven gökyüzü ışıkları (HDRI) ve gerçek dokular (CC0). Gerçek modeller: binalar ve sokak eşyaları (Quaternius Downtown City), ağaçlar ve bitkiler (Stylized Nature), arabalar, Poly Haven mobilyaları; Dünya NASA Blue Marble ve atmosfer ışıltısıyla. Sokakta binaların zemin katında Türkçe dükkân tabelaları. Yazılı eşyalar (gazete, tabela, takvim, ekran...) kitin kendi çizimi. Kamera: 10 kadraj, 11 hareket.
  - Zıplama gerçek fizikle: kalkış klibinin sonunda havalanır, yükseklikten hesaplanan süre boyunca parabol çizer, iniş klibinin ilk karesinde yere değer.
  - Doğrulayıcı tüm hataları bir kerede, izin verilen adlarla yazar. Değişmeyen beat yeniden render edilmez. `VLOGKIT_3D_ENGINE=cycles` (GPU'suz), `VLOGKIT_3D_RES=0.5` (hızlı taslak).
  - Eski oyuncak karakterler `"style": "toon"` ile seçilebilir.
- **Yerel Türkçe seslendirme (`speech/`):** Pocket TTS Turkish (yerel, ücretsiz, ticari kullanım serbest; 6 ses, duygu ayarı, izinli ses kopyalama), kendi `uv tool` ortamında. Süreler sesin kendisinden ölçülür. Sistem sesleri (Yelda, Tolga) robotik olduğu için kendiliğinden seçilmez.
- **Stüdyo:** "3B animasyon" iş türü; kurulum ekranında isteğe bağlı üç satır: Blender (Homebrew / winget), 3B karakter ve mekân kütüphanesi (~160 MB, `vlogkit-studio`'nun `3d-library-1` sürümünden, SHA-256 doğrulamalı), Türkçe ses modeli. İsteğe bağlı satırlar "hazır" durumunu ve "Hepsini kur"u etkilemez.
- **Kadraj dışı yazı uyarısı (`scene3d/framing.py`, `bpy_kit/framecheck.py`):** `3d preview` karelerin altına, `build` ise her planın ortasında, kadraja sığmayan sahne yazılarını (tabela, takvim, tahta, afiş) `!` ile yazıyor: yüzde kaçı dışarıda ve hangi kenardan. Önceden ancak kareye bakınca fark ediliyordu.
- **Duygu adları (`speech/tts.py`):** `voice.emotion` adları ses modelinin kendi etiketlerine çevriliyor (`notr` → nötr, `uzgun` → üzgün, `heyecanli` → mutlu; `saskin` eklendi). Yanlış duygu ya da ses adı artık render başlamadan doğrulayıcıda görünüyor (önceden model çalışırken hata veriyordu).
- **Windows 10 / 11 (`winsupport.py`, `install.ps1`):** Stüdyo ve 3B animasyon işleri: PowerShell kurulum satırı, winget ile FFmpeg ve Git, masaüstü ve Başlat menüsü kısayolu, dosya seçici, Explorer'da göster, iş sürerken uyumama, iş ağacını durdurma, her Python sürecinde UTF-8, Windows yollarının sohbette önizlenmesi, Segoe emoji. Gerçek bir Windows makinesinde otomatik test (`.github/workflows/windows-3d.yml`). Apple'a özel analiz araçları Mac'te kalır.

## [0.17.0] - 2026-10-11

### Eklendi
- **İş türü (Stüdyo):** Yeni işte yazma kutusunun üstünden tür seçilir: Otomatik, Vlog, Short / Reels, Hareketli grafik, Kapak ve başlık, Soru. Mesaja "İş türü: ..." satırı gider. Her türün "Önce plan" ayarı, eforu ve ekleri ayrı saklanır; bir türde seçilen ek (ör. 4K teslim) başka türe geçmez. Kurgu ayarı yalnız kesim içeren türlerde (Otomatik, Vlog, Short) eklenir. Görev listesinden Short ya da uzun video görevi seçince tür kendiliğinden gelir. Önceden bütün işlere eklenen ekler "Otomatik"e taşınır.
- **Hedef teyidi:** Ajan her işin ilk cevabının ilk satırında hedefi tek cümleyle yazar (ne, oran, süre, çözünürlük); tür istekle çelişiyorsa sorar.
- **Trend şarkı aday kartı:** "Trend şarkı" tanımlandı: tanınmış sanatçıların edit şarkıları (ör. 21 Savage "a lot"), ülke dinlenme listesi değil. Şarkı verilmediyse ajan kurgudan önce 4-6 adayı "Seçim:" kartıyla gösterir (şarkı, BPM, drop, kaynak ve tarih, neden) ve seçimi bekler. Seçim kartlarında birden çok seçenek seçilebilir.

### Değişti
- **Daha hızlı varsayılanlar:** Varsayılan efor Extra high yerine Yüksek; Vlog türünde Extra high, Soru'da Orta.
- **Eleştirmen yalnız büyük işte:** ham çekimden kurgu, 60 sn'den uzun yeni kurgu, büyük revizyon ya da istenirse. İkinci tur yalnız ilk turda kritik madde çıktıysa. Ajan eleştirmeni ya da arka plandaki derlemeyi sabit süreli `sleep` döngüleriyle beklemez: bağımsız işleri yapar, kalmadıysa kısa bir notla turu bitirir; iş bitince oturum kendiliğinden devam eder (headless `claude -p` ile doğrulandı). Stüdyo devam eden adımları notun altında yeni bir blokta canlı gösterir.
- **4K yalnız 4K kaynakta:** Ek "Kaynak 4K ise 4K teslim et." oldu; Stüdyo onu seçili video 4K değilse göndermez. Kaynak video yoksa (hareketli grafik, kapak) teslim 1080p.
- **Kurulum ekranı Mac'te olanı sayar:** ffmpeg-full (filtrelerine bakılarak; düz ffmpeg yetmez), whisper ve aubio araç araç algılanır; satır neyin var neyin eksik olduğunu yazar ve yalnız eksikler kurulur. Araçlar başka yoldan kuruluysa Homebrew adımı gerekmez. Hugging Face'ten indirilmiş konuşma modeli de kullanılır. Intel Mac'te ffmpeg-full (`/usr/local/opt`) bulunur.
- **Kaldırma yalnız vlogkit'in kurduğunu siler:** İlk kurulum kontrolünde Mac'te olan araçlar ve modeller (`build/ui/found.json`) "Uygulamayı ve kurulan paketleri kaldır"da yerinde kalır. Bu sürümden önce kurulmuş kopyalarda o an kurulu olan her şey "önceden vardı" sayılır.

### Düzeltildi
- **"Video ve ses araçları" kurulurken %0'da kalıyordu.** Homebrew 4.5'ten beri önce bütün paketleri indiriyor, sonra kuruyor; ilerleme yalnız kurulumu sayıyordu ve zaten kurulu bağımlılıkları da hesaba katıyordu. Artık indirmeler (%70) ve kurulumlar (%30) yalnız eksik paketlere göre sayılır.

## [0.16.0] - 2026-10-09

### Eklendi
- **Trend şarkıya drop'tan kesim (`reel --bpm X --drop SN`):** Şarkı dosyası yokken drop saniyesi (uygulamada dinleyerek ya da senkron sözlerden) ızgarayı kurar: drop bir ölçü başıdır, önceki ölçüler şarkının başına doğru sayılır (`music.anchored`). Harita verilmezse drop'a kadar orta, drop'tan sonra 8 yüksek ölçü, sonra orta; `--map` verilirse ilk `D` drop'a oturur. `--first-beat` ile birlikte verilmez.
- **`SoftText(rise=...)`:** Kapanış yazısının yükselme mesafesi ayarlanır; `rise=0` yazıyı kaydırmadan, yerinde belirtir (Stüdyo oturumu).

### Değişti
- **Yükleme notu üç platform için:** `reel` artık `<ad>.instagram.txt` yerine `<ad>.muzik.txt` yazar: başlangıç saniyesi, hizalanacak kesme, trend sesin kesit olabileceği uyarısı ve TikTok, Instagram Reels, YouTube Shorts notları (işletme hesabı sınırları; 60 sn'den uzun videoda Shorts uyarısı). Fonksiyon `beatcut.upload_note`; eski projeler için `instagram_note` adı da çalışır.
- **Trend şarkı rehberi (`docs/shorts.md`):** Trendin nereden okunduğu (TikTok Creative Center, YouTube "Top Songs on Shorts", Instagram'da uygulama içi), tempo ve drop kaynakları, platform tablosu. Trend listesi ve BPM ajanın web aramasından gelir; ücretli servis, MCP ya da API anahtarı yok. CLAUDE.md'de yeni iş türü satırı, prompt rehberinde kalıp güncellendi.

### Düzeltildi
- **Shorts telif kuralı:** `docs/shorts.md` "24 Eylül 2026'dan beri 1-3 dk Short engellenmiyor" diyordu; resmi sayfalar (9 Ekim 2026) hâlâ telif iddialı 1 dk üstü Short'un engellendiğini söylüyor. Telifli şarkı eklenecek Short 60 sn altında kalmalı.

## [0.15.1] - 2026-10-07

### Değişti
- **Yerel model donanıma göre:** Mac'in belleğine uymayan model artık kurulamaz (2B 8 GB, 4B ve 9B 16 GB ister; önce yalnız "ağır" uyarısı vardı), diskte indirme + 5 GB boş yer yoksa da kurulmaz; satırda nedeni yazar. Rahat çalışan en büyük model "önerilen" diye işaretlenir (9B 24 GB'tan itibaren). Daha önce kurulmuş, belleğe uymayan model kullanılabilir kalır, satırı uyarır. `vlogkit extras install vlm` de aynı kuralla seçili ya da önerilen modeli kurar.

## [0.15.0] - 2026-10-07

### Eklendi
- **Ayarlar paneli (sol alt):** Kurulum (araçlar, konuşma modeli, kütüphane, ajan; kurulum ekranıyla aynı satırlar), Yerel model, Depolama (geçmiş, ara dosyalar) ve Sürüm ve kaldırma (sürüm, güncelleme, prompt rehberi). Yazma kutusundaki ⋯ artık yalnız iş ayarları (ajan, izinler, model, efor, ek talimatlar). Sürüm numarası sol altta görünür; "Prompt rehberi" bağlantısı Ayarlar'a taşındı.
- **Kaldırma (`vlogkit/uninstall.py`):** "Uygulamayı kaldır" (vlogkit klasörü ve masaüstü uygulaması) ve "Uygulamayı ve kurulan paketleri kaldır" (ayrıca Homebrew paketleri ve kullanılmayan bağımlılıkları, konuşma modeli, yerel video modelleri, mlx-vlm). Önce silinecekler boyutlarıyla gösterilir; projeler, iş geçmişi, sözlük ve yerel manifest `~/yt-vlogs/vlogkit-yedek-<tarih>`'e yedeklenir. Videolar, Homebrew, Apple geliştirici araçları, uv, Claude Code ve Codex kalır. Geliştirici kopyasında kapalı.

### Değişti
- Açık bir Stüdyo yeni sürüme saatte bir bakar (önce 6 saatte bir).

### Düzeltildi
- **Yerel model kaldırınca yer açılmıyordu:** Hugging Face model dosyalarını ortak bir depoda tutup model klasörüne bağlantı koyuyor; yalnız klasör siliniyordu. Artık o modelin kullandığı (başka modelle paylaşılmayan) dosyalar da silinir ve boyut doğru gösterilir.

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

