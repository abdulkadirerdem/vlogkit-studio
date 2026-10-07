# İş akışı ve öğrenilenler

Kackar Short 01'i kurgularken oturan süreç. Her yeni edit bu sırayla gider.

## 0. Ham çekim kaydı (`vlogkit log`): önce kaydet, sonra kes

Seyrek bakışla yapılan kurgu anlamsız anlar seçer: kameraya eğilme, kaydı başlatma/durdurma, lensin önünden geçme. 28-09 vlogunda "evden çıkış" yerine kameraya eğilinen 1-2 sn konmuştu.

- **Nasıl çalışır:** Her klip tek geçişte çözülür (media engine + GPU ölçekleme; 4K HEVC gerçek zamanın ~6 katı). Klip, kesmeler ve ~4 sn'lik parçalar halinde bölünür.
  - Her parçada şunlar var: Vision etiketi (kapı, merdiven, sokak...), yüz boyu, hareket, netlik, parlaklık, konuşma.
  - Klibin tamamını kapsayan zaman damgalı sayfalar çıkar: klip 60 sn'ye kadarsa 1 sn'de, 5 dk'ya kadarsa 2 sn'de, daha uzunsa 4 sn'de bir kare.
- **`kurulum` bayrağı:**
  - Klibin başı ve sonu, görüntü oturana kadar kurulum sayılır; bu kısım yakın anlarla zincirlenir.
  - Ortada ise ancak kameraya dokunma izi varsa kurulum sayılır: lens kapalı ya da karanlık, sabit arka planın bir kısmı gizlenmiş, dev ya da kenardan kesilen yüz, sarsıntı, bulanıklık.
  - Tüm ölçüler klibe göredir: gece klibi "karanlık", selfie yüzü "çok yakın" sayılmaz.
- **Engelleyen bayraklar:** `kurulum`, `karanlık`, `bulanık`. `çok yakın` ve `sarsıntı` yalnız bilgi. `keep: true` hepsini geçersiz kılar.
- **Anlamla arama (`vlogkit find KLASÖR kelimeler...`, `analysis/find.py`):** Log'daki her parçanın `desc`, `beat`, yerel modelin cümlesi (İngilizce), Vision etiketleri ve konuşması içinde arar. Kelimeleri iki dilde ver ("ateş fire campfire"). Büyük/küçük harf ve Türkçe harf fark etmez (göl = gol); kelime başı eşleşir, ek gizlemez ("göl" → "gölde"); model sütununda 4+ harfli kelime birleşik kelimenin içinde de bulunur ("fire" → "campfire"). Sıra: en iyi parçanın eşleşen kelime sayısı, sonra alan ağırlığı (desc/beat 3, model ve konuşma 2, etiket 1). Komşu eşleşmeler en fazla 16 sn'lik aralık olur; bayraklı parçalar ayrı satır ve en sonda. Her sonuç için 3 kare: `build/find/`. 3 harfli kelime ilgisiz uzun kelimeye de çarpabilir ("göl" / "gölge"): kareye bak.
- **İş bölümü:** Bayraklar yalnız kamera kullanımını söyler, anlamı söylemez. Anlamı Claude sayfalara bakıp `desc` / `beat` alanlarına yazar (`CLAUDE.md` 1. adım). Kurgu, hikâye adımları ve her adımın en iyi parçasıyla kurulur. `footage.selects(log)` kullanılabilir aralıkları verir.
- **Hız:** 28-09 vlogu (24 klip, 52 dk 4K) 6-7 dk'da loglandı; önbellekten 1 sn.
- **Doğruluk:** 0005'te 0:00-0:21 (kamerayı merdivene koyma) ve 1:06-1:11 (geri gelip kamerayı alma) `kurulum` işaretlendi; kapıdan çıkış ve ayakkabı giyme temiz kaldı.
- **Bilinen kaçırmalar:** Başsız gövde ya da kol karanlık ya da hareketli sahnede kaçabiliyor. Kadrajın dibinden girip çıkmak da `kurulum` sayılıyor.
- **Sonrası:** Derleme bitince `vlogkit review` plan sayfası (her planın orta karesi) ile kontrol et.

**Yerel video modeli (`vlogkit log --vlm`, `vlogkit ask`, `vlogkit face`):**
- **Ne yapar:** Qwen3.5-9B (4-bit MLX, Apache-2.0, 5,6 GB) her ~4 sn'lik parçayı 4 kare/sn izler ve log.md'ye tek cümlelik bir gözlem yazar ("model" sütunu, İngilizce). Kontak sayfası seyrek kare gösterir; model hareketi görür: kapıdan çıkma, ayakkabı giyme, lense uzanma.
- **Kurulum:** mlx-vlm ayrı bir `uv tool` ortamında (`vlogkit extras install vlm`); vlogkit'in kendi ortamı hafif kalır. Worker (`tools/vlm/worker.py`) modeli bir kez yükler.
- **Hız:** 2 kare/sn yönü karıştırıyordu, 4 kare/sn doğru buldu. 40 sn'lik pencerede zaman damgalı olay listesi ise uydurma ve eksik JSON verdi; bu yüzden parça başına soruluyor. 28-09 klasörü (52 dk) 44 dk sürdü, düşük öncelikte (nice). Önbellekli, kesilirse kaldığı yerden devam eder.
- **Doğruluk:** Model aday bulucudur, hakem değil. Yönü karıştırabilir (0005'te "giyiyor" yerine "çıkarıyor"). Kamera kullanımında yanlış alarm verebilir (`kurulum?` sadece "bak" demek). Kullanışlılık puanı ayırt etmez (802 parçanın 734'ü "2"). Sezgisel `kurulum` ile uyum %91; modelin tek başına yakaladığı "lensi elle kapatma" gibi anlar da var.
- **Doğrulama:** Bir adayı kullanmadan önce sayfaya bak ya da `vlogkit ask VIDEO --start --end "soru"` ile tam kare hızında sor (en fazla 60 sn; 24 sn ~20 sn sürer).
- **Mimik (`vlogkit face VIDEO --start --end`):** Tam kare modelde yüz ~100 px kalıyor ve karanlık perdede ifade okunmuyor. Bu yüzden Apple Vision yüzü 2 kare/sn takip eder, kare bir yakın plan kesilir (yüz yüksekliğinin ~2,6 katı), aydınlatılır ve 512 px'te modele verilir. Çıktı: ifade (zaman içinde), enerji, gülümseme, gülme, kameraya bakış, tuhaflık ve anlar. Rize denemesinde (8 sn) "nötr → hafif gülümseme → ciddi → kaşlar kalkık" dedi, 21 sn sürdü. Anların saniyelerini bazen klip süresinden uzun uyduruyor; süre dışındakiler atılıyor, kalanlar da yaklaşık. Sesi duymaz: tonu ve espriyi transcript'ten al. Serbest soru için `vlogkit ask ... --face`.
- **Isı:** Mac'i ısıtır; build ya da render ile aynı anda çalıştırma.

## 1. Analiz: kesmeden önce bak

| Soru | Araç | Not |
|---|---|---|
| Format ne? | `ff.probe`, `vlogkit check` | Telefon/GoPro "30 fps" = 30000/1001 (29.97). Her şeyi kare hassasiyetinde düşün. |
| Neler oluyor? | `vlogkit sheet` (0.1 sn'lik kontak sayfası) | Altyazıyı doğru kareye oturtmanın tek yolu. Hareketin başladığı kareyi bul. |
| Kesmeler nerede? | `analysis.scenes.detect_cuts` (`scdet=threshold=8`) | Zoom ve renk pencereleri kesmelere göre çizilir. Render sonrası doğrulama da bununla yapılır. |
| Loş yerler? | `analysis.luma` (signalstats YAVG) | 45'in altı loş. `grade.lift` ile gamma artır; plan içinde aydınlanma varsa `fade_out` kullan. |
| Ses yapısı? | spektrogram, `loudness.momentary`, `beats` | Müzik mi, konuşma mı, ortam sesi mi? Müziğin "açıldığı" an iyi bir kesme noktasıdır. |
| Konuşma? | `vlogkit transcribe` | **Önbellekli:** aynı dosya ve ayarlar `build/cache/transcripts`'ten gelir (review, gaps, strip ve Stüdyo aynı kelimeleri ister). **Özel adlar:** `assets/vocab.txt` (satır başına bir ad) whisper'a ipucu olarak verilir; whisper ipucunu sessizlikte aynen tekrar ederse o satır atılır. Müzikte adları uyduruyorsa `--no-vocab`. **Sadece müzik varsa Whisper halüsinasyon üretir:** "İzlediğiniz için teşekkür ederim", "Altyazı M.K.", "中文字幕" gibi. `Segment.suspicious` bunları işaretler. Müzik altındaki konuşmayı kısa pencerelerle `--no-context --beam 5` ile, birkaç dilde tara; sadece tutarlı çıkan satırı kullan. |
| Siyah bant? | `analysis.letterbox.active_area` | Yeniden dışa aktarılmış videolarda yatay görüntü dikey kanvasta olabilir (464x832 içinde 464x262). `analyze` bunu bulur, parlaklığı sadece görüntüde ölçer. |
| Kare hızı sabit mi? | `analyze` raporu | `r_frame_rate` 60 ama ortalama 32 ise değişken kare hızı: filtre zincirine önce `reframe.cfr` koy. |
| Tam olarak nereden kesilecek? | `vlogkit strip VIDEO --start --end [-m SN]` (`analysis.strip`) | Tek görsel: 10 kare, ses dalgası, 0,4 sn'den uzun sessiz bantlar (mavi), whisper kelimeleri zamanlarında, kırmızı aday çizgileri. En fazla 180 sn; kelimeler 60 sn'ye kadar. Kelimeler önbellekli transcript'ten gelir. |
| Kare nerede, koordinat ne? | `vlogkit frame VIDEO -t SN`, `vlogkit preview PROJE -t SN --grid` | Tek kare 1280 px, 0-1 ızgara (0,1 adımlı, 0,5 sarı, üçte birler mavi kesikli), kare numarası ve kaynak boyutu. Kırpma `x`'i, yüz konumu ve grafik yeri ızgaradan okunur. Kontak sayfaları da her karenin kaynak kare numarasını yazar (`12.345 #370`). |
| Konuşmada boşluk / dolgu? | `vlogkit gaps` (`analysis.speech`) | Whisper kelime aralıkları + silencedetect. Whisper "ııı/eee"yi çoğu zaman yazmaz; bunlar kelimeler arası *duraklama* olarak yakalanır. 2,5 sn'den uzun konuşmasız bölümler ("konuşmasız") vlogda genelde aksiyondur (koşu, manzara): isteğe bağlıdır, varsayılan olarak kesilmez. "yani/şey" de isteğe bağlı. |
| Kapak karesi? | `vlogkit thumbs` (`analysis.thumbs`) | Kaynak görüntüde çalıştır (üstünde yazı olmasın). Netlik + renklilik + pozlama puanı; kesmeye yakın kareler atlanır. Yüz tanıma yok: adayları sayfada görüp seç. Otomatik seçim yan dönük ya da anlamsız kareyi de seçebilir: hikâyeye göre kareyi kendin seç, 4K'dan `thumbnail.design` ile kur (odak + zoom, yüze ışık, kenar karartma, `Words` / `Badge`), `check_sheet` ile 640 / 360 / 168 px'te ve süre etiketiyle kontrol et. Kişiyi başka bir kareden kesip koymak için `analysis.segment.mask` + `cutout` + `bloat` + `Subject`: bakış vaade (göl, yazı) dönsün (gerekirse aynala), kalkık kol kadraj dışına taşsın, arka plan insansız bir kare olsun. MrBeast tarzı set için tek fikir başına bir kapak: önce/sonra `split` ("0 M | 2800 M"), küçük şeye `Ring` + tek `Arrow`, yorgun yüz + bitmeyen yol ("GÖL NEREDE?"). Kişi başka bir kareden alınacaksa aynı kişi olduğundan emin ol (gözlüklü arkadaşı "sen" diye kesme). Bir kareden insan silmek için `segment.mask` + `clone_fill`; gölgeli ve güneşli bölgeleri ayrı kaynaklardan doldur (tek kaydırma gölgeli yamaca açık leke bırakır), yeni kişiyi silinen yere koy. Kullanıcı süreleri son kurgudan (ör. EDIT_2) verir: kaynağa çevir. Tema efekti (ör. soğuk suya giriş) için `frost_fx` + `Sticker(blend="screen")`; köşeye koy, yüze ve yazıya değdirme. Hazır buz/ateş görseli lisanslı değilse prosedürel efekti kullan. |

**Bilgi kaynağı:** Uzun videodaki konuşmalar (ör. gece öncesi anlatım) altyazılar için gerçek bilgi verir: saatler, sayılar, şakalar. Uydurma altyazı yazma.

## 2. Kurgu kararları

- **Hook:** İlk 1–3 saniye her şeydir. Sonucu önce göster (dağda tırmanış, kendi sesin), sonra "⏪ geri saralım".
- **Müziğe dokunma:** Kaynak kurgu müziğe göre kesilmişse ses zaman çizelgesini sabit tut ve sadece görüntüyü değiştir (yeniden kurgu, ekleme, efekt). Kontrol: çıktının kesmeleri kaynakla birebir aynı olmalı.
- **Müzikli kurgudan bir parça çıkarmak** (kullanıcı isterse; `kackar-run-p3` v7): Müzik de kesilir. Atlamayı kareye tam denk gelen adaylar arasından, müziğin (Demucs `no_vocals`) iki yakası en iyi örtüşecek şekilde seç: dalga biçimi, zarf ve başlangıçlar. Görüntü plan sınırında atlar. Ses aynı uzunlukta ama sözün hemen öncesinde atlar (J-cut) ve kısa `acrossfade` alır; böylece dudak senkronu korunur. Aubio vuruş ızgarası bu iş için fazla oynak çıktı (0,38–0,42 sn).
- **Zoom'lar planın içinde kalır:** Pencere bir planda başlar ve aynı planda biter. Aksi halde plan ortasında zıplama görünür. `Zoom().push/punch/snap`.
- **Varyantlar:** Deneme = yeni varyant. Onaylı çıktı asla ezilmez.
- **İzlenme süresi:** Plan `docs/viral-edit.md` kontrol listesine göre yapılır (vaat, ilk saniye, tempo, yeniden yakalama, bitiş). Loop ve kanca A/B denemesi isteğe bağlıdır.
- **Boşluk kesme (A-cut):** `gaps` adayları planda tablo olarak gösterilir; onaylananlar `speech.keep_segments` → `video.jumpcut.jumpcut(src, keep, video, audio)`. Kesmeler kaynak karelerine oturur, her ses parçası 10 ms fade alır (yoksa tık sesi). Kaynağa göre zamanlanmış her şey (altyazı, SFX, zoom) `jumpcut.remap(t, keep)` ile yeni zaman çizelgesine taşınır. Değişken kare hızlı kaynakta önce `reframe.cfr`.

## 3. Görüntü

- **Renk:** `INDOOR_WARM` (loş iç mekân) / `OUTDOOR_MILD` (parlak dış mekân). Zamana bağlı değerler string ifade olarak verilir (`Grade.but(gamma="1.07*(...)")`).
- **Otomatik ışık:** `grade.auto_lift(luma_curve, kesmeler)` her plan için gamma artışı hesaplar, kesmede adım atar, plan içinde yumuşakça kayar (oda turu karanlığa dönerken). `max_amount=0.3` gece planlarını gece bırakır. `Grade.but(gamma=f"(1+{expr.piecewise(keys)})")`.
- **Yatay teslim (16:9):** `Edit.layout = LANDSCAPE`, `preset = YOUTUBE_LONG`. Düşük çözünürlüklü kaynağı büyütürken `reframe.upscale`: kaynak boyutunda deblock + denoise, lanczos, sonra CAS keskinlik (çıplak lanczos makro blokları büyütür).
- **4K teslim:** 4K kaynağı 4K bırak: `Edit.layout = LANDSCAPE_4K` (grafikler 1080p tasarımının iki katı boyutta, doğrudan 4K çizilir), `zoom_crop(..., 3840, 2160)`. Push/punch 4K'da görüntüyü büyütür: %8'i geçme. 4K ProRes ara dosyası ~1,4 Gbps (3 dk ≈ 30 GB) ve ~5 kare/sn'de derlenir; overlay ile paralel çalıştırılabilir.
- **Dikey kırpma (16:9 → 9:16):** Kaynak 4K ise önce 1215×2160 kırp, sonra 1080×1920'ye ölçekle; kalite kaybı olmaz. `x` ifadesiyle yüzü takip et.
- **Ara dosya:** ProRes 422 HQ 10-bit. Grafik katmanı ProRes 4444 (alfa kanallı).
- **Apple VT (`video/vt.py`, `vlogkit upscale` / `slowmo`; macOS 26 + Apple silicon):**
  - **Büyütme:** Düşük çözünürlüklü kaynağı büyütürken (aktif görüntü < 720p) `vt.upscale(src, out, vf=kırpma, target=(1920, 1080))`. Apple'ın gürültü filtresi + ML 4x süper çözünürlüğü, lanczos + CAS'ın büyüttüğü bulanıklık ve blokların yerine temiz kenar kurar. Düşük çözünürlüklü bir ekran kaydında çizgiler ve etiketler belirgin şekilde daha net, halo yok.
  - **Sınırlar:** Hareket bulanıklığıyla kaybolan detayı geri getiremez. Girdi en fazla 1920x1080, ölçek yalnız 4x.
  - **Ton:** Model tonu birkaç yüzde kaydırır; sarmalayıcı kaynağa göre ölçüp düzeltir.
  - **Hız:** 464x262 girdide ~14 kare/sn; 4,5 dakikalık video ~10 dakika.
  - **Diğer işlemler:** `vt.interpolate(factor=2)` gerçek ara kareli yavaş çekim verir; hız rampasında kare tekrarından çok daha akıcıdır. Taneli (gece, mavi saat) planı yavaşlatırken `denoise=1.0` ver: ara kareler gerçeklerden pürüzsüz çıkar ve yavaş çekimde tane karede bir titrer; filtre ara kareden *sonra* çalışınca eşitlenir (4K'da da çalışır, 5 sn'lik plan ~1 dk). `vt.motion_blur` hızlı bölümlere doğal hareket bulanıklığı ekler. `vt.denoise` tek başına çok hızlıdır.
  - **Ne zaman değil:** Minik kaynaktan 9:16 tam boy kırpma: 464x262'den dikey kırpma ~147 px genişlik bırakır. Böyle kaynakta "pencere + bulanık arka plan" düzeni kullan. Zaten 1080p olan görüntüde de gerek yok. Değişken kare hızlı kaynakta önce `reframe.cfr`.
  - **Tuzak:** Frame rate conversion ve motion blur işlemcileri kapanırken macOS 26.4'te çöküyor. Araç dosyayı bitirip `exit(0)` ile çıkar. Başı boş edit list olan dosyada AVFoundation 1 kare ekler; girdi her zaman 0'dan başlayan ProRes olarak hazırlanır.
- **Renk eşleme (`video/colormatch.py`, `vlogkit match-color`):** Bir planı beğenilen bir kareye (başka plan ya da fotoğraf) benzetir. Hedeften 5 kare (ya da `--at`), referanstan bir kare ölçülür. Oklab'da ışık (p10/p50/p90), beyaz dengesi (en az renkli dörtte bir) ve doygunluk eşlenir. Çıktı 33'lük bir `.cube` ve yanında önce/sonra/referans görseli.
  - Kullanım: grade zincirinde Grade'den önce `colormatch.lut_filter(cube)`. Zincir 10-bit kalır: filtre görüntüyü `gbrp16le`'ye çevirip uygular. 4K'da kare başına ~10 ms ekler.
  - Güvenlik: kontrast ve doygunluk 0,6-1,6 kat, ışık en fazla ±15 (orta griye göre ~1 stop). Siyah ve patlamış beyaz yerinde kalır. Varsayılan güç 0,8; bilinen bir bozulmayı geri alırken 1,0 daha kötü çıktı.
  - Sınır: İstatistik içeriğe bakar. Referans benzer bir sahne olmalı (gökyüzü/zemin oranı, koyu giysi). İçerik çok farklıysa (ahşap duvar, kaya yakın planı) ışığı ve doygunluğu yanlış yöne çeker. Benzer anları `--at`/`--ref-at` ile seç ya da `--strength 0.5` kullan. Önce/sonra görseline bakmadan uygulama. Yalnız SDR Rec.709 (D-Log/HLG değil).
- **Yüz ve plaka gizleme, tek kişiyi vurgulama (`video/redact.py`, `vlogkit redact`):** Hareket eden bir şeyi Apple Vision ile takip eder. ffmpeg tek geçişte 10-bit işler; çıktı kaynak boyunda ProRes HQ, kaynağın sesi ve renk etiketleriyle.
  - Yüzler: `redact VIDEO --faces --start S --duration D`. Vision saniyede 8 kez bakar: tüm kare ve 3x3 örtüşen parça (tek başına tüm kare, kalabalıktaki küçük yüzlerin çoğunu kaçırıyor). Yüzler izlere bağlanır, arası doldurulur, kutu saç ve çene için büyütülür.
  - `--keep-main` senin yüzünü açık bırakır: en büyük, ortaya yakın ve aralığın en az yarısında ekranda olan yüz. Öyle bir yüz yoksa hepsi bulanıklaşır.
  - Tek şey (plaka, kişi, hayvan): kutuyu `frame VIDEO -t SN` ızgarasından oku, `--box x,y,en,boy@SN` ver. Takip ileri gider; Vision kaybedince orada biter ve komut "kayboldu" yazar. Sonrası için o andan yeni bir `--box` ver.
  - "Şu kartala bak": `--mode spotlight --box ...`. Gerisi kararır ve biraz solar. Işık takip başlayınca 0,4 sn'de açılır, bitince söner.
  - Bulanıklık en büyük kutuya göre artar; yakın yüz de okunmaz.
  - Hız: 4K'da yüz taraması gerçek zamanın ~4 katı, nesne takibi ~5 katı hızlı; render ~40-50 kare/sn. 4K ProRes saniyede ~100 MB yer tutar.
  - Sınırlar: Kalabalıkta güneş gözlüklü, şapkalı, yan ya da arkası dönük yüzlerin bir kısmı kaçar (Kaçkar start alanında görünenlerin kabaca üçte ikisi bulundu). Gizlilik gerekiyorsa çıktının sayfasına bak, kaçanlara `--box` ekle.
  - Takip kutusu boyunu pek değiştirmez: kameraya yürüyen kişide kutu baş ve göğse kayar, spot ışığı yukarıda kalır.
  - Yalnız kullanılan parçayı işle; yüzlerce kutu render'ı yavaşlatır (300 kutu, 1080p: ~6 kare/sn).
- **Stabilizasyon (`video/stabilize.py`, `vlogkit stabilize`):** Telefonla koşarken çekilen titrek planlar için vid.stab, iki geçiş. `analyze` titremeyi ölçer, `transform_filter` kamera yolunu yumuşatır.
  - Hazır ayarlar: `running` (güçlü yumuşatma, uyarlanır zoom), `walking`, `tripod-ish` (sabit durması gereken el çekimi).
  - Plan plan uygula, kesme içeren parçaya uygulama. İki geçiş aynı kareleri görmeli (aynı `start`/`duration`); kare sayısı değişmez.
  - vid.stab yalnız 8-bit çalışır: zincirin başına koy, arkasından `format=yuv422p10le` gelsin.
  - Sadece ham görüntüye uygula. Üstüne yazı gömülmüş kurgulu klipte yazı da sallanır; selfie planlarda yüz kayabilir.
  - DJI gimbal görüntüsünün buna ihtiyacı yok (ölçüm: 28-09-vlog ham kliplerinde sarsıntı ~0).
- **Arka plan değiştirme (`video/background.py`, `vlogkit background`):** Perde önünde, loş ışıkta çekilen konuşmaların arkasını değiştirir. Apple Vision her karede kişiyi ayırır (hybrid: keskin saç çizgisi, sadece insan), ffmpeg 10-bit birleştirir, çıktı kaynak boyunda ProRes HQ.
  - `--bg`: `studio` (kişinin arkasında yumuşak ışık + vinyet), `keep` (perde kalır, arkasında sıcak bir arka ışık; `keep:#ffd8a8:0.5`), `#renk`, `gradient:#üst,#alt`, resim, `klip.mp4@sn`, `frame:klip.mp4@sn` (başka çekimden tek kare).
  - "Arkama bulanık Rize manzarası koy": ham klasörden insan olmayan bir manzara karesi seç (`sheet`), sonra `background TAKE --bg frame:ham/KLIP.MP4@60 --blur 18 --match --start S --duration D`. Parlak gündüz manzarasında `--match` hep açık: kişiyi biraz açar, manzarayı kısar.
  - Yalnız kullanılan parçayı işle: 4K'da uçtan uca ~10 kare/sn (1 dk ≈ 3 dk). El kamerası klibi arkada sallanır; `frame:` ile tek kare kullan.
  - Sınırlar: hızlı el/kol hareketinin bulanıklığı kolun etrafında koyu bir kenar olarak kalır; ince saç telleri düz bir kontura iner. Yalnız BT.709 kaynak doğru çevrilir (telefonun BT.601 ya da HDR arka planı değil).

## 3b. Efektler (`video/fx.py`)

İki tür var:
- **Segment efektleri (`SpeedRamp`, `Freeze`):** Segmentin süresini değiştirir. concat'ten önce tek segmente uygulanır; kaç kare çıkaracakları Python'da bilinir (`.frames`), müzik ve altyazı buna göre planlanır.
  - `SpeedRamp.through(3, peak=4)`: 1x→4x→1x yumuşak hız rampası. Yavaşlatmada (<1x) kareler tekrarlanır, optik akış yok.
  - Rampanın sesi için iki yol var. Kaynak sesi kapatıp `ramp_whoosh` kullan (whoosh en hızlı ana oturur; güvenli varsayılan) ya da `ramp_audio` (tempo, perde korunur; `gain=0.3` ile kısılır).
  - `Freeze(kare, hold=1, punch=0.08, photo=True)`: kareyi dondurur; flaş, siyah-beyaz ve kontrast, yavaş zoom.
- **Kesme efektleri (`Glitch`, `WhipPan`, birlikte `CutFX`):** Birleşmiş zaman çizelgesinde kesmenin etrafındaki birkaç kareye dokunur, süre değişmez. Kare numarasıyla açılır; pencere dışındaki kareler bit bit aynı kalır (test: framemd5). `WhipPan(angle=90)` dikey savurma.
- **Doz:** Efekt bir anı vurgulamak içindir; her kesmeye koyma. Short'ta 1-3 tane yeter.
- **Kural:** 10-bit ara dosyada `noise`, `vignette`, `eq`, `curves`, `drawbox`, `rgbashift` kullanma. ffmpeg her kareyi 8-bit'e çevirip geri çevirir, efektin dışındaki kareler de değişir. Bunların yerine `geq`, `lutyuv`, `hue`, `scroll`, `dblur` kullan.

## 4. Grafik

- Tasarım dili ve güvenli alanlar: `graphics/style.py`, ayrıntısı [`shorts.md`](shorts.md).
- **Metin:** `[vurgu]` sarı yapılır. Emoji Apple Color Emoji ile 160 px'te çizilir.
- **Emoji dozu:** En fazla üç altyazıda bir emoji, altyazı başına tek emoji, sadece anlam katıyorsa. Konuşma altyazısında (`Subtitle`) hiç yok. `overlay` adımı kural aşılınca `!` satırıyla uyarır (`graphics.emoji_notes`; ZWJ dizileri, ten rengi ve bayraklar tek sayılır). Kaçkar Short 01'de 10 altyazının 9'unda emoji vardı; fazla geldi.
- **Semboller:** `▶` ve `⏪` emoji kutusu olarak çıkıyor; ikon lazımsa polygon çiz (`RewindFX.icon`). Çince/Japonca karakterler otomatik olarak Hiragino Sans GB ile çizilir.
- **Düzen:** `style.VERTICAL` (Shorts) ve `style.LANDSCAPE` (YouTube, 1920x1080, %90 başlık-güvenli alan). Yeni öğeler `layout=` alır.
- **Uzun video öğeleri:** `ChapterCard` (sol üstte bölüm kartı), `Subtitle` (konuşma altyazısı, pop yok), `EndCard(layout=...)`. Altyazı verisi tek liste (`export.subtitles.Cue`): hem videoya gömülür hem `.srt` olur.
- **Karaoke:** Kelimeler taban çizgisine hizalı (`keep_v=True`). Ekranda 1–4 kelimelik parçalar olsun.
- **Önizleme:** `vlogkit preview` önce gerçek karenin üstünde bakar, sonra render alırsın.

## 5. Ses

- **Konuşma altında müzik:** ~-10 dB (0.32).
- **Müzik seçimi (`audio/audition.py`, `vlogkit music`):** Ajan müziği dinleyemez; etiket ve açıklamayla seçilen telifsiz parça çoğu zaman sahneye uymuyordu (Rize adaylarının hiçbiri dinlenmemişti). Kural: 3-5 aday, sahnenin altında önizleme, seçimi kullanıcı yapar. Sahne bir kez küçük (uzun kenar 960) işlenir; her parça yalnız ses olarak üstüne karışır (`-c:v copy`, 5 aday ~3 sn). Parça, 3 sn'lik pencerelerin %80'lik seviyesine 3 LU yaklaştığı ilk yerin 1 sn öncesinden başlar: uzun sessiz girişler seçimi belirlemez; sahne süresi parçaya sığacak şekilde geri çekilir. `id@sn` başlangıcı sabitler, `@0` baştan çalar. Müzik `loudnorm` ile `--level` LUFS'a (varsayılan -20, konuşmasız sahnede -16) getirilir; `loudnorm` 192 kHz verir, arkasından `aresample=48000` şart. Sahnenin kendi müziği varsa `--no-sound`.
- **Seçim bloğu:** "Seçim: soru" satırı ve altında `N. etiket — /mutlak/yol` maddeleri. Stüdyo bunu önizlemeli kartlara çevirir, "Bunu seç" yazma kutusuna `Seçim: N. etiket` yazar; terminalde düz liste olarak okunur. Müzik dışında kapak ve renk seçeneklerinde de kullanılır.
- **Telefon ve kamera sesini eşleme (`audio/sync.py`, `vlogkit sync KAMERA TELEFON`):** İki kaydın ses zarfını karşılaştırıp telefonun 0. saniyesinin kamerada kaçıncı saniye olduğunu verir (~1 ms). Güven 0,4'ün altındaysa sonuç tahmindir: ortak ses yok ya da çok az. Kayma, ortak kısmın başı ile sonu arasındaki farktır; 1 kareden azsa tek ofset yeter, düzeltilmez. Sesi kurguya `sound_at = giriş - ofset` ile koy ya da `sync.align_filter` ile hizala. Kısa bir klibi uzun kayıtta ararken `--max-offset` ver.
- **Meme SFX:** Müzik kısa rampalarla kısılır (`Sfx(duck=-6..-12)`). Meme sesi müzikten +3–4 LU yüksek olsun, ortam sesleri (cırcır böceği) ~-23 LUFS'ta kalsın. `analysis.loudness.momentary` ile bak.
- **Ses seviyesi:** Gain, sonra limiter (0.80), sonra ölçüm; 1–2 turda -14 LUFS / < -1.5 dBTP. `loudnorm linear` kullanma: +8 dB gerekince dinamik moda düşüp pompalıyor.
- **Seviye eşitleme:** Kısık müzik yatağı (-37 LUFS) ile yüksek canlı ses (-17 LUFS) arasında gidip gelen kurguda sadece normalize etmek yatağı ~-30'da bırakır. `audio.level.plan(momentary, kesmeler)` her plana kazanç verir (yakın planları birleştirir, vurgulu anı `emphasis` ile +2–3 LU tutar). `keyframes` kazancı kesmede değiştirir: düşerken kesmeden önce, yükselirken sonra. Hemen arkasına `peak_limiter`.
- **Sentez efektler:** `audio/synth.py` (whoosh, impact, pop, tape_rewind). Lisans sorunu yok, rastgele gürültüde `seed` sabit.
- **Konuşma gürültüsü (`audio/denoise.py`, `vlogkit denoise`):** DeepFilterNet, rüzgâr, nefes ve uğultuda afftdn'den çok daha temiz.
  - Kaçkar koşu klibinde gürültü -27'den -70 dB'e indi, ses seviyesi korundu.
  - Müzik eklenmeden önce ham ses izine uygula.
  - `atten_db=18-25` biraz ortam sesi bırakır; tamamen ölü sessizlik vlogda yapay duruyor.
  - EQ, de-esser ve kompresör için ardından aşağıdaki `audio.voice` zincirini kullan.
  - Müzik üstünde müziği gürültü sanar: önce `separate`.
- **Konuşmayı müzikten ayırma (`audio/separate.py`, `vlogkit separate`):** Demucs htdemucs ile `vocals` ve `no_vocals` çıkar. Yarış hoparlörü gibi telifli müziğin üstündeki konuşmayı kurtarıp müziği lisanslı bir parçayla değiştirmek için kullanılır. Ayrım kusursuz değil (davul sızar), kulakla kontrol et.
- **Konuşma temizliği (`audio/voice.py`):** Sadece ham konuşma sesine, müzikle karıştırmadan önce: `voice_for(kaynak, "outdoor-wind").filter()`.
  - Sıra: highpass (rüzgâr, uğultu) → afftdn (hışırtı) → çamur kesme ve netlik EQ → deesser → yumuşak kompresör.
  - afftdn'in kendi gürültü takibi işe yaramıyor (-39 dB hışırtıda 0,7 dB). Bu yüzden gürültü tabanı ölçülüp sabit verilir (`noise_floor_db`, sözler arasındaki sessizlik).
  - Müzik eklenmiş bir videoda ölçüm yapma: ölçülen "taban" müzik olur.
  - Hazır ayarlar: `light`, `phone`, `outdoor-wind`. RNNoise ancak model dosyası verilirse eklenir.
  - Ayarlar sentetik sinyalle yapıldı: gerçek konuşmada kulakla kontrol et.

## 6. Teslim dosyaları

`Edit.sidecars()` → `{".zh.srt": ..., ".chapters.txt": ...}`: compose adımında videonun yanına yazılır. `export.chapters.youtube_chapters` YouTube kurallarını denetler (0:00'dan başla, en az 3 bölüm, her biri en az 10 sn) ve damgaları yukarı yuvarlar: tıklayınca önceki bölümün son karesi görünmez.

### DaVinci Resolve'a aktarma (`vlogkit resolve PROJE [-v VARYANT]`)

Final video aynı kalır; aktarım onun katmanlı bir kopyasıdır.

- **Klasör:** Videonun yanına `<çıktı>_resolve/` yazılır. İçinde bir FCPXML 1.10 zaman çizelgesi (File > Import > Timeline) ve `media/` klasörü var.
- **V1:** Görüntü plan plan bölünmüş. Kesmeler `Edit.cuts()`'tan gelir, proje vermiyorsa scdet ile bulunur.
- **V2 ve üstü:** Her grafik öğesi kendi ProRes 4444 alfa klibi. Overlay ile aynı kodla çizilir; üst üste konunca aynı kare çıkar. Tek istisna: çok parçalı bir öğe (RewindFX, karaoke) başka bir öğenin üstündeyse 8-bit yuvarlamadan en fazla 3/255 fark olur.
- **En üst iz:** Altyazılar kapalı ve görünmez Resolve metni olarak durur. Bir kelimeyi değiştirmek için o metni aç, altındaki resim katmanını kapat. Resolve metninde kontur, gölge ve emoji aynı olmaz.
- **Ses:** A1'de son miks var. `_stems.fcpxml` her sesi (stem) ayrı izde verir: 32-bit float, limiter'sız. Stem'ler `AudioGraph.chain(stem=...)` ile ayrılır; belirtilmezse dosyadan okuyan "main", sentezlenen "sfx" olur.
- **Bölüm işaretleri:** `chapters()` varsa oradan, yoksa ChapterCard'lardan gelir.
- **Yenileme:** Base yeniden derlenirse aktarmayı da yenile; `media/base.mov` bir hard link.
- **Notlar:** Projenin `notes()` notları "Not: ..." işaretçisi olarak gelir.
- **Claude'un Resolve'u doğrudan kullanması (araştırma, denenmedi):** Resolve 21.1 Studio (tek seferlik ücretli) yerleşik bir MCP sunucusuyla Claude Code ve Codex'e açılıyor (File > Setup AI Assistants). Ücretsiz sürümde yok; topluluk sunucusu `davinci-resolve-mcp` (MIT) uygulama içi köprüyle ücretsiz sürümde de çalıştığını söylüyor. İki durumda da başlangıç `vlogkit resolve` aktarımıdır; ince ayar elle ya da MCP ile yapılır, ama asıl kurgu `edit.py`'de kalır.
- **Doğrulanmamış:** FCPXML Apple'ın 1.10 DTD'sine göre geçerli. Resolve'un ücretsiz sürümünde dışarıdan script çalışmadığı için içe aktarma otomatik denenemedi. Metinlerin yazı tipi/konumu, `enabled="0"` ve alfa modu kullanıcıyla doğrulanacak. Kenarlar tuhafsa: Clip Attributes > Alpha Mode: Straight.

### Tarif (`vlogkit recipe PROJE [-v VARYANT]`, `export/recipe.py`)
- **Ne:** Onaylanan kurgunun ölçülebilir hâli: açılış (ilk kesme, ilk yazı, kanca başlığı), plan ritmi (sayı, ortalama, ortanca, en kısa/uzun, üçte birlere göre), yazı ailesi (tür sayıları, dakikadaki yazı, emoji payı) ile grafik/efekt elemanları ayrı, ses katmanları ve seviye, `edit.py`'de kullanılan efektler, NOTES.md'deki amaç/strateji/tercih satırları ve bunlardan "Uygularken" maddeleri. Kuraldan fazla emoji gibi hatalar kopyalanmaz, uyarılır.
- **Nerede:** `recipes/<proje>-<varyant>.md`, repoda (kodla birlikte taşınır). Render gerekmez; planlar zaman çizelgesinden, yoksa videodan gelir.
- **Ne zaman:** Kullanıcı bir kurguyu onaylayınca çıkar. "Şu videodaki gibi yap" denince önce tarifi oku, sayıları yeni malzemeye uyarla.

### Lisans dosyası (`export/licenses.py`, `vlogkit licenses`)
- Her derleme adımı `assets.recording()` içinde çalışır: `ctx.asset(id)` / `assets.path(id)` ile alınan her kütüphane dosyası o adımın kaydına girer (`build/<proje>/<varyant>/assets.json`, adım başına). Yalnız `-s compose` derlense de önceki adımların kaydı durur. Medyayı dosya yolunu elle yazarak değil `ctx.asset(id)` ile al, yoksa kayda girmez.
- `compose` videonun yanına `<video>.lisans.md` yazar (müzik önce; yazar, lisans, sayfa, `checked` tarihi, İngilizce itiraz metni) ve aynı veriyi zaman çizelgesi JSON'una koyar (Stüdyo'nun Lisanslar kartı). Kütüphaneden hiçbir şey kullanılmıyorsa eski not silinir.
- 0.14'ten önceki derlemeler için `vlogkit licenses PROJE -v V`: kayıt yoksa ses ve grafiklerin kullandıkları (`audio()`, `elements()`) yazılır; görüntü adımının eklediği stok klipler ancak yeniden derlemeyle bilinir.

### Stüdyo zaman çizelgesi ve yorumlar (`export/timeline.py`, `vlogkit timeline`)
- **Ne:** Kurgunun veri hâli: planlar (`Edit.cuts()`; yoksa videodan bulunur), yazılar (zaman penceresi olan her eleman), bölümler (`chapters()`), notlar (`notes()`). Her `build` (compose adımı) ve `reel` `build/timelines/<ad>-<anahtar>.json`'a yazar; dosya videonun boyut ve zamanıyla damgalı, video sonradan değişirse "eski" sayılır.
- **Stüdyo:** Çıktı videosunun altında izler: tıklayınca o ana gider, aynı anda görünen yazılar alt satırlara dizilir. "Bu ana yorum" mesaja `[01:23.4 · plan 12/40 · Caption: ...]` ekler. "Kelimeler" videonun konuşmasını kelime kelime gösterir (whisper, önbellekli; ilk sefer biraz sürer); tıkla = oradan oynat, Shift+tıkla = aralık, "Seçileni kes" mesaja `Kes (çıktıda): 00:12.40–00:13.10 «...»` ekler. Değişikliği her zaman ajan `edit.py`'de yapar; arayüz kurguyu doğrudan değiştirmez (tek doğru kaynak kod).
- **Proje dışı video:** Planları video ilk oynatıldığında bulunur (tam kare tarama, `cutcheck.spikes`; aynı anda en fazla 2), sonra önbellekten gelir. Sohbeti açmak tek başına tarama başlatmaz. Tarama sürerken video yeniden derlenirse yeni derlemenin çizelgesi korunur.
- **Yakınlaştırma:** İzler bir pencereyi `[a, b]` gösterir; öğeler pencereye göre yerleşir, dışındakiler çizilmez. Yakınken üstte bütün videonun özet şeridi pencereyi ve oynatma başlığını gösterir. Pencere yalnız oynarken ya da bir aramadan sonra başlığı izler; elle kaydırılan pencere duraklatılmışken yerinde kalır. Plan başına 16 px'ten az düşüyorsa ve video 90 sn'den uzunsa çizelge ilk dakikayla açılır.
- **Ajan için:** `vlogkit timeline PROJE -v VARYANT --at 83.4` o andaki planı, yazıyı, bölümü ve yakın notu tek satırda verir.
- **Notlar:** `Edit.notes()` (edit.py'de `NOTES`): açık sorular, dinlenecek anlar, yapılmamış yorumlar. Zaman çizelgesinde kırmızı işaret, Resolve aktarımında "Not: ..." işaretçisi.
- **İş sürerken mesaj (Claude):** `claude -p --input-format stream-json --replay-user-messages`, stdin açık kalır. Stüdyo yeni mesajı bir `uuid` ile hemen stdin'e yazar; Claude onu bir sonraki araç sınırında alır ve aynı `uuid` ile `isReplay` olarak geri bildirir. Eşleştirme sayımla değil uuid ile: birkaç mesaj tek tura birleşse de her biri ayrı replay alır, başka replay'ler (bildirimler) yok sayılır. Stüdyo kapanırsa yazılmış mesajlar yeniden açılışta düz sıra öğesi olur. Cevaptan sonra 45 sn içinde alınmayan mesaj için girdi kapatılır, mesaj yeni çalıştırmayla gider. Yeni bir klasörden ek içeren mesaj canlı yazılmaz (çalışan sürecin `--add-dir`'i sabit), sıraya girer. Cevaptan önce alınan mesaj çalışan tura katılır ("[İş sürerken eklenen mesaj]"), cevaptan sonra alınan yeni tur açar. Cevap gelince yolda mesaj yoksa stdin kapatılır ve süreç biter. Codex `exec` çalışırken girdi almadığı için orada eski sıra davranışı kalır.
- **Çalışan işte efor:** Claude'un açık stdin'ine `control_request` / `apply_flag_settings` `{"effortLevel": ...}` yazılır; oturumun `applied.effort` değeri hemen değişir (`get_settings` ile doğrulandı) ve bir sonraki model çağrısında geçerli olur. CLI geçersiz bir değeri de "success" diye kabul ediyor: değer Stüdyo'da `EFFORTS` ile denetlenir ve modelin desteklediği en yakın alt seviyeye indirilir (`claude_effort`). Seviyesi olmayan modelde (Haiku) yazılmaz. Hata dönerse sohbete "Ajan ayarı almadı" notu düşer. Codex'te sonraki çalıştırmadan geçerli.
- **Mesajı düzenleme:** Gizli `--resume-session-at` oturumu gerçekten kesmedi (model sonraki turdaki bilgiyi hâlâ biliyordu) ve `--rewind-files` kapalı. Bu yüzden düzenleme özetli yeni oturumdur: geçerli turlar ve ayrılan turlarda değişen dosyalar (`Edit`/`Write` araç adımları; Codex'te `file_change` yolları) ilk mesajda verilir, ayrılan turlar `Job.branches`'ta saklanır. Dosyalar geri alınmaz; ajan gerekirse `git diff` ile bakar.
- **Kurgu ayarı (Stüdyo'daki "Kurgu" çipi):** Kaba kesim sertliği (temkinli / dengeli / sert / belirtme), bitiş (altyazı, müzik, ses efekti) ve ince kesim notu; kaydedilir ve yeni işlere "Kurgu ayarı" satırı olarak eklenir. Seviyelerin `gaps` karşılıkları `CLAUDE.md`'de.

## 6a. Shorts: adaylar, kanca başlığı, altyazı stili, güvenli alan
- **Adaylar (`vlogkit moments VIDEO`, `analysis/moments.py`):** Konuşma paragraflara bölünür (0,9 sn'den uzun sessizlik paragraf sonu, paragraf en fazla 45 sn); paragraf sınırında başlayıp biten her 15-60 sn'lik pencere aday olur (her başlangıç için sığan en uzunu). Her aday için ilk 3 sn'de söylenen, kelime/sn, en yüksek anlık ses (zamanı ve LUFS), ortalama hareket ve 4 kare. Konuşma yoksa planlar birim olur. Puanlamaz: puanı ajan `docs/viral-edit.md`'deki ölçütle verir (Kanca/Akış/Değer, gerekçeli). 4K 4 dk'lık videoda ~2,5 dk (transcript önbellekten gelirse daha kısa).
- **Kanca başlığı (`graphics.captions.HookTitle`):** Vaat ilk saniyelerde üstte, tek stil (ExtraBold, yumuşak koyu kutu, `[vurgu]` sarı); dikeyde y≈300 (üst simgelerin altı). `reel --hook "..."` Reels'e ekler (ilk drop'a ya da 3 sn'ye kadar); plan.json'da `hook` alanı.
- **Altyazı stilleri (`graphics.captions.STYLES`, `vlogkit captions`):** pop (ev stili), kutu (koyu kutu, parlak görüntüde okunur), sade (küçük, zıplamaz), karaoke (kelime zamanı ister; yoksa eşit dağıtılır), büyük (Türkçe büyük harf, `tr_upper`). Galeri, aynı kareye beş stili koyar ve platformun kapattığı bölgeleri kırmızıyla gösterir.
- **Güvenli alan (`style.unsafe_zones`, `captions.safe_notes`, `review` "Yazı"):** Dikey: üst 180 px, alttan %25 (y > 1440), sağ sütun (x > 960, y 1000-1700); YouTube Shorts ile Reels'in sıkı olanı. Yatay: %90 başlık alanı dışı. Yazının dolu pikselleri (gölge hariç) bölgeye %10'dan fazla girerse `!`, biraz girerse `·`.

## 6b. Müziğe göre kurgu: Reels / Shorts (`vlogkit reel`)

Şarkı kesmeleri belirler, en iyi anlar drop'a düşer.

1. **Şarkının yapısı:** `vlogkit beats ŞARKI`.
   - Çıkanlar: BPM, ölçü başları, ölçü başına enerji (`.` düşük, `-` orta, `#` yüksek, `D` drop) ve drop zamanları.
   - aubio vuruşları tempoya göre düzeltilir: kaçan vuruş eklenir, çift vuruş atılır; yoksa ölçüler iki kat uzun çıkıyor.
   - Ölçü başı, basın en güçlü vurduğu vuruştur. Drop, bası önceki iki ölçüden 6 dB fazla olan yüksek ölçüdür.
2. **Montaj:** `vlogkit reel ŞARKI KLİP... [--start S] [--length 20] [--name AD]`.
   - Klipleri kronolojik sırayla ver: montaj hikâyeyi gevşekçe korur (başlangıç → yol → bitiş).
   - `--start` verilmezse başlangıç, ilk drop 2,5 sn'ye gelecek şekilde seçilir; bitiş ölçü sonuna yuvarlanır.
3. **Kesme ritmi (`beatcut.rhythm`):** Her seviyenin en kısa planı var: yüksek 0,55 sn, orta 1,1 sn, düşük 2,2 sn. Adım bunu tutan en küçük vuruş sayısıdır; 150 BPM'de yüksek bölüm 2 vuruşta bir, 90 BPM'de her vuruşta kesilir.
   - Drop'tan önceki ölçü her vuruşta keser (build-up).
   - Yüksek bölümde her 4 ölçülük cümlenin son ölçüsü iki kat hızlıdır (fill).
   - Drop her zaman bir kesmedir.
4. **Anları seçme (`beatcut.plan`):**
   - **Kanca:** İlk plan en güçlü, hareketli anı alır.
   - **Enerji:** Yüksek ölçü hareketli, düşük ölçü sakin (ama donuk olmayan) an ister.
   - **Kalite:** Bulanık ya da patlamış kareler puan kaybeder.
   - **Tekrar yok:** Aynı klip üst üste gelmez, bir an iki kez kullanılmaz.
   - **Gömülü yazı:** Yazılı anlar (Vision OCR) seçilmez; başka seçenek kalmazsa kullanılır.
   - **Vurgular:** Drop'ta punch-in ve flaş, yüksek ölçü başlarında küçük punch, düşük ölçülerde yavaş push.
5. **Plan düzenlenebilir:** `build/reels/<ad>/plan.json` düz veridir. Bir planı değiştir (kaynak, `src_in`, vurgu) ve `vlogkit reel ŞARKI --plan plan.json --name AD` ile yeniden derle.
6. **Teslim:**
   - `<ad>.mp4`: şarkılı; izlemek ve arşiv için.
   - `<ad>_muziksiz.mp4`: yüklemek için.
   - `<ad>.instagram.txt`: şarkının hangi saniyeden başlatılacağı ve drop kesmesinin zamanı.
   - Kesmeler şarkı zamanına göre kareye oturur (`round(t * fps)`); ses tam kare süresi kadardır.
7. **Daha havalı yapmak için** (Claude elle ekler, isteğe bağlı):
   - drop'a girişte `fx.SpeedRamp`;
   - bölüm değişiminde `fx.WhipPan`;
   - son vuruşta `fx.Freeze`;
   - en fazla 2-3 kısa yazı (güvenli alanda);
   - ham ve yazısız kaynak kullanmak.
8. **Şarkı dosyası yoksa (trend şarkı): tempo haritası.**
   - BPM'i songbpm.com'dan (Spotify analizi) al. Bölüm ve söz zamanlarını LRCLIB'in senkron sözlerinden al (`lrclib.net/api/get/<id>`; yalnız zamanlar, sözleri videoya yazma).
   - `music.grid(bpm, enerji, first_downbeat)` ile ızgarayı kur. İlk ölçüyü en güvenilir vuruşa bağla (drop ya da vokalin girdiği satır).
   - Ardışık satırlar ızgaraya oturuyor mu diye bak. Kaçkar'da Timber'ın satırları hep 1 vuruş önceden (pickup), Döndüm'ün nakaratı ~0,7 sn geç giriyordu. Oturmayan yerde bölümü söz satırında başlat (`kackar-reels`'teki `("@", saniye)`).
   - Teslim müziksiz olur. Not, "şu kesme şu vuruşa" diye tek bir hizalama noktası verir. Önizlemedeki ses şarkı değil, rehber ritimdir (`synth.guide_track`).
   - Plan karelerini `Shot(x=..., rotate=..., speed=..., vf=...)` ile ayarla: 4K 16:9'dan dikey kesitte konu ortada kalsın, yan çekilmiş klip çevrilsin, gece planı aydınlansın.

**Müzik ve telif (Instagram, Eylül 2026):**
- Kişisel ve creator hesaplar Reels'te Instagram'ın müzik kütüphanesini kullanabilir. İşletme hesapları yalnız Meta Sound Collection'ı kullanabilir.
- Telifli bir şarkıyı videoya gömüp yüklemek Meta Rights Manager'a takılır: ses kısılır, video kaldırılır ya da hesap kısıtlanır.
- Doğru yol: şarkı sadece *rehber*. Kullanıcı kendi yasal kopyasını (satın alınmış dosya) verir, kurgu ona göre yapılır, müziksiz dosya yüklenir ve aynı şarkı uygulamadan eklenir.
- Şarkıyı YouTube ya da Spotify'dan indirme (kullanım şartları ve telif).
- Telifsiz müzik (CC0, Pixabay, lisanslı) videoya gömülebilir.
- **Reels güvenli alanı:** üstte 250, altta 420, yanlarda 60 px boş kalsın. `VERTICAL` düzen buna uyuyor: altyazı merkezi y=1180, genişlik <= 840, üst yazılar y=330.
- Reels 3 dakikaya kadar olabilir, 1080x1920.

## 7. Doğrulama (teslimden önce)

1. `vlogkit review <çıktı> -p <proje> [--promise "vaat,kelimeleri"]`: izlenme süresi kontrolü.
   - Kontrol edilenler: süre, kanca (açılış karesi, ilk ses <= 0,5 sn, ilk saniyede hareket, ilk söz/yazı, vaat), tempo, bitiş (Short'ta son sözden sonra <= 1 sn; loop isteğe bağlı), loudness, emoji.
   - Tempo için değişimsiz aralık sınırı Short'ta 3 sn, uzun videoda 5 sn. Kesmeler ve pop'lar kare farkından okunur; altyazı gibi küçük grafikler projeden eklenir, çünkü kare farkında görünmezler.
   - `!` maddeleri ya düzelt ya da neden bıraktığını yaz. Rapor `build/review/<ad>.md`.
   - **Kesmeler** (`analysis.cutcheck`): çıktı tam kare hızında tek geçişte taranır (96 px, parlaklık + kare farkı). Bulgular hep çıktının kendisinden gelir: kesme, komşularından belirgin yüksek kare farkı olan karedir (hızlı pan ya da koşu kesme sayılmaz). Kesme sayfaları projenin `Edit.cuts()` listesini, yoksa bulunan kesmeleri gösterir. 4K 4 dk'lık çıktıda tarama ~1,5 dk sürer. Bulunanlar: iki kenarı da güçlü kesme olan 0,2 sn'den kısa artık plan (`!`), ortada 1-6 siyah kare (`!`), daha uzun kararma (`·`), 1 sn'den uzun donuk görüntü (`·`, freeze değilse kaynak kısa kalmış olabilir), kesmede 8 LU'dan büyük ses sıçraması (`·`; 3'ten fazlaysa tek satır, müzikli videoda müziğin kendisi olabilir). Şeritte ve kelimelerde whisper'ın müzikte uydurduğu "Altyazı M.K." gibi kelime dizileri atılır. Kesme sayfaları `<ad>_kesmeler*.jpg`: sayfa başına 12 kesme; her satırda 1,5 sn öncesi (aynı planın içinde), son kare, ilk kare, 1,5 sn sonrası. 36'dan fazla kesmede işaretliler + eşit örnek. `--no-cuts` kapatır.
2. **Eleştirmen turu** (`docs/critic.md`): yeni kurguda ya da büyük revizyonda, kurguyu yapan ajandan ayrı bir bakış. Claude Code'da `vlogkit-critic` alt ajanı (`.claude/agents/`), Codex'te aynı listeyle ayrı tur. En fazla 10 madde, zamanlı ve somut düzeltmeli. Düzelt → gereken adımları derle → review; en fazla 3 tur, kalanlar kullanıcıya "Açık kalanlar" olarak yazılır.
3. `vlogkit check <çıktı> --cuts`: kare sayısı, -14 LUFS, kesme hizası.
4. Kontak sayfasıyla kritik kareler (`analysis.sheets.frames_sheet`), özellikle eklemelerin giriş/çıkış kareleri.
5. **Kulakla dinle.** Rüzgâr temizliğini ve SFX seviyelerini ölçüm tam söylemez.

## Tuzaklar (hepsi yaşandı)

1. **`fps` filtresi concat'ten sonra 1 kare yuttu.** Bütün segment müzikten 1 kare kaydı. Çözüm: `settb + setpts=N` (`video.graph.concat`). Test: `test_concat_keeps_every_frame`.
2. **`0*exp(büyük) = 0*inf = NaN`** → scale filtresi "Error when evaluating the expression" hatasıyla çöktü. Pencereli terimler `if()` ile yazılır (`expr.window`), ölçek ifadeleri `nan_safe`.
3. **Eklenen klip pencereden önce EOF'a ulaşırsa** overlay orijinal kareyi geçirir ve 1 karelik sızıntı olur. Klibi ~0.3 sn uzun oku (`video.inserts`).
4. **Pencere sınırını tam kare zamanına koyma.** Float hatası yüzünden hangi karenin etkilendiği belirsizleşir. `timecode.before_frame` kullan.
5. **`-ss` ile tek kare çekince `t` sıfırlanır.** Zamana bağlı filtreler testte görünmez; tam segmenti işle.
6. **Shell tırnaklaması** filtre zincirlerini bozar. Her zaman Python'dan argüman listesi.
7. **Karaoke'de kelimeleri dikeyde ayrı kırpma:** "az" yukarı kayar (`keep_v`).
8. **Altyazı 840 px'ten genişse** Shorts butonlarının altına girer (`text.fit`).
9. **Miks normalize edilmeden önce +0.6 dBTP'ye çıkıyordu.** Önce limiter.
10. **Karşılaştırma yaparken:** Alfa kanallı formatta (4 düzlem) `psnr` log'unun sütunları kayar; `psnr_avg` alanını adıyla oku. x264 ve ProRes çıktıları deterministik; farklı MD5 = farklı girdi.
11. **Zaman hesabı:** Grafik karesi zamanı `n / Fraction(30000,1001)` ile tam hesaplanır. Float bölmeyle 1 ULP fark, pop/fade anında 1 px'lik yuvarlama farkı yaratabiliyor.
12. **Headless `claude -p` ve izinler:** Klasöre Claude Code'da hiç "güven" onayı verilmediyse projenin `.claude/settings.json` dosyasındaki izinler yok sayılır ve komutlar "This command requires approval" ile reddedilir. `-p` modunda bu onay ekranı gösterilemiyor. Çözüm: izin dosyasını `--settings` ile açıkça ver (`vlogkit ui` bunu yapıyor).
13. **Siyah bantlar parlaklığı yanıltır.** 464x832 kanvasta 464x262 görüntü: ortalama luma bantlarla ~45 çıktı, her plan "loş" göründü; gerçek değer ~110. Aktif alanda ölç (`luma_curve(crop=...)`; `analyze` artık otomatik). Kırparken bant kenarındaki 2 px karışık satırı da at (`Box.inset`).
14. **Değişken kare hızı.** Kaynak `r_frame_rate` 60 diyor ama ortalama 32 fps (60 fps parçalar + 30 fps kurgu). `frames_sheet` gibi kare numarasıyla çalışan araçlar yanlış kareyi gösterir. Zincirin başına `reframe.cfr(fps)`; çıktının kesmeleri `round(kesme*30)` karesine düşer.
15. **ffmpeg ifade sınırı.** ~100 terimden uzun düz toplamlar ayrıştırılamıyor, `eq` bunu "Cannot allocate memory" diye raporluyor. Anahtar noktalı eğriler için `expr.piecewise` (dengeli `if` ağacı, derinlik log₂n). Test: `test_piecewise_is_a_shallow_tree`, `test_unletterbox_to_landscape_with_big_piecewise_grade`.
16. **Müzik altında whisper.** `auto` dil tespiti İngilizce şarkıyı Çince sandı; tam dosyada her 30 sn'lik pencere aynı satırı (`中文字幕:YK`, `优优独播剧场`) tekrarladı. Çözüm: 5–8 sn'lik pencereler, `--no-context --beam 5`, farklı dil ve ön işlemlerle tekrarla; üç ayarda da aynı çıkan satırı al (ör. "拜拜武汉"), gerisini koyma. Şarkı sözlerini altyazı yapma.
17. **Yükseltilmiş yataktaki tıkırtılar.** Seviye eşitlemede +16 dB alan bölümdeki çarpma sesleri miksi +6 dBTP'ye çıkardı; son limiter onları 60 ms boyunca 10–18 dB bastırıp müzikte delik açtı. Kazancın hemen arkasına hızlı bırakan `level.peak_limiter`.
18. **Düşük çözünürlüğü büyütmek görüntüyü bozar.** Uzun bir videoda: 464x832 kanvastaki 464x262 görüntü siyah bantları kırpılıp 1920x1080'e (4,1 kat) büyütüldü; kullanıcıya kaynaktan daha kötü göründü. Oran ya da çözünürlük değişikliği plan maddesidir: aktif görüntü < 720p ise önce sor. Seçenekler: kaynağı olduğu gibi bırak, 2 kattan fazla büyütme, keskinleştirme (CAS) kullanma.
19. **Altyazı pop'u kare farkında görünmez.** Kaçkar Short 01'de altyazının belirdiği karelerde scdet skoru 0,5 kaldı; el titremesi 1-3. Tempo analizi bu yüzden projedeki grafiklerin başlangıç zamanlarını ayrıca sayar (`pacing.overlay_starts`). Geri sarma gibi hızlı bölümlerde kesmeler "son 1 sn'nin ortalamasına göre" değil, mutlak eşikle (8) aranır; aksi halde hepsi kaybolur.
20. **Whisper dolgu kelimeleri yazmaz.** "ııı, eee" transkriptte yok; kelimeler arasında boşluk olarak kalırlar. Dolgu aramak için kelime aralıklarına bak, metne güvenme. Koşu gibi konuşmasız aksiyon da "boşluk" görünür: 2,5 sn üstü `quiet` ve isteğe bağlı.
21. **10-bit ara dosyada 8-bit filtreler efekt penceresi dışını da bozar.** `noise`, `eq`, `curves`, `vignette`, `drawbox`, `rgbashift` her kareyi dönüştürür. Pencereli efektlerde yalnızca `geq`, `lutyuv`, `hue`, `scroll`, `dblur` (test: framemd5 pencere dışında aynı).
22. **Ses görüntüden 6 ms kısa olunca mp4 son kareyi kaybetti.** Reel: 180 kare (6,006 sn) ama şarkı 6,000 sn kesilmişti → 179 kare. Sesi tam kare süresi kadar yap: `nframes / fps` (`beatcut.music_graph`). Birkaç örnek kısa kalması da yetiyor: `kackar-run-p3`'te 1719 kare = 2753150,4 örnek, ses 2753150'de kesilince 8 µs kısa kaldı ve son kare yine düştü. `AudioGraph` artık süreyi tam örneğe yukarı yuvarlıyor (`samples`); `check` kare sayısını her teslimde kontrol et.
23. **Kurgulu kaynakta gömülü yazılar.** Kaçkar kliplerinde "KM 25", "BAŞLIYORUZ!" gibi yazılar vardı; montajda bağlamsız kaldı. Vision OCR (`analysis/ocr.py`) iki işaretle yazıyı bulur: büyük yazı (kare yüksekliğinin >= %3'ü) ya da komşu örnekte aynı yerde duran aynı yazı. El kamerası oynarken sabit kalan yazı altyazıdır; manzaradaki yazı görüntüyle kayar. OCR bazı örnekleri kaçırdığı için işaret bir örnek öne ve arkaya genişletilir. Sadece "yazı var mı" diye bakmak manzarayı da (TURKCELL, KACKAR takı) atıyordu.
24. **Python'da `"İ".lower()` = "i" + birleşik nokta.** "İzlediğiniz için teşekkür ederim" halüsinasyon listesiyle eşleşmiyordu. Metin hem Türkçe (İ→i, I→ı) hem İngilizce kuralla küçültülüp kontrol ediliyor.
25. **vid.stab kurgulu klibe uygulanınca gömülü yazı sallanır** ve selfie'de yüz kayar. Sadece ham, yazısız plana, plan plan uygula.
26. **Taneli planda yavaş çekim titriyor.** Apple ara kareleri gerçek karelerden daha az taneli; 0.5x'te tane saniyede 15 kez gelip gidiyor. Önce ara kare, sonra zamansal gürültü filtresi: `vt.interpolate(..., denoise=1.0)`. Filtreyi önce uygulamak (0.6) farkı kapatmadı.
27. **Büyük yazıda gölge kutusu.** `render_line`'ın sabit 60 px boşluğu 400 px'lik kapak yazısının gölge bulanıklığını kesiyordu: yazının etrafında soluk, sert kenarlı bir dikdörtgen. Boşluk artık `size * 0.5`. Kapakta hizalama gölgeye değil harfe göre (`thumbnail.text_block`), yoksa yazı çapasından içeri kayıp küçülüyor.
28. **Aynı klibin art arda iki parçası kesme sayılmaz.** Kaçkar Reels'te göl manzarası (0054 @0) ve hemen ardından aynı çevrinin 1,6. saniyesi review'da "3,3 sn değişimsiz" çıktı; göze de tek plan gibi geliyor. Aynı klipten iki anın arasına başka bir klip koy ya da ikinci anı ilkinin bittiği yerden uzaklaştır.
29. **Kamera saati ile hatırlanan saat çelişebilir.** Bir yarış videosunda konuşmada start saati yarım saat erken söyleniyordu; kamera saatine göre start ve finiş arasındaki fark ise resmi süreyi tutuyordu. Duvar saati yerine doğrulanmış süreyi (0:00'dan başlayan) göster ya da kullanıcıya sor.
30. **Seyrek bakış anlamsız an seçtirdi.** 28-09 vlogunda "evden çıkış" yerine kameraya eğilip aldığın 1-2 sn kullanıldı: hareketli ve yüzlü olduğu için "iyi an" gibi görünüyordu. Çözüm: kurgudan önce `vlogkit log` (tam kapsama + `kurulum` bayrağı + Claude'un parça notları), sonra review plan sayfası.
31. **Mesaj "-" ile başlayınca `claude -p` onu seçenek sandı** ("error: unknown option '- 7 için ...'"). Mesaj artık stdin'den gidiyor; uzun mesajlarda argüman sınırı da kalmadı.

32. **Aynı cümlenin çok denemesi whisper'ı döngüye soktu.** Konuşma çekiminde tüm klibe `transcribe` her pencereye "Pardon, başa alıyorum" ya da "Altyazı M.K." yazdı. Çözüm: klip başına eşikle (en sessiz %20 + 11 dB) konuşma bandı zarfından adalar çıkar (0,9 sn'den kısa boşlukları köprüle), her adayı tek başına `--words --beam 5 --no-context` ile çöz. `silencedetect` gürültü tabanı farklı kliplerde adaları birleştirdi. İlk kelimenin başlangıcı güvenilmez; kesmeden önce zarfla doğrula.
33. **Siyah perdede kişi maskesi tüm kareyi kapladı.** `segment.mask(person=True)` koyu perdeyi de kişi saydı (kutu tam kare). Yüz/baş konumu ölçerken `largest=True` ön plan maskesi kullan.
34. **Konuşma çekiminde renk, arka plan değiştikten sonra.** Loş, düz çekimi açan `gamma` sıcak `studio` zeminini de açar ve doyurur (turuncuya kaçar). Siyah zeminde sorun yok; renkli zeminde rengi koyu seç (`studio:#2a1c12` gibi) ve sonucu karede kontrol et.

35. **Uzun render sırasında Mac uykuya geçti.** Arka planda sıralı derlenen üç 4K varyantın sonuncusunda görüntü adımı normalde ~5 dk sürerken 1 saatte %20 ilerledi ve iş zaman sınırına takılıp kesildi. Uzun build'leri `caffeinate -i` ile çalıştır. Her 4K varyantın `base.mov`'u ~20-25 GB: `vlogkit disk` eski varyantların ara dosyalarını siler (yeniden derlemede `Edit.plan_steps` eksik adımı ekler).

36. **Ses dosyası -1,1 dBTP, mp4 -0,6 dBTP.** Örnek tepesini tutan limiter, örnekler arasındaki tepeyi (true peak) kaçırıyor; AAC kodlaması da ~0,3-0,5 dB ekliyor. `normalize` limiter'ı 4 kat örnekleme hızında çalıştırıyor ve wav'ı -1,5 dBTP'nin altında tutuyor. Teslimden sonra `check` ile mp4'ü ölç, wav'ın değerine güvenme.

37. **DJI ham klibinin döndürme etiketi yanlış.** Rize ham kliplerinin bazılarında (0025: -180, 0039: -90) etiket var ama pikseller zaten düz; ffmpeg etiketi uygulayınca görüntü ters ya da yan çıktı. `vlogkit log` sayfaları etiketi yok saydığı için düz görünüyordu. Ham klibi okurken önce bir kareyi `-noautorotate` ile ve onsuz karşılaştır; düz olanı kullan.

38. **ffmpeg crop, kare boyutu sonradan değişirse ilk boyutu kullanır.** `scale=...:eval=frame` ile büyüyen karelerde crop `iw`'yi ve x/y sınırını kurulumdaki boyuttan alıyordu; zoom 1'de başlayan her itme sol üst köşeye yapışıyordu. `zoom_crop` ölçeği zirve zoom'da kurup konumu o anki ölçek formülüyle hesaplıyor (test: `test_zoom_crop_stays_on_its_focus_when_the_zoom_changes`). Kendi crop ifadeni yazarsan `iw`'ye güvenme.
39. **Ayrı kaydedilmiş ses (telefon) ile görüntüyü eşlemek.** Elle yapma: `vlogkit sync KAMERA TELEFON` zarfları kaba-ince çapraz korele eder, ofseti ~1 ms, güveni ve kaymayı verir (Rize konuşması: elle 3,345 sn, araç 3,346 sn). Whisper'ın ilk kelime zamanına güvenme; güven düşükse `strip` ile kontrol et.
40. **CIELAB'da mavi gökyüzü mora kayar.** Doygunluğu CIELAB'da 0,71 kat azaltınca DJI gökyüzü ~4 derece mora döndü. Renk eşleme bu yüzden Oklab'da çalışır.
41. **ffmpeg `fps` filtresi kareyi geç verdi.** Varsayılan yuvarlamada saniyede 8 alınan örnek, o andaki kare yerine ~0,05 sn sonraki kareydi; hızlı pan'da bulanıklık yüzün arkasında kaldı. Zamanı önemli örneklemede `fps=R:round=up:start_time=0` kullan (`redact.sample_filter`, test: `test_samples_are_the_frames_on_screen`).

42. **Disk derleme ortasında doldu.** Bir haftada `build/` 120 GB'a çıktı (4K uzun vlogun parçaları 59 GB, Rize'nin iki varyantı birer 27 GB base.mov). Artık `Edit.run` başlamadan yazacağı yeri tahmin eder (ProRes 422 HQ: 1080p29,97'de ~220 Mb/s, piksel ve kare hızıyla orantılı; base'in 1,3 katı + overlay + ses) ve 5 GB pay kalmayacaksa başlamaz, 30 GB'ın altına inecekse uyarır. `vlogkit disk` / Stüdyo "Ara dosyalar" N gündür derlenmeyen varyantların mov/wav'larını siler; mp4, görsel, json ve araç klasörleri (`log`, `analysis`, `cache`, `timelines`, `ui`) kalır. Yalnız `edit.py`'si olan projelerin klasörlerine bakılır. Başka bir projenin kodunda `BUILD_DIR / "proje" / "varyant"` ya da `build/proje/varyant` olarak geçen klasör hiç silinmez (`rize25-shorts` ve `rize25-anlatim`, `rize25-vlog01/2`'deki gürültüsü alınmış sesi ve büyütülmüş planı okuyor; onları yalnız o proje yeniden üretir). Derleme yeri tahmininden üzerine yazacağı dosyaları düşer: 27 GB'lık base.mov'u yeniden derlemek az yer ister. Varyantlar arasında hardlink'li dosyalar (Rize'de `manzara_x2.mov` 9 bağ) tek sayılır; dışarıdan (Resolve klasörü) bağlı olan silinmez, çünkü yer açmaz. Temizlik iş çalışırken yapılmaz: ajan o varyanttan derliyor olabilir.

43. **Pixabay sayfaları komut satırına kapalı (Cloudflare, 403).** `curl` ve WebFetch sayfadaki indirme bağlantısını ve "Content ID Registered" rozetini göremiyor. Bilgisayardaki Chrome ile Playwright (`channel="chrome"`, `navigator.webdriver` gizli) sayfayı açabiliyor; `cdn.pixabay.com/download/audio/...` bağlantısı ve rozet oradan okunur, dosyanın kendisi `curl` ile iner. Rozeti olan parçayı alma (bu oturumda adayların yarısından fazlasında vardı).

44. **Satır satır müzik kısması, art arda kesilmiş konuşmada müziği zıplatır.** Her satıra "önce aç, sonra kıs" anahtarı koyunca iki satırın birleştiği her kesmede müzik ~0,3 sn tam sese çıktı ve anlatımı böldü (kullanıcı: "şarkı anlatımımı çok bölmüş"). Konuşma aralıklarını birleştirip tek kısma tut: `audio.level.duck_keys(..., bridge=)`. Müziği yalnız gerçekten konuşmasız anlarda (manzara açılışı, fotoğraf) aç.

45. **Güncellemeden sonra `uv.lock` "elle değişmiş" sayıldı.** Kurulu kopyada `uv sync` ve `uv run` kilit dosyasını yeniden yazınca bir sonraki güncelleme onu `git stash`'e aldı. Kurulu kopyada uv hep `--frozen` çalışır (`install.sh`, `update.apply`, masaüstü kısayolu): yayının kilidi olduğu gibi kalır.

### 10-bit luma tuzağı

`signalstats` YAVG değerini filtreye gelen bit derinliğinde verir: 10-bit bir klipte 180, 8-bit referansta yaklaşık 45 eder. `luma_curve` artık `format=yuv444p` ile ölçüm akışını 8-bit yapar; tüm eşikler 0–255 referansındadır. Eski 10-bit analiz raporlarının loş sahne listeleri yeniden ölçülmelidir. Bu dönüşüm medyayı veya pozlamayı değiştirmez; HDR transfer fonksiyonunu SDR ile eşitlemez. Aktif alan kırpması dönüşümden önce uygulanır.
