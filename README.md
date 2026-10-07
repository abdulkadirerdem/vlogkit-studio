# vlogkit

Vlog kurgu araç setimiz. Uzun videolar ve Shorts/Reels için ortak araçlar: video analizi, renk, zoom, animasyonlu altyazı ve grafikler, ses miksi, ses seviyesi ayarı ve platforma uygun export. Altta **ffmpeg** ve **Pillow** kullanıyor. Her video bir **proje** (`projects/<ad>/edit.py`), tek komutla baştan üretiliyor.

```
uv run vlogkit analyze ~/yt-vlogs/kackar/Kackar_Short_02.mp4   # önce videoya bak
uv run vlogkit build kackar-short01 -v meme                     # sonra derle
uv run vlogkit check ~/yt-vlogs/kackar/Kackar_Short_01_EDIT_meme.mp4 --cuts
```

## Kurulum

Apple Silicon bir Mac'e (macOS 14+) tek satırla kurulur; Terminal'e yapıştır:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/abdulkadirerdem/vlogkit-studio/main/install.sh)"
```

Ne kurduğu, ilk açılış (Claude Code ya da Codex'e giriş), yerel video modeli, güncellemeler ve kaldırma: **[KURULUM.md](KURULUM.md)**.

### Geliştirici kurulumu (bu repo, macOS)

```bash
brew install ffmpeg-full whisper-cpp aubio uv
# Whisper modeli (~1.6 GB):
mkdir -p ~/.cache/whisper-cpp && curl -L -o ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin

cd ~/yt-vlogs/vlogkit
uv sync                          # .venv + bağımlılıklar (editable)
uv run vlogkit assets fetch      # lisanslı SFX / stok klipler -> assets/library/
uv run vlogkit doctor            # her şey ✅ olmalı
```

> Normal `ffmpeg` formülünde `drawtext`/`subtitles`/`whisper` filtreleri yok. `ffmpeg-full` gerekli, vlogkit onu `/opt/homebrew/opt/ffmpeg-full/bin` altında otomatik buluyor.

## Komutlar

| Komut | Ne yapar |
|---|---|
| `vlogkit doctor` | Araçları, modeli, fontları ve medya kütüphanesini kontrol eder |
| `vlogkit analyze VIDEO` | Kesmeler, loş bölgeler, loudness, konuşma (whisper), vuruşlar, kontak sayfası ve spektrogram → `build/analysis/<ad>/report.md` |
| `vlogkit sheet VIDEO --start 30 --duration 3 --fps 10` | Zaman damgalı kontak sayfası (her karede kaynak kare numarası) |
| `vlogkit frame VIDEO -t 12.5 [--no-grid]` | Tek kare, büyük: 0-1 koordinat ızgarası, kare numarası, kaynak boyutu (kırpma ve grafik yeri için) |
| `vlogkit strip VIDEO --start 60 --end 75 [-m 63.5]` | Kesme kararı için tek görsel: 10 kare + ses dalgası + sessiz bantlar + whisper kelimeleri + aday çizgileri → `build/strips/` |
| `vlogkit transcribe VIDEO [--words] [--beam 5 --no-context --prompt ...] [--no-vocab]` | Konuşmayı yazıya döker (`--words` karaoke için kelime zamanları; müzik altında `--no-context --beam 5`). Önbellekli; `assets/vocab.txt`'deki özel adları ipucu olarak verir |
| `vlogkit log KLASÖR --vlm` | Aynı kayıt + yerel video modeli (Qwen3.5-9B) her parçanın ne olduğunu yazar ("model" sütunu); ham süreye yakın sürer, önbellekli |
| `vlogkit find KLASÖR kelimeler... [-n 12]` | Ham çekimde anlamla arama: log'daki açıklama, hikâye adımı, yerel modelin cümlesi, Vision etiketleri ve konuşmada; kelimeleri iki dilde ver (ateş fire). Her sonuç için 3 kare → `build/find/` |
| `vlogkit ask VIDEO --start S --end E "soru" [--face]` | Yerel modele belirli bir anı sor (en fazla 60 sn): "kapıdan çıkıyor mu, hangi saniyede?" `--face` yüzün yakın planını gösterir |
| `vlogkit background VIDEO --bg studio` | Konuşma çekiminin arkasını değiştir (Apple Vision maskesi, 10-bit): `studio`, `keep`, renk, gradyan, resim, klip, `frame:klip.mp4@sn`; `--blur`, `--match` |
| `vlogkit redact VIDEO --faces [--keep-main]` ya da `--box x,y,en,boy@sn [--mode spotlight]` | Hareket eden bir şeyi gizle ya da vurgula (Apple Vision takibi, 10-bit ProRes): yabancı yüzler ve plaka bulanık, `--keep-main` senin yüzünü açık bırakır; `spotlight` tek kişiyi aydınlık bırakıp gerisini karartır → `build/redact/` |
| `vlogkit face VIDEO --start S --end E` | Kameraya konuşan kişinin mimiği (yerel model, yüzü takip eden yakın plan): ifade, enerji, gülümseme, kameraya bakış, anlar; denemeleri karşılaştırmak için |
| `vlogkit log KLASÖR` | Kurgudan önce ham çekim kaydı: her klip parça parça (Vision etiketi, konuşma, `kurulum` / `bulanık` / `karanlık` bayrakları) ve tüm klibi kapsayan sayfalar → `build/log/<klasör>/` |
| `vlogkit gaps VIDEO [--soft]` | Konuşmadaki boşlukları ve dolgu kelimeleri kesme adayı olarak listeler; `build/analysis/<ad>/gaps.json` |
| `vlogkit moments VIDEO [--min 15 --max 60]` | Uzun videodan Short adayları: paragraf sınırında 15-60 sn'lik pencereler, açılış cümlesi, kelime/sn, en yüksek ses, hareket, kare sayfaları → `build/analysis/<ad>/moments.md` (puanı Claude açıklamalı verir) |
| `vlogkit captions [--video V -t SN]` | Altyazı stilleri galerisi (pop, kutu, sade, karaoke, büyük) ve platformun kapattığı bölgeler → `build/captions/` |
| `vlogkit thumbs VIDEO --text "ZİRVE\n[5 SAAT]" [-n 3] [-t SN]` | Kapak adayları: en net ve renkli kareler, üzerine kapak yazısı → `build/thumbs/<ad>/` |
| `graphics.thumbnail.design(...)` + `check_sheet` (Python) | Seçilen kareden tasarlanmış kapak: odak/zoom, yüze ışık, yazı blokları, rozet; mobil boyutlarda kontrol sayfası |
| `analysis.segment.mask` + `thumbnail.cutout` / `bloat` / `Subject` / `Arrow` / `Ring` / `split` (Python) | Apple Vision ile kişiyi kareden kes, başı 1.2x büyüt, başka bir karenin önüne koy; ok, halka, önce/sonra bölünmüş kare, klon damgayla kişi silme, buz/donma efekti (`frost`, `Sticker`) |
| `video.pip` (Python) | Resim içinde resim: yuvarlak köşeli, gölgeli anlatıcı penceresi; ardışık pencereler kesintisiz birleşir |
| `graphics.FilmLeader` / `PhotoInset` / `Rain` / `SoftText` / `RingMark` (Python) | Eski film geri sayımı, yuvarlak köşeli foto penceresi (halkayla), yağmur, kararmış ekranda sessiz yazı, çizilerek beliren halka |
| `vlogkit projects` | Projeleri ve varyantlarını listeler |
| `vlogkit build PROJE [-v VARYANT] [-s base -s overlay ...] [--out X]` | Derler. Adımlar: `base`, `overlay`, `audio`, `compose` (videonun yanına `.srt` / `.chapters.txt` da yazar) |
| `vlogkit preview PROJE -t 5.5 -t 9.5` | Grafikleri belirli anlarda gerçek görüntünün üstünde PNG olarak gösterir |
| `vlogkit review [VIDEO] -p PROJE [--promise "zirve,5 saat"] [--no-cuts]` | İzlenme süresi kontrolü: kanca, tempo, kesmeler (artık plan, siyah kare, donuk görüntü, ses sıçraması), bitiş/loop, ses, emoji; plan sayfası ve kesme sayfaları → `build/review/<ad>.md`, `<ad>_planlar.jpg`, `<ad>_kesmeler*.jpg` |
| `vlogkit check VIDEO [--cuts]` | Teslim öncesi kontrol: kare sayısı, süre, -14 LUFS / -1 dBTP, kesmeler |
| `vlogkit beats ŞARKI` | Şarkının yapısı: BPM, ölçü başları, enerji haritası, drop'lar |
| `vlogkit music VIDEO -s 12 -d 30 -t ID -t ID@56 -t parca.mp3 [--level -20] [--no-sound]` | Aday müzikleri sahnenin altında dinlet (en fazla 6): sahne bir kez küçük işlenir, her parça kendi "açıldığı" yerden (ya da `@sn`) altına karışır → `build/music/<video>-<sn>s/`; Stüdyo'da kart olarak görünen "Seçim:" bloğunu yazar |
| `vlogkit reel ŞARKI KLİP... [--start S --length 20 --name AD --hook "..."]` | Müziğe göre montaj: kesmeler vuruşta, en iyi anlar drop'ta; şarkılı + müziksiz çıktı ve Instagram notu (`--plan plan.json` ile düzenleyip yeniden derle) |
| `vlogkit reel ŞARKI_ADI KLİP... --bpm 130 --map '----D###'` | Şarkı dosyası yoksa (telifli trend şarkı): BPM ve ölçü başına enerji haritasıyla aynı montaj; önizlemede şarkı yerine rehber ritim sesi |
| `vlogkit upscale VIDEO [--target 1920x1080]` | Düşük çözünürlüğü Apple'ın ML süper çözünürlüğüyle büyütür (siyah bantları kırpar, gürültüyü temizler) |
| `vlogkit slowmo VIDEO --factor 2` | Gerçek ara karelerle yavaş çekim (Apple VT) |
| `vlogkit match-color VIDEO --ref REF` | Planın rengini referans kareye uydur (Oklab, 3D LUT `.cube` + önce/sonra görseli); `--ref-at`, `--at`, `--strength` |
| `vlogkit stabilize VIDEO --preset running` | Titrek ham plan için vid.stab (2 geçiş) |
| `vlogkit sync KAMERA TELEFON...` | İki kaydı sesinden eşler: diğer kaydın 0. saniyesi kamerada kaçıncı saniye (~1 ms), güven ve kayma |
| `vlogkit denoise VIDEO` / `separate VIDEO` | DeepFilterNet ile konuşma temizliği / Demucs ile konuşmayı müzikten ayırma |
| `vlogkit extras list` / `install deepfilter\|demucs\|vlm` | İsteğe bağlı dış araçlar (vlm = yerel video modeli, ~6 GB) |
| `vlogkit resolve PROJE [-v VARYANT]` | DaVinci Resolve'a katmanlı aktarım: plan plan görüntü, her grafik ayrı alfa klip, kapalı düzenlenebilir metinler, ayrı ses izleri → `<çıktı>_resolve/` |
| `vlogkit timeline PROJE\|VIDEO [-v VARYANT] [--at SN]` | Kurgunun zaman çizelgesi (planlar, yazılar, bölümler, notlar) → `build/timelines/`; `--at` o anda ne olduğunu yazar (Stüdyo yorumlarını projede bulmak için) |
| `vlogkit recipe PROJE [-v VARYANT]` | Onaylanan kurgunun tarifi: açılış, plan ritmi, yazı ailesi, ses, efektler, NOTES.md stratejisi → `recipes/<proje>-<varyant>.md` ("şu videodaki gibi" için) |
| `vlogkit new PROJE` | Şablondan yeni proje açar (`edit.py` + `NOTES.md`) |
| `vlogkit licenses PROJE [-v VARYANT]` | Derlenmiş videonun yanına `<video>.lisans.md`: kullanılan kütüphane medyası (müzik, SFX, stok), lisansı, sayfası, Content ID kontrol tarihi ve İngilizce itiraz metni. Her `build` bunu kendisi yazar; komut eski derlemeler içindir |
| `vlogkit disk [--clean --older-than 14 --yes]` | Boş yer ve varyant başına ara dosyalar (base.mov, overlay.mov, wav); N gündür derlenmeyen varyantlarınkini siler. Teslim videoları, kayıtlar ve önbellekler kalır; varyant yeniden derlenince eksik adımlar kendiliğinden çalışır |
| `vlogkit open` / `ui` | vlogkit Stüdyo arayüzü (arka planda / ön planda) |
| `vlogkit shortcut` | Masaüstüne çift tıkla açılan uygulama |
| `vlogkit assets list` / `fetch` | Medya kütüphanesini listeler / indirir |

## Yapı

```
vlogkit/
├── src/vlogkit/
│   ├── cli.py            komut satırı (typer)
│   ├── config.py         araç yolları + klasörler (VLOGKIT_* env ile değiştirilebilir)
│   ├── ff.py             ffmpeg/ffprobe sarmalayıcıları, probe()
│   ├── timecode.py       kare <-> zaman (29.97), güvenli pencere sınırları
│   ├── project.py        Edit sınıfı, varyantlar, build adımları
│   ├── prompts.py        docs/prompts.md -> veri (artifact sayfası + arayüz)
│   ├── ui/               vlogkit ui: sunucu, claude -p çalıştırıcı, static/ arayüz
│   ├── assets.py         manifest.toml -> assets/library (indir, doğrula)
│   ├── analysis/         scenes, luma, letterbox, loudness, transcribe, beats, sheets, report
│   ├── video/            expr (NaN-güvenli ifadeler, piecewise), zoom/focus, grade (auto_lift),
│   │                     reframe (bant kırpma, VFR->CFR, büyütme), rewind, inserts, graph
│   ├── graphics/         style (VERTICAL / LANDSCAPE / LANDSCAPE_4K düzen), text (emoji + CJK),
│   │                     elements (Caption, Karaoke, Clock, Counter, RewindFX, EndCard, TitleCard...), render
│   ├── audio/            mix (AudioGraph, Sfx, ducking), level (kesme bazlı eşitleme), synth, loudness
│   └── export/           encode presetleri, subtitles (SRT), chapters (YouTube bölümleri)
├── projects/
│   ├── _template/        yeni proje şablonu (edit.py + NOTES.md)
│   └── <vlog>-<parça>/   her video bir proje: edit.py, varyantlar, NOTES.md
├── assets/
│   ├── fonts/            Montserrat (OFL, git'te)
│   ├── manifest.toml     üçüncü taraf medyanın kaynağı, lisansı, yazarı (git'te)
│   └── library/          indirilen dosyalar (git'te DEĞİL)
├── docs/                 workflow.md, shorts.md, viral-edit.md (izlenme süresi), tools.md (açık kaynak araçlar), prompts.md (prompt rehberi)
├── .claude/settings.json  arayüzden çalışan Claude oturumlarının izin listesi
├── CLAUDE.md             bu repoda çalışan her Claude oturumunun kuralları
├── tests/                pytest (ffmpeg testleri sentetik kliplerle)
└── build/                ara dosyalar ve analizler (git'te DEĞİL, silinebilir)
```

**Klasörler:**
- **Ham görüntüler** `~/yt-vlogs/<vlog>/` altında kalır ve repoya girmez. Projeler onlara `VLOGS_ROOT`'a göre göreli yolla bakar (`kackar/Kackar_Short_01.mp4`).
- **Final çıktı** varsayılan olarak ham görüntünün yanına yazılır.

## Yeni bir video nasıl kurgulanır

1. `uv run vlogkit analyze <video>`: `report.md` dosyasına ve kontak sayfasına bak. Konuşma varsa bilgiyi oradan çıkar; altyazılar uydurma değil, gerçek bilgi olsun.
2. `uv run vlogkit new <vlog>-<parça>` → `projects/<ad>/edit.py` içindeki verileri doldur.
3. Önizlemeyle iterasyon yap:
   - `vlogkit build <ad> -s base` (bir kere)
   - `vlogkit preview <ad> -t ...` (altyazı değiştikçe)
4. `vlogkit build <ad>` → `vlogkit check <çıktı> --cuts`. Müzik korunuyorsa kesmeler kaynakla birebir aynı olmalı.
5. Deneme yapacaksan yeni bir **varyant** aç. Onaylı versiyon hiç ezilmez: `build/<ad>/<varyant>/`, `<çıktı>_<varyant>.mp4`.

Ayrıntılı süreç, parametreler ve öğrenilen tuzaklar için [`docs/workflow.md`](docs/workflow.md). Shorts güvenli alanları, ses seviyesi ve telif/lisans kuralları için [`docs/shorts.md`](docs/shorts.md). MrBeast dokümanı, Onur Naci Öztürkler, Jenny Hoyos ve Paddy Galloway'den derlenen izlenme süresi kontrol listesi için [`docs/viral-edit.md`](docs/viral-edit.md).

## Arayüz: vlogkit Stüdyo

**Açmak için:** Masaüstündeki **vlogkit Stüdyo**'ya çift tıkla ya da terminalden `uv run vlogkit open` (ön planda çalıştırmak için `uv run vlogkit ui`). Kısayolu yeniden oluşturmak için: `uv run vlogkit shortcut`. Sunucu arka planda açılır; kapatmak için sol alttaki ⏻.

**Kullanım:**
1. **Video:** Bilgisayardan, `~/yt-vlogs` kütüphanesinden ya da yol yapıştırarak ekle. Video, yazma kutusunun üstünde film şeridi olarak görünür.
2. **İstek:** Ne istediğini yaz. İstersen **Görev** menüsünden ya da ana ekrandaki çiplerden prompt rehberindeki bir şablonu seç; video yolu otomatik dolar, kalan `<alanlar>` "Doldur:" satırında listelenir.
3. **Gönder** (Enter; Shift+Enter yeni satır açar):
   - Claude Code abonelik girişinle arka planda (`claude -p`) çalışır.
   - Çalışırken adımlar "N adım · süre" satırında katlanır. Altında Claude'un son notu ve o an çalışan adım yerinde güncellenir ("Düşünüyor… 12 sn", "Yazıyor…" ya da çalışan komut ve süresi). Düşünce metninin kendisi headless modda gelmiyor.
   - Bitince cevap sade metin olarak gelir.
   - Üretilen video ve görseller önizlenir; "Finder" butonu dosyayı Finder'da gösterir.
4. **Devam:** "Önce plan" açıkken Claude plan gösterip durur. Alttaki kutuya "Onaylıyorum, derle." gibi yanıt yazarsın, oturum `--resume` ile devam eder. Çalışan iş **Durdur** ile kesilir.
   - **İş sürerken yazmak:** Claude Code'da mesaj hemen iletilir; Claude onu bir sonraki adımda (araç çağrısı arasında) alır ve aynı işe katar, terminaldeki gibi. Mesaj "İş sürerken eklendi" notuyla görünür. Claude cevabını bitirmişse mesaj yeni tur olur. İletilen mesaj geri alınamaz (✕ yok). Yeni bir klasörden dosya eklersen mesaj sıraya girer: çalışan ajan o klasörü okuyamaz, bir sonraki adımda izinle gider. Codex çalışırken mesaj alamıyor: orada mesaj sıraya girer, adım bitince sıradakiler tek mesaj olarak gider. İş durdurulur ya da hata verirse sıradakiler bekler: "Şimdi gönder" ya da ✕.
   - **Eforu değiştirmek:** Açık bir işte yazma kutusunun altındaki **Efor** seçimi, iş çalışırken de değişir. Claude yeni eforu bir sonraki adımında alır (çalışan sürece ayar olarak gider); Codex ve duran işler sonraki turda alır. Değişiklik sohbete not düşer.
   - **Mesajı düzenlemek:** Gönderdiğin bir mesajın yanındaki **Düzenle** (üstüne gelince görünür; iş çalışırken yok). Değiştirip gönderince o mesajdan sonraki turlar ayrılır (iş dosyasında `branches` altında saklanır) ve konuşma oradan yeni bir oturumla devam eder: ajan geçerli turların özetini ve ayrılan turlarda değişen dosyaların listesini alır. Dosya değişiklikleri geri alınmaz; ajan gerekirse geri alır. Claude ve Codex'te aynı çalışır.
   - **Taslaklar:** Her sohbetin gönderilmemiş yazısı kendinde kalır. Eklenen video yeni işle gider; bir sonraki "Yeni iş" boş başlar.
   - **Sıralama:** Sol menü son hareketlere göre sıralanır; yeni cevap gelen sohbet üste çıkar ve kalın görünür.
5. **Zaman çizelgesi:** Üretilen her videonun altında planlar, yazılar, bölümler ve notlar izler hâlinde görünür; tıkladığın ana gider (planı kayıtlı olmayan videoda planlar oynatınca bulunur).
   - **Yakınlaştırma:** +/−, ⌘ + tekerlek ya da iki parmakla sıkıştırma imlecin olduğu yere yakınlaşır; bir izde çift tık o bölgeye yakınlaşır; Shift + tekerlek ya da yana kaydırma pencereyi gezdirir. Yakınken üstte bütün videoyu gösteren ince bir şerit çıkar: pencereyi sürükleyebilir ya da bir yere tıklayabilirsin. Video oynarken pencere oynatma başlığını izler. Plan sayısı okunamayacak kadar çoksa çizelge ilk dakikayla açılır; "Tümü" bütün videoya döner.
   - **Bu ana yorum:** Mesaja `[01:23.4 · plan 12/40 · ...]` ekler; arkasına ne istediğini yazarsın ("bunu 0,5 sn kısalt").
   - **Kelimeler:** Konuşmayı kelime kelime gösterir. Tıkla: oradan oynat, Shift+tıkla: aralık seç, **Seçileni kes**: mesaja `Kes (çıktıda): ...` satırı ekler. Değişikliği Claude projede yapar.
6. **Kurgu ayarı:** Yazma kutusundaki **Kurgu** çipi: kaba kesim (temkinli / dengeli / sert), altyazı, müzik ve ses efekti açık/kapalı, ince kesim notu. Kaydedilir, yeni işlere eklenir.
7. **Lisanslar:** Sohbetteki videolarda kütüphaneden müzik ya da efekt varsa sağ üstte **Lisanslar** kartı çıkar: parça, yazar, lisans sayfası, Content ID kontrol tarihi; **İtiraz metnini kopyala** platformun telif talebine yapıştırılacak metni verir. Geniş ekranda açık, dar ekranda katlı başlar.
8. **Seçim kartları:** Claude dinleyerek ya da bakarak seçmen gereken seçenekleri (ör. `vlogkit music` ile sahnenin altında 3-5 müzik) cevabın altında kart olarak gösterir. Birini oynatınca diğerleri durur. **Bunu seç** yazma kutusuna "Seçim: 2. ..." yazar; istersen not ekleyip gönderirsin.
9. **Öneriler:** Claude iş sırasında vlogkit'e eklenmeye değer bir şey görürse cevabın altında bir **Öneri** kartı çıkar. **Öneriyi uygula** yazma kutusunu doldurur; gönderirsen Claude özelliği vlogkit'e ekler (test, belgeler, sürüm). Ürün böylece kullanırken gelişir.

**Kolaylıklar:**
- **Dosya eklemek (her mesajda):** Görsel, video ya da belge; ataç butonuyla, pencereye sürükleyip bırakarak ya da görseli ⌘V ile yapıştırarak. Konuşma ilerledikten sonra da olur.
  - Görseller `build/ui/attachments/` içine kopyalanır; iPhone HEIC fotoğrafı JPG'ye çevrilir.
  - Mesajla birlikte dosya yolları ajana "Ekler" olarak gider; ajan görsele bakar (Claude: Read, Codex: view_image). Gönderilen mesajda küçük önizleme görünür.
  - Ana ekranda ilk bırakılan video işin kaynağı olur.
- **Video eklemek:** Videoyu ya da klasörü pencereye sürükleyip bırakabilirsin. Tarayıcı dosyanın yolunu vermediği için stüdyo onu adı, boyutu ve tarihiyle `~/yt-vlogs`, Masaüstü, İndirilenler ve Filmler'de bulur. Bulamazsa `~/yt-vlogs/studyo-eklenen/` içine kopyalamayı önerir.
- **Arka planda:** Tarayıcı sekmesini kapatsan da işler sürer, sunucu sen ⏻ ile kapatana kadar açık kalır. İş sürerken Mac boşta uykuya geçmez (`caffeinate`); ekran kapanabilir.
- **İş bitince:** macOS bildirimi gelir. Tıklayınca işi açar (`terminal-notifier` varsa); sekme başlığında çalışırken ●, bitince ✓ görünür.
- **Silme:** Soldaki ✕ önce onay ister.

**Ayarlar (⋯):** Ajan, izin modu, model, efor, ek talimatlar, geçmiş, yerel video modeli ve ara dosyalar burada.
- **İlk açılış:** Claude Code ya da Codex kurulu ve girişli değilse karşılama ekranı çıkar: **Kur** satıcının kendi kurucusunu çalıştırır (Claude Code: resmi kurucu, Codex: Homebrew), **Giriş yap** Terminal'de giriş komutunu açar; ekran girişi kendisi görür. Eksik bir temel araç (ffmpeg, whisper, aubio) varsa onu da yazar.
- **Yerel video modeli:** Aynı modelin üç boyutu (Qwen3.5 2B / 4B / 9B, MLX 4-bit). Ekran Mac'in belleğini ve hangisinin uyduğunu gösterir; **Kur** ilerlemeyle indirir, seçilen model `log --vlm`, `ask` ve `face`'te kullanılır, **Kaldır** diski boşaltır. "Yok" seçilirse yerel model kullanılmaz. Seçim `build/vlm.json`'da; `VLOGKIT_VLM_MODEL` seçimi geçersiz kılar.
- **Güncelleme (kurulu kopyalarda):** Sol altta "Güncelleme var"; tıklayınca yenilikler ve **Güncelle**. İş çalışırken güncellenmez.
- **Modeller:** Listeler terminaldeki `/model` menüleriyle aynıdır. Claude Code'unki CLI'ın kendisinden okunur (günde en çok iki kez, model çağrısı yapmadan), Codex'inki `~/.codex/models_cache.json` dosyasından. Efor listesi seçilen modele göre değişir (Haiku'da yok, Codex modellerinde "Ultra"ya kadar). Varsayılan: Opus · 1M, Extra high.
- **Ajan:** Claude Code (varsayılan) ya da Codex. Codex, ChatGPT aboneliğinle `codex exec` üzerinden çalışır; `OPENAI_API_KEY` alt süreçte silinir. Varsayılan seçenek Codex'in kendi ayarındaki modeldir (şu an GPT-6-Astra); listeden başkası da seçilebilir. Güvenli modda Codex'in sandbox'ı yalnızca `~/yt-vlogs` ve uv önbelleğine yazar, `.git` salt okunurdur; commit için "Tam yetki" gerekir. Kuralları `CLAUDE.md` dosyasından okur.
- **Geçmiş:** İşler `build/ui/jobs/` klasöründe durur, stüdyo kapansa da kalır. Varsayılan: hiç silinmez (bir iş birkaç yüz KB). İstersen 3, 7 ya da 30 gün sonra silinir. Kenar çubuğunda iğne ikonuyla sabitlenen işler hiç silinmez. Silinen işin (elle ya da süre dolunca) istekleri, cevapları ve çıktıları video klasöründeki `VLOGKIT-NOTLAR.md` dosyasına yazılır.
- **Ara dosyalar (disk):** Derlemeler `build/<proje>/<varyant>/` altına büyük ara dosyalar yazar (base.mov ProRes 422 HQ: 4K'da 4 dakikaya ~27 GB). Varsayılan "Elle temizle": menüde boş yer ve kaç gündür derlenmeyen varyantlarda ne kadar yer açılacağı yazar; **Temizle** iki tıklamayla siler. 7, 14 ya da 30 gün seçersen o kadar gündür derlenmeyen varyantlarınki saatte bir silinir (iş çalışırken hiç). Teslim videoları, `log`/`analysis` kayıtları, önbellekler, başka yerden bağlı (hardlink) dosyalar ve başka bir projenin okuduğu varyant klasörleri kalır. Boş yer 30 GB'ın altına inince sol altta uyarı çıkar ve iş bitince sohbete not düşer. `build` başlamadan önce yazacağı yeri tahmin eder; yetmiyorsa hiç başlamaz.
- **Eski oturumlar:** Claude Code kendi oturum kayıtlarını 30 gün sonra siler (`cleanupPeriodDays`). Kaydı silinmiş bir işe yazarsan, stüdyo önceki turların özetiyle yeni bir oturum açar.
- **Güvenli:** `acceptEdits` + `.claude/settings.json` izin listesi.
- **Otomatik:** auto mode.

**İzinler:**
- **İzin var:** `uv run`, ffmpeg/ffprobe, whisper, aubio, temel dosya komutları, git status/diff/log/add/commit/push.
- **Yasak:** `sudo`, `rm -r`, force push, `git reset --hard`, `git clean`.
- **Nasıl veriliyor:** Arayüz bu dosyayı `--settings` ile verir. Headless modda projenin kendi ayarları, klasör Claude Code'da "güvenilir" onaylanmadıkça okunmuyor.
- **API faturası yok:** `ANTHROPIC_API_KEY` alt süreçte silinir, kullanım aboneliğinin limitinden düşer.

**Güvenlik:**
- Sunucu sadece `127.0.0.1`'de dinler.
- Her açılışta yeni bir erişim anahtarı üretilir, Host başlığı kontrol edilir.
- Sadece `~/yt-vlogs`, `build/` ve seçtiğin yollar sunulur.
- İş geçmişi `build/ui/jobs/` klasöründe, arka plan sunucu günlüğü `build/ui/server.log` dosyasında tutulur.

## Sürümler ve dağıtım

- **Geliştirme:** Bu repo (`dev` → `main`). Kişisel projeler, notlar ve testler burada kalır.
- **Yayın:** `main`'e her birleştirmeden sonra `uv run python scripts/release.py`. Yalnız araç kodu herkese açık [vlogkit-studio](https://github.com/abdulkadirerdem/vlogkit-studio) reposuna `v<sürüm>` etiketiyle gider. Dışarıda kalanlar: `projects/` (şablon hariç), `recipes/`, `assets/vocab.txt`, `tests/`. Herkese açık CHANGELOG 0.14.0'dan başlar, proje maddeleri çıkarılır. Ev klasörünün yolu, git e-postası ya da `scripts/private-terms.txt`'teki bir terim (kişi adları, özel ayrıntılar; tam kelime) bir dosyada geçerse yayın durur; bu liste yayınlanmaz. Commit'ler GitHub hesabının noreply adresiyle atılır, bilgisayarın adı görünmez. Uzak depo silinip yeniden açılsa bile eski yerel geçmiş itilmez; itme başarısız olursa geride etiket kalmaz. `--dry-run --keep KLASÖR` neyin gideceğini gösterir. Aynı sürüm ikinci kez yayınlanmaz: önce sürümü artır.
- **Kurulu kopyalar:** `install.sh` yayın reposunu klonlar (`.release` dosyası bunu belirtir). Stüdyo 6 saatte bir yeni etiketi sorar; yeni sürüm varsa sol altta "Güncelleme var" çıkar. Güncelleme kopyayı o etikete taşır, `uv sync --frozen` ve `assets fetch` çalıştırır, Stüdyo'yu yeniden başlatır; sayfa yeni sunucuyu görünce kendini yeniler. Bir adım başarısız olursa kopya eski commit'ine, ortamına ve elle yapılmış değişikliklerine geri döner. Kopyada atılmış commit'ler `yedek-<tarih>` dalında kalır. Güncelleme sürerken yeni iş başlatılmaz. Kullanıcının projeleri, derlemeleri, sözlüğü ve `assets/manifest.local.toml` git dışında kalır; elle değişmiş araç dosyaları silinmez, `git stash`'e gider.
- **Kurulu kopyada ajan** vlogkit'in kendi dosyalarını değiştirmez ("vlogkit'i geliştir" görevleri gizli, öneriler "Kopyala" ile geliştiriciye iletilir).

## Lisans

[PolyForm Noncommercial 1.0.0](LICENSE) ve bir ek izin: vlogkit ile kendi videolarını yapıp yayınlamak, para kazanan kanallarda da serbest. Yazılımı satmak, ücretli hizmet olarak sunmak ya da ticari bir ürüne katmak yazılı izin ister. Haklar geliştiricide kalır. Fontlar (OFL) ve `assets/manifest.toml`'daki medya kendi lisanslarıyla gelir.

## Prompt rehberi

Claude'a verilecek hazır prompt'lar (keşif, Shorts, uzun video, revizyon, yayın, vlogkit'i geliştirme): **[vlogkit Prompt Rehberi](https://claude.ai/artifact/WQakjmnPnJ95AJ1kyQPdPW)**.
- **Kaynak:** [`docs/prompts.md`](docs/prompts.md).
- **Güncelleme:** vlogkit'e yeni bir yetenek eklendiğinde `docs/prompts.md` güncellenir. `uv run python scripts/build_prompts_page.py --out <dosya>` ile sayfa üretilir ve artifact aynı adrese yeniden yayınlanır.

## Geliştirme

```bash
uv run pytest            # testler (ffmpeg yoksa entegrasyon testleri atlanır)
uv run ruff check .      # lint
uv run ruff format .     # format
```

**Kurallar:**
- ffmpeg komutları her zaman argüman listesiyle çalıştırılır, shell string'i kullanılmaz.
- Zamana bağlı ifadeler `video/expr.py` yardımcılarıyla yazılır (`window`, `nan_safe`).
- Yeni bir tuzakla karşılaşınca `docs/workflow.md` dosyasına ve bir regresyon testine eklenir.

## Yol haritası

- [x] Yatay (16:9) uzun video düzeni: `style.LANDSCAPE`, bölüm kartı, altyazı, SRT, YouTube bölümleri (0.4.0)
- [x] 4K uzun video: `style.LANDSCAPE_4K` (grafikler 4K'da çizilir), `TitleCard` soğuk açılış başlığı
- [ ] Konuşmalı videolarda whisper kelime zamanlarından otomatik karaoke altyazı
- [ ] Müzikli seste segment zamanları kaba (tam saniyelere yuvarlanıyor): VAD veya kelime modundan segment üret
- [ ] Basit projeler için `timeline.yaml` (kodsuz altyazı/SFX/zoom listesi)
- [ ] DaVinci Resolve'a export: timeline (FCPXML/OTIO), overlay'i V2'ye, sesleri ayrı kanallara koyup elle ince ayar
- [ ] `analyze` raporunu HTML'e çevirmek (kontak sayfası + zaman çizelgesi bir arada)
- [ ] Kalite kontrolü (`check`) içine altyazıların güvenli alan dışına taşma kontrolü

### Yüksek bit derinliğinde parlaklık analizi

`vlogkit analyze` 8/10/12/16-bit videoların luma ölçümünü ortak 0–255 referansında yapar. Loş sahne eşikleri bit derinliğinden bağımsızdır; bu yalnız analiz dönüşümüdür, kaynak medyayı değiştirmez ve HDR ton eşleme yapmaz.
