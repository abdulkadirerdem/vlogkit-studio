# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/). Sürümleme: [SemVer](https://semver.org/).

## [0.21.0] - 2026-11-07

### Eklendi
- **3B formatları (`scene3d/formats.py`, `docs/formats/`):** her video bir format seçer (`"format"`); format kanıtlanmış bir kısa video kalıbıdır (hikâye yapısı, ekran dili, altyazı biçimi, tempo, kontrol listesi). `3d new --format <id>` projeyi formatın çalışılmış örneğiyle açar. Senaryolar sayfası formata göre araştırır, kartta formatı gösterir. İlk iki format:
  - **Peki ya?** (`pekiya`): 7 adımlık kalıp (soğuk açılış, kurallar, tırmanan sonuçlar, gerçek sayı, dönüş, insani an, çözülmemiş kapanış).
  - **Kesitten inşa** (`kesit`): pasta gibi kesilmiş bir bahçede gündelik bir şey adım adım inşa edilir: "Eğer… Ama… O yüzden… Buna ___ denir." Tek kelime altyazı; sahne beat'ten beat'e birikir (`carry`: her beat yalnız eklediğini yazar, `remove` çıkarır). Çalışılmış örnek: "Bahçendeki çukur nasıl kuyu olur?"
- **Kesit kiti:** `cutaway` mekânı (çimli, toprak katmanlı, çatlak dokulu kesit bloğu; iki katlı ev, çit, ağaçlar; yaz, sonbahar, kış), `pit` (bowl, box, shelf, trench, tunnel; yüzeyin altında bant için `top`), `layer` (su, bulanık su, kum, çakıl, taş, beton, asfalt, membran, buz…; tabandan yükselerek dolar), `pipe`, `tank`, `hand_pump`, `fish`, `lily_pad`. Diorama ölçeğinde kamera (mekân kendi ölçeğini söyler).
- **Gerçek kelime zamanları:** seslendirme whisper ile dinlenip her kelimenin zamanı ölçülür; olaylar, kesmeler ve altyazı tahmine değil sese oturur (sayılarda fark yarım saniyeye kadar çıkıyordu). Whisper yoksa eski hece tahmini.
- **`3d kontak`:** render'dan önce her planın ortasından bir kare tek sayfada: plan no, zaman, söylenen kelimeler, telefon arayüzünün kapattığı alanlar.
- **`3d kontrol`:** bitmiş videonun makine kontrolü: seslendirme senaryoyla eşleşiyor mu (whisper), ölü an, 3 sn'den uzun plan, kısa kalan altyazı, ses seviyesi.
- **`3d puanla`:** kör puan: yeni bir Claude oturumu yalnız izleyicinin gördüğünü görür, 7 satırda 70 üzerinden puanlar, en zayıf yeri ve 3 düzeltme yazar.

## [0.20.0] - 2026-11-04

### Eklendi
- **Kaydırılan ekran kaydından yavaş kamera hareketi (`video/pagescroll.py`):** Birinin bir sayfayı (profil, sohbet, belge) kaydırdığı ekran kaydı sayfanın tamamını taşır ama kendi kaydırması sarsıntılıdır — 4 sn'lik savurmadan 13 sn'lik yavaş bir iniş kesilemiyordu. `stitch` kareleri satır parlaklığı imzasıyla eşleyip tek bir uzun sayfa görüntüsüne yapıştırıyor (`Column` ile yalnız kayan içerik sütunu; tarayıcı çubuğu, yapışkan başlık ve yan sütun dışarıda). Eşleme tek bir "en iyi" kaydırmaya güvenmiyor: savurmanın en hızlı yerinde yalnız birkaç yüz satır örtüşüyor ve çoğu boş kart zemini olduğu için birden çok kaydırma neredeyse aynı puanı alıyor (bu kayıtta 262, 294, 342, 433 arasında 0,5 fark vardı); adaylar sayfanın şimdiye kadar birleşmiş uzun bağlamına göre puanlanıp seçiliyor (`_shifts` + `_place`). Tek eşlemeyle sayfanın iki bölümü (Hakkında, Faaliyet) eziliyor ve bir satır ortadan kesiliyordu. `move` o sayfanın üzerinde `Key(t, cx, cy, w)` anahtar kareleriyle pencere gezdiriyor: alt piksel hassasiyetinde (ffmpeg `zoompan` tam sayıya yuvarlayıp basamak yapıyor), genişlik geometrik aradeğerli, `ease` ile hızlanan/yavaşlayan iniş, aynı değerli iki anahtarla bekleme, kısa genişlik düşüşüyle vurgu darbesi. Grade/vinyet/fade aynı encode'da (`filters`), kareler bir kez örnekleniyor. Yüksek DPI kaydında yazı 7-8 kat büyütmeye dayanıyor.
- **Sessiz teslim (`AudioGraph.silent`):** Şarkısı uygulamadan (Reels / TikTok kütüphanesi) eklenecek videolar için sessiz ses yatağı; mp4 yine bir ses kanalı taşıyor.

### Düzeltildi
- **`vlogkit analyze` müziksiz kayıtlarda tamamen çöküyordu:** aubio bazı dosyalarda (sessiz ekran kaydı) segfault veriyor. `beats`/`tempo` artık `BeatsUnavailable` fırlatıyor, `analyze` vuruş listesini atlayıp raporu yazıyor ("Vuruşlar: okunamadı" + nedeni), `vlogkit beats` tracebook yerine tek satır hata basıyor.
- **Sessiz mikste sonsuz kazanç:** `loudness.normalize` -inf LUFS'tan -14 LUFS'a giderken kazancı hesaplayamıyordu; -70 LUFS altındaki miks artık olduğu gibi yazılıyor.

## [0.19.1] - 2026-11-03

### Eklendi
- **Süresi değişen plan yeniden render edilmiyor:** anlatım yavaşlayınca ya da bir cümle yeniden yazılınca bütün video baştan render ediliyordu. Her plan artık uzunluktan bağımsız bir "şekil" de taşıyor: kelimeye bağlı zamanlar planın süresine oranlanır (`plan._stretched`), efektlerin mutlak süresi (`dur`) olduğu gibi kalır, karşılaştırma %3 toleranslıdır (`plan.same_shape`) — kare sayıları tam sayı olduğu için aynı plan başka tempoda birebir aynı sayıları vermez. İçerik aynı, yalnız süre değiştiyse diskteki kareler yeni uzunluğa göre örneklenir (`plan.mark_reuse`, `plan.source_frame`) ve Blender hiç çalışmaz. Sınır ±%33. Günlükte `önbellekten uzatıldı (90 → 99 kare)` diye görünür; örnek: tempo 0,9'a inince 30 planın 12'si karelerini korudu (1579 kare yerine 865 render).
- **Anlatım hızı (`scene.json` → `voice.speed`, 0,5-2,0):** kanal sesinin hızı referans kayıttan geliyordu ve `speed` alanı yok sayılıyordu; artık seslendirilen satır perdesi bozulmadan yavaşlatılıyor ya da hızlandırılıyor (`tts.retime`, ffmpeg atempo). Daha sakin ve ağır bir anlatım için `"voice": {"speed": 0.9}`.

## [0.19.0] - 2026-11-02

### Eklendi
- **3B: anlatılan her şey ekranda olur.** Bir cümle artık birden çok plan (`shots`): her plan bir kelime söylendiği anda başlar (`cue`), kamerayı, mekânı, oyuncuları, eşyaları, efektleri ya da görünümü değiştirir; değiştirmediği şey beat'ten gelir ve zaman akmaya devam eder (aynı hareket, yeni açı). Hareketler, efektler, eşya hareketleri, sayaç ve ses efektleri de bir kelimeye bağlanır (`"from": "zıplasaydı"`, `"at": "patladı"`). `3d plan` her planı ve 3 saniyeden uzun olanları gösterir; iç kesmelerde yumuşak whoosh.
- **Efektler (`bpy_kit/fx.py`, `fx`):** çatlak (zemin/duvar, büyüyerek), parçalar, cam kırılması, patlama (ateş topu, ışık, duman, parça, sarsıntı), duman, ateş, kıvılcım, su baskını, akan sıvı ve birikinti, yağmur (para, konfeti, su, kar), flaş, kamera sarsıntısı, ışın, bir eşyayı ikiye bölme (Ay, Dünya, bina), belirme ve kaybolma. Hepsi anahtar karelerle kurulur: önizleme karesi tam render'la aynıdır.
- **Etkileşim:** eşyalar hareket eder (`anim`: taşınır, döner, düşer, büyür, belirir, kaybolur), elde tutulur ve elden ele geçer (`hand`), kapılar menteşesinden açılır (`open`); oyuncular birbirine ya da bir eşyaya döner (`"facing": "veli"`); kamera bir eşyayı boyuna göre ya da birkaç kişiyi birlikte kadrajlar. Yeni hareketler: fly (3B yol boyunca uçar), give, dodge.
- **Kalabalık (`bpy_kit/crowd.py`, `crowd`):** 6 farklı kişi kurulur, gerisi ucuz kopya; panik, sevinç, zıplama, yürüme, koşma, dans; uzak planlar için basit kalabalık.
- **Görünümler (`scene3d/looks.py`, `look`):** güvenlik kamerası (siyah-beyaz, kumlu, REC, saat), canlı haber (SON DAKİKA bandı, manşet, kayan yazı, CANLI), telefonda viral video (beğeni sayacı tırmanır), eski film, gece görüşü. Render'dan sonra çizilir; görünüm değişince yeniden render gerekmez.
- **Yeni eşyalar:** haber yayını açık televizyon, ARANIYOR afişi, duvar haritası, dev telefon ekranı.
- **Paylaşım paketi (`publish.py`, `docs/yayin.md`):** bitmiş dikey video için YouTube Shorts, Instagram Reels ve TikTok'a ayrı başlık, açıklama, etiketler ve 1080x1920 kapak; Claude yazar, kişi paylaşır (platform API'si ve uygulama onayı yok). Paket videonun yanında `<video>.yayin.json`, kapaklar `<video>.kapak-<platform>.jpg`. Video bir senaryodan üretildiyse senaryonun başlık ve etiketleriyle başlar. Komutlar: `vlogkit yayin MP4 [--taslak]`, `yayin-kapak` (3B videoda kare verilmezse sayacın en büyük olduğu an; kapak altyazısız resimden), `yayin-kontrol` (platform sınırları: başlık 100, Instagram 5 etiket, açıklama uzunlukları; erişim uyarıları).
- **Stüdyo: Paylaş düğmeleri:** sohbetteki her videonun altında YouTube, Instagram, TikTok. Açılan pencerede kapak, her metin için Kopyala, "Videoyu göster" (yükleme sayfasına sürüklemek için), platformun yükleme sayfası, "Paylaşıldı" işareti; paket yoksa "Paketi hazırla" Claude'a yazdırır.
- **Elde tutma:** telefon avuçta durur, ekranı tutanın yüzüne döner (ekranında bir uygulama), elden ele geçerken iki el arasında yol alır.
- **Ay:** NASA CGI Moon Kit dokusu ve yükseklik haritası (LRO, telifsiz; `assets/moon`). İkiye bölünmede yarımlar kesik yüzlerini kameraya çevirir, aradaki erimiş çekirdek parlar; uzayda parçalar düşmez, süzülür.
- **Kanal sesi vurgusu:** referans sesin yazılı metni yanında durursa (`assets/voice/kanal.txt`) ses, referansın tınısıyla birlikte enerjisini ve vurgusunu da kopyalar.

### Değişti
- **Kanal sesi daha tutkulu:** yeni referans kayıt (Chatterbox, daha yüksek vurgu) ve yazılı metni; Qwen3 artık referansın enerjisini ve vurgusunu da kopyalıyor. Üç örnek arasından kulakla seçildi; perde oynaklığı eskisinden ~%30 fazla. Eski seslendirmeler önbellekte kalmaz, yeniden üretilir.

### Düzeltildi
- 3B jestler (şok, işaret, sevinç...) yazıldığı andan önce de görünüyordu; artık kendi zaman penceresinde, yumuşak geçişle oynar. Bir hareketten önceki bekleme süresi bekleme animasyonundan kısa olunca render "Unable to add strip" hatasıyla duruyordu; artık karakter o süre boyunca bekler.

## [0.18.4] - 2026-11-02

### Eklendi
- **Asansör mekânı (`3d kit` → `elevator`):** çelik kabin, kapı kanatları, kat levhası (`set_opts.floor`), düğme paneli, tutamak ve tavan lambası. `set_opts`: `open` (kapılar açık), `ceiling: false` (tepeden çekim), `shaft` (kabinin üstündeki kuyu: beton, kılavuz rayları, sekiz taşıyıcı halat; tavanı kaldırır), `emergency` (kırmızı acil ışık), `floor_color`. Asansör, düşme ve kapalı kalma senaryoları artık stüdyo fonunda taklit edilmiyor.
- **`vlogkit 3d senaryo-kontrol --tum`:** klasördeki bütün senaryoları tek komutta doğrular (arşiv dahil), her satırda kimliğiyle; bir tanesi bile bozuksa komut hata döner.

### Düzeltildi
- **Prompt rehberinde maddeli "Claude ne yapar" blokları sayfaya hiç çıkmıyordu** (`prompts.py`): satır sonunda metin yoksa altındaki maddeler artık toplanıyor (`Prompt.does_items`) ve kartta liste olarak çiziliyor. S3, B1, B2 ve benzeri kartların açıklamaları geri geldi.

## [0.18.3] - 2026-11-02

### Eklendi
- **Senaryolar sayfası (Stüdyo, `scene3d/scenarios.py`, `docs/senaryo.md`):** Claude viral olabilecek 3B "Peki ya?" fikirlerini web'de araştırır, beş ölçütle puanlar (merak, tırmanış, görsellik, sayılar, yorum), ortalaması 7,5'in altındakileri eler, kalanları sahne sahne yazar (her cümlenin ekranda olacak olayı, sayaç, efekt, kapanış sorusu, sonraki video ipucu, platform başlıkları ve etiketler, kaynaklar). Senaryolar `projects/_senaryolar/` altında JSON; sayfada puanıyla listelenir, ayrıntısı tablo olarak açılır. "Bu senaryoyu çek" seçili senaryoyu 3B işine verir; durum (yeni, seçildi, üretiliyor, üretildi, arşiv) sayfada görünür. Yeni iş türü "Senaryo araştır"; komutlar `3d senaryolar`, `3d senaryo-kontrol`, `3d senaryo-durum`. Prompt rehberinde "3B animasyon" bölümü (B1, B2).

### Düzeltildi
- Windows testinin uçtan uca videosu kanal sesiyle seslendiriliyor (eski Pocket sesini istiyordu).

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

