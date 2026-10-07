# vlogkit: ajanlar için çalışma kuralları (Claude Code ve Codex)

Bu repo, kullanıcının vlog kurgu araç seti (ffmpeg + Pillow, Python 3.12+, uv). Oturumlar ya terminalden ya da `vlogkit ui` arayüzünden başlar (headless `claude -p`, ya da Codex seçildiyse `codex exec`; Codex bu dosyayı da okur). Kullanıcıya **Türkçe** yaz.

## Kurulu kopya mı, geliştirici kopyası mı
Repo kökünde `.release` dosyası varsa bu bir **kullanıcı kurulumu**dur (`install.sh` ile kurulmuş, güncellemeler Stüdyo'dan gelir):
- vlogkit'in kendi dosyalarını değiştirme: `src/`, `tools/`, `docs/`, `scripts/`, `CLAUDE.md`, `assets/manifest.toml`. Güncelleme onları yeniden yazar. Commit atma, push etme.
- İşini `projects/<proje>/` altında yap (bu klasörler kullanıcınındır, güncelleme dokunmaz). Yeni lisanslı medyayı `assets/manifest.local.toml`'a aynı biçimde yaz; özel adları `assets/vocab.txt`'ye.
- vlogkit'te eksik bir şey görürsen yalnız "Öneri:" satırı yaz; kullanıcı onu geliştiriciye iletir. Aşağıdaki "vlogkit'i geliştirince" ve "Git" kuralları kullanıcı kurulumunda geçerli değil.

`.release` yoksa burası geliştirici kopyasıdır; kuralların hepsi geçerli.

## Yerleşim
- **Ham görüntüler:** `~/yt-vlogs/<vlog>/`. Repo **dışında**, ama erişim var (`--add-dir ~/yt-vlogs`).
- **Kütüphane:** `src/vlogkit/`.
- **Her video bir proje:** `projects/<vlog>-<parça>/edit.py`. Şablon için `projects/_template`; geliştirici kopyasında tam örnek `projects/kackar-short01`.
- **Ara dosyalar:** `build/<proje>/<varyant>/` (git'te yok, silinebilir).
- **Final çıktı:** Ham görüntünün yanına yazılır, ör. `~/yt-vlogs/kackar/<ad>_EDIT[_varyant].mp4`.
- **Lisanslı medya:** `assets/manifest.toml`. İndirmek için `uv run vlogkit assets fetch`.
- **Mutlaka oku:** `docs/workflow.md` (süreç + tuzaklar), `docs/shorts.md` (güvenli alanlar, ses, telif), `docs/viral-edit.md` (izlenme süresi kontrol listesi), `docs/prompts.md` (kullanıcının prompt kalıpları).

## Komutlar (hep `uv run` ile)
`vlogkit doctor` · `log KLASÖR [--vlm]` · `find KLASÖR kelimeler...` · `ask VIDEO --start --end "soru" [--face]` · `face VIDEO --start --end` · `analyze VIDEO` · `sheet VIDEO --start --duration --fps` · `frame VIDEO -t SN` · `strip VIDEO --start --end [-m SN]` · `transcribe VIDEO [--words] [--no-vocab]` · `gaps VIDEO` · `moments VIDEO [--min --max]` · `captions [--video V -t SN]` · `thumbs VIDEO --text` · `new PROJE` · `build PROJE [-v VARYANT] [-s base|overlay|audio|compose]` · `preview PROJE -t SN` · `review [VIDEO] -p PROJE --promise [--no-cuts]` · `check VIDEO --cuts` · `resolve PROJE [-v VARYANT]` · `timeline PROJE|VIDEO [-v VARYANT] [--at SN]` · `recipe PROJE [-v VARYANT]` · `beats ŞARKI` · `reel ŞARKI KLİP... [--start --length --plan --hook]` · `upscale VIDEO --target` · `slowmo VIDEO` · `stabilize VIDEO --preset` · `match-color VIDEO --ref REF [--ref-at SN] [--at SN]` · `background VIDEO --bg SPEC` · `redact VIDEO --faces|--box x,y,en,boy@SN [--mode spotlight]` · `denoise VIDEO` · `separate VIDEO` · `sync KAMERA TELEFON...` · `extras list|install` · `assets list|fetch`

## Orkestrasyon: hangi iş, hangi araçlar, hangi sırayla
Oturumun başında `uv run vlogkit doctor` ile neyin kurulu olduğuna bak (yerel video modeli, DeepFilterNet, Demucs, Apple VT, Vision OCR). Kurulu olmayanı atla ya da `vlogkit extras install` öner, kendiliğinden kurma. Her iş türü için sıra:

| İstek | Sıra |
|---|---|
| **Ham klasörden vlog / Short** | `log KLASÖR [--vlm]` → log.md'yi ve her klibin sayfalarını oku → hikâye adımları (beat) ve adımlara aday parçalar (`find KLASÖR <türkçe> <english>`) → emin olmadığın adayı `ask` ile doğrula → konuşmalı klipte `gaps` → plan tablosu (klip, zaman, desc) → `new` + `edit.py` → `build` → `review` (+ plan ve kesme sayfaları) → eleştirmen → `check` |
| **Kurgulu videoyu cilala / Short'a çevir** | `analyze` + `sheet` → plan → proje → `build` → `review` → eleştirmen → `check` |
| **Uzun videodan Short'lar** | `moments VIDEO` → moments.md + kare sayfaları → her adaya Kanca/Akış/Değer (1-5, gerekçeli; `docs/viral-edit.md`) → sıralama tablosu → kullanıcının seçtikleri → proje (9:16, `HookTitle`, altyazı stili) → `build` → `review` → eleştirmen |
| **Müziğe göre Reels** | `beats ŞARKI` → kaynak ham ise `log` → `reel ... --dry-run` ile planı göster → onay → `reel` → `review` → `.instagram.txt`'yi rapora yaz |
| **Uzun video** | `analyze` (siyah bant, değişken kare hızı) → düşük çözünürlükse sor, sonra `upscale` → `grade.auto_lift` + `audio.level` → altyazı (`transcribe`, SRT) → bölüm kartları → `review` → `check` |
| **Revizyon** | Sadece istenen değişiklik → `preview` ile değişen anlar → sadece gereken adımları `build -s ...` → `review` |
| **Stüdyo yorumu / kelime kesimi** | `timeline PROJE -v VARYANT --at SN` ile o anı bul → edit.py'de değiştir → gereken adımları derle → `review` (aşağıda "Stüdyo'dan gelen satırlar") |
| **Yayın paketi** | `thumbs` (kaynak görüntüde) + 10 başlık (≤ 50 karakter, vaat açılışla aynı) + açıklama |
| **Resolve'da elle düzenleme** | `resolve PROJE -v VARYANT` |

Sorun → araç:
- **Titrek koşu planı (ham):** `stabilize`.
- **Rüzgâr ya da uğultulu konuşma:** `denoise` (DeepFilterNet), sonra `audio.voice`.
- **Konuşmanın altında telifli ya da gürültülü müzik:** `separate` (Demucs).
- **Telefon (ya da ikinci kamera) ile ayrı kaydedilmiş ses:** `sync KAMERA TELEFON`. Telefonun 0. saniyesinin kameradaki karşılığını, güveni ve kaymayı verir. Elle eşleme yapma; güven düşükse `strip` ile kontrol et.
- **Düşük çözünürlük:** `upscale` (Apple ML), lanczos değil.
- **Bir planın rengi diğerlerinden farklı (ışık, beyaz dengesi):** `match-color VIDEO --ref KARE_YA_DA_KLİP [--ref-at SN] [--at SN]`, sonra `_once-sonra.jpg`'ye bak; uygunsa zincirde Grade'den önce `colormatch.lut_filter(cube)`. Referans benzer bir sahne olsun (gökyüzü/zemin oranı); çok farklı içerik ışığı ve doygunluğu yanlış yöne çeker.
- **Yavaş çekim / hız rampası:** `fx.SpeedRamp`; akıcı olsun istersen `slowmo` (`vt.interpolate`).
- **Kaynakta gömülü yazı:** OCR bayrakları, o anı kullanma.
- **Anlamsız an riski:** log + plan sayfası.
- **Ham çekimde belirli bir an ("göl kenarında ateş"):** `find KLASÖR ateş fire campfire göl lake`; sonuçların 3 karesine bak, emin değilsen `ask`.
- **"Şu videodaki gibi yap":** `recipes/` altındaki tarifi oku; yoksa `recipe PROJE -v VARYANT` ile çıkar. Kullanıcı bir kurguyu onaylayınca tarifini çıkar.
- **Konuşmada nereden keseceğin:** `strip VIDEO --start --end` (10 kare + ses dalgası + sessiz bantlar + kelimeler). Kelimenin bittiği, nefesin ve sonraki hareketin başladığı yer buradan okunur.
- **Kırpma, yüz ya da grafik konumu:** `frame VIDEO -t SN` (tek kare, 0-1 ızgara, kare numarası) ya da `preview PROJE -t SN --grid`. Koordinatı tahmin etme, ızgaradan oku.
- **Özel adlar yanlış yazılıyor (Kaçgar, Soğanlu):** `assets/vocab.txt`'ye ekle; transcribe ipucu olarak verir. Müzikte o adları uyduruyorsa `--no-vocab`.
- **Altyazı stili seçimi:** `vlogkit captions --video VIDEO -t SN` galerisini göster (pop, kutu, sade, karaoke, büyük); seçileni projede `graphics.captions.styled(stil, metin, t0, t1, layout)` ile kur. Parlak/kalabalık görüntüde `kutu`. Büyük harf gerekiyorsa `style.tr_upper` (Python'un `upper()`'ı "i"yi "I" yapar).
- **Kanca başlığı:** Short'ta vaadi ilk saniyelerde üstte tek satırla göster: `graphics.captions.HookTitle("Göle [5 saat] kaldı", 0, 3)` (Reels'te `reel --hook`). 3-7 kelime, kapakla aynı vaat.
- **Güvenli alan:** `review` yazıların platform arayüzünün altında kalıp kalmadığına bakar (dikeyde üst simgeler, alttaki başlık bloğu, sağdaki butonlar; yatayda %90 başlık alanı). `%10`'dan fazlası taşıyorsa düzelt.
- **Kullanıcı düzeltilmiş SRT verdi:** altyazıları ondan kur (`export.subtitles.read_srt`), yeniden transcribe etme.
- **Yabancı yüz, plaka (gizlilik) ya da tek kişiyi vurgulama:** `redact VIDEO --faces [--keep-main]` ya da `--box x,y,en,boy@sn` (kutuyu `frame` ızgarasından oku); vurgu için `--mode spotlight`. Kalabalıkta bazı yüzler kaçar (şapka + gözlük, profil): çıktının sayfasına bak, kaçanlara `--box` ekle. Sadece kullanılan parçayı işle.
- **Konuşma çekiminde kötü arka plan (siyah perde, loş oda):** `background --bg studio|keep|frame:klip@sn --blur 18 --match`. Sadece kullanılan parçaları işle (1 dk ≈ 3 dk).
- **Müzik seçimi:** Telifsiz müziği tek başına seçme: dinleyemiyorsun ve etiketten seçilen parça çoğu zaman sahneye uymuyor. 3-5 aday çıkar (manifest'te `kind = "music"` açıklamaları, `beats`, gerekirse aşağıdaki Pixabay yolu), `music VIDEO -s SN -d SN -t id -t id ...` ile sahnenin altında önizlet, verdiği "Seçim:" bloğunu son mesaja koy ve kullanıcının seçimini bekle. Sahnenin sesinde eski müzik varsa `--no-sound`, konuşmasız sahnede `--level -16`. Kullanıcı "sen seç" derse seç ve nedenini tek cümleyle yaz. Kurguda önizlemedeki başlangıç saniyesini kullan (`id@sn`).
- **Disk az ya da `build` "disk yetmiyor" dedi:** Kendiliğinden silme. `disk` çıktısını (varyant başına ara dosyalar, kaç gündür derlenmedikleri) kullanıcıya göster; onay verirse `disk --clean --older-than N --yes`. Teslim videoları ve kayıtlar silinmez, temizlenen varyant yeniden derlenince eksik adımlar kendiliğinden çalışır. Aynı ara dosyayı başka varyanta kopyalama: hardlink ver (`os.link`).
- **Kameraya konuşma: en iyi deneme (take):** `transcribe` ile denemeleri senaryo satırlarına eşle, aynı satırın adaylarında `face` (mimik, enerji, göz teması), kararı transcript + sayfa ile ver.

**Yerel video modeli (varsa, `doctor`'da "vlm"; Qwen3.5-9B, Mac'te çalışır):**
- **`log --vlm`:** Her ~4 sn'lik parçayı 4 kare/sn izler ve log.md'de "model" sütununa tek cümlelik İngilizce bir gözlem yazar ("opens the door", "putting on shoes").
- **`ask VIDEO --start --end "soru"`:** Belirli bir anı (en fazla 60 sn) tam kare hızında sorar; 24 sn'lik aralık ~20 sn sürer.
- **`face VIDEO --start --end`:** Konuşan kişinin yüzünü takip edip yakın plan keser (Apple Vision) ve mimiği sorar: ifade, enerji, gülümseme/gülme, kameraya bakış, tuhaflık, anlar. En fazla 30 sn; 8 sn ~20 sn sürer. `ask --face` aynı yakın planla serbest soru sorar. Sesi duymaz: espri, vurgu ve ton için transcript'e bak. Anların saniyeleri yaklaşıktır.
- **Aday bulucu, karar verici değil.** Hikâye adımlarının adaylarını model sütunundan bul; seçimi sayfaya bakarak sen yap.
- **Güvenilirlik:** Yönü karıştırabilir (giyiyor/çıkarıyor, giriyor/çıkıyor). Kullanmadan önce sayfada ya da `ask` ile doğrula.
- **Bayraklar:** `[kamera]` ve `kurulum?` yumuşak işarettir (yanlış alarm olabilir), sadece "bak" der; engelleyen, sezgisel `kurulum` bayrağıdır. Modelin kullanışlılık puanı ayırt etmiyor, kullanma.
- **Süre:** Ham süreye yakın (28-09: 52 dk çekim, 44 dk). Önbellekli ve kaldığı yerden devam eder.
- **Kullanıcıya yazarken:** Uzun bir `--vlm` taramasından önce tahmini süreyi söyle. Açıklamaları Türkçe aktar.
- **Isı:** Mac'i ısıtır; build ya da render ile aynı anda çalıştırma. Büyük klasörde acele varsa önce `--vlm`'siz log, sonra aday kliplerde `ask`.

## İş akışı (her edit)
0. **Proje hafızası.** Kullanıcı bir video, klasör ya da projeden bahsediyorsa `projects/*/edit.py` içinde o yolu ara. Projenin `NOTES.md` dosyası varsa oturumun başında oku ve ilk mesajda geçen oturumu tek cümleyle özetle ("Geçen sefer: ..."). Yoksa projeyi açarken `projects/_template/NOTES.md`'den oluştur (`vlogkit new` kopyalar). İş bitince **Kararlar** (tarihli) ve **Açık işler**'i güncelle; kullanıcının bu videoya özel tercihlerini ("emoji yok", "müzik sakin") **Kullanıcının tercihleri**'ne yaz.
1. **Ham klasörden kurgu: önce kayıt (log).** Ham çekimden kurgu yapmadan önce `vlogkit log KLASÖR` çalıştır. Çıktılar: `build/log/<klasör>/log.md` (klip başına tablo), `log.json` ve `sheets/` (her klibin tamamını kapsayan zaman damgalı sayfalar).
   1. Her klibin sayfalarına tek tek bak, hiçbirini atlama. Seyrek bakışla seçilen anlar anlamsız çıkıyor (kameraya eğilme, kaydı başlatma/durdurma). Log'da "model" sütunu varsa (yerel video modeli) önce onu oku: aday anları oradan bul, sonra sayfada doğrula.
   2. `log.json`'da her parçaya `desc` (ne oluyor, 3-8 kelime), `beat` (hikâyedeki yeri) ve gerekirse `keep` yaz. Notlar yeniden çalıştırmada korunur.
   3. Planı hikâye adımlarından (beat) kur. Her adım için o adımı en iyi *gösteren* parçayı seç: "evden çıkış" kapıdan çıkma ya da ayakkabı giyme anıdır, kamerayı kurduğun ya da kameraya eğildiğin an değildir.
   4. `kurulum`, `karanlık` ve `bulanık` parçaları kullanma (kullanıcı `keep: true` demediyse). `çok yakın` ve `sarsıntı` yalnız bilgi; sayfaya bakıp karar ver.
   5. Plan tablosunda her planın klibini, zamanını ve `desc`'ini yaz.
2. **Önce bak:** `vlogkit analyze`, `sheet`. Altyazıları uydurma; bilgiyi konuşmalardan ve kullanıcıdan al. Whisper'ın müzikte uydurduğu satırları (`suspicious`) kullanma. Konuşmalı çekimde `vlogkit gaps` ile boşluk/dolgu adaylarını çıkar: kesmeden önce planda göster. "Konuşmasız" bölümler aksiyon olabilir, onlar ve "yani/şey" isteğe bağlı.
3. **Plan:** Zaman çizelgesini tablo olarak ver ve `docs/viral-edit.md` kontrol listesine göre eksikleri söyle. Kullanıcı "önce plan" dediyse derlemeden dur ve onay iste.
   - İzlenme süresi için modelin her zaman bildiği kurallar (kısa özet, ayrıntısı `docs/viral-edit.md`):
     - Vaat Shorts'ta ilk 1-3 sn'de, uzun videoda ilk 10 sn'de verilir.
     - İlk kare dolu olur, ilk ses 0,5 sn içinde başlar.
     - Aynı görüntü Short'ta 3 sn'den, uzun videoda 5 sn'den uzun durmaz.
     - Tatmin geciktirilir; ödülden sonra hemen bitirilir.
     - Uzun videoda yaklaşık 3. ve 6. dakikada, sonra 2-3 dakikada bir yeniden yakalanır.
     - Her ses efektinin bir sebebi olur.
     - Efektler (hız rampası, freeze, glitch, whip pan) bir anı vurgulamak içindir; Short'ta 1-3 tane yeter.
   - İsteğe bağlı olanlar ancak istenirse ya da açıkça faydalıysa yapılır: loop'lu bitiş, kanca A/B varyantı, kapak/başlık paketi (`vlogkit thumbs` + en fazla 50 karakterlik 10 başlık).
4. **Yazım:** `vlogkit new` ile proje aç, veriyi (zamanlar, altyazılar, SFX) `edit.py`'nin başına yaz. Kütüphanede eksik yetenek varsa projeye özel hack yerine kütüphaneye genel API olarak ekle.
5. **Deneme:** Her deneme ayrı bir **varyant**. Onaylı çıktının üzerine asla yazma.
6. **Doğrulama (öz-denetim turu):**
   - `vlogkit review <çıktı> -p <proje> --promise "<vaat kelimeleri>"`: her teslimde. `!` maddelerini düzelt ya da neden bıraktığını söyle; özetini son mesaja yaz.
   - Review'un **plan sayfasına** (`<ad>_planlar.jpg`, her planın orta karesi, numaralı) bak. Her plan hikâyede bir şey anlatmalı; kurulum, lense eğilme, anlamsız duvar ya da bulanık geçiş varsa değiştir.
   - **Kesme sayfalarına** (`<ad>_kesmeler*.jpg`: her kesmenin öncesi, son karesi, ilk karesi, sonrası) bak. Review'un "Kesmeler" bölümü birkaç karelik artık planı, siyah kareyi, donuk görüntüyü ve kesmedeki ses sıçramasını zamanıyla verir. Şüpheli kesmeyi `strip` ile incele.
   - **Eleştirmen:** Yeni kurguda ya da büyük revizyonda, teslimden önce `vlogkit-critic` alt ajanını çalıştır; ona video yolunu, proje/varyantı, kullanıcının isteğini ve review raporunun yolunu ver. Codex'te alt ajan yok: `docs/critic.md`'deki listeyle ayrı bir tur yap. Küçük düzeltmelerde gerekmez.
   - **Tur sınırı:** Bulunanları düzelt → sadece gereken adımları derle → review. En fazla 3 tur; sonra kalanları son mesajda "Açık kalanlar" başlığıyla kullanıcıya yaz, döngüye girme.
   - `vlogkit check <çıktı> --cuts`: -14 LUFS, <= -1 dBTP; müzik korunuyorsa kesmeler kaynakla birebir aynı.
   - Kritik anların kontak sayfası.
   - Sesi duyamazsın: ölçümleri raporla, son dinlemeyi kullanıcıya bırak.
7. **Rapor:** Son mesajda üretilen dosyaları mutlak yollarıyla "Çıktılar:" altında listele.

## Stüdyo'dan gelen satırlar
Kullanıcı çıktı videosunun altındaki zaman çizelgesinden mesaja satır ekleyebilir. Zamanlar hep **teslim edilen videodaki** zamandır, kaynaktaki değil.
- **`[01:23.4 · plan 12/40 · Caption: ...] yorum`:** O andaki yorum. `vlogkit timeline PROJE -v VARYANT --at 83.4` ile o andaki planı, yazıyı ve bölümü doğrula, değişikliği `edit.py`'de yap (planın kaynağını projenin kendi verisinden bul). Sadece isteneni değiştir, gereken adımları derle.
- **`Kes (çıktıda): 00:12.40–00:13.10 «yani şey»`:** Çıktıdaki o kelimeleri kes. Aralığı kaynağa çevir, kelime sınırına oturt (`vlogkit strip` ile bak), iki yanda nefes payı bırak, kesmede kısa ses geçişi yap, sonraki altyazı/efekt zamanlarını kaydır. Birden çok satır gelirse hepsini tek turda uygula.
- **`Seçim: 2. etiket`:** Kullanıcı son mesajındaki "Seçim:" kartlarından birini seçti (ör. müzik). O seçenekle devam et.
- **Kalan işler:** Hemen yapılamayan yorumları ve kullanıcıya dinletilecek anları projede `notes()` olarak tut (edit.py'nin en üstünde `NOTES = [(sn, "metin")]`; `Edit.notes()` bunu okur): Stüdyo zaman çizelgesinde ve Resolve'da işaretçi olarak görünür.
- **Kurgu ayarı:** Mesajda "Kurgu ayarı: kaba kesim ..., müzik yok, ...; ince kesim: ..." satırı varsa kesim içeren işlerde uygula, planın ilk satırında tek cümleyle teyit et; kesim içermeyen işte yok say. Satırda yalnız kullanıcının seçtikleri var: geçmeyen katman için kendi kararını ver (istenmediyse ekleme kuralı geçerli).
  - **temkinli:** yalnız ölü boşluklar ve açık hatalar (`gaps --min-pause 0.8 --pad 0.18`); dolgular ve doğal nefesler kalır.
  - **dengeli:** `gaps` varsayılanı (0,45 sn duraklar, 0,12 sn pay) ve sert dolgular; "yani/şey" kalır.
  - **sert:** `gaps --soft --min-pause 0.25 --pad 0.08`; "yani/şey" dahil, sıkı jump cut. Short'ta doğal seçim.
  - **"altyazı yok" / "müzik yok" / "ses efekti yok":** o katmanı ekleme. İnce kesim notunu plana uygula; mesajda referans görsel varsa ona göre.
- **Zaman çizelgesi verisi:** Her `build` ve `reel` `build/timelines/` altına yazar (planlar `Edit.cuts()`'tan, yazılar elemanlardan, bölümler `chapters()`'tan, notlar `notes()`'tan). Eski bir çıktı için `vlogkit timeline PROJE -v VARYANT`.

## Kurallar
- **ffmpeg:** Her zaman argüman listesiyle çalıştır (vlogkit sarmalayıcıları). Filtre zincirlerini shell string'ine gömme. Normal `ffmpeg` değil `ffmpeg-full` kullan (vlogkit otomatik bulur).
- **Zamana bağlı ifadeler:** `video/expr.py` yardımcılarıyla yaz (`window`, `nan_safe`); kare hassasiyeti için `timecode.before_frame`.
- **Oran ve çözünürlük:** Kaynağın oranını ya da çözünürlüğünü değiştirmek (kırpma, büyütme, dikey↔yatay) bir karardır, sessizce yapma. Planda ayrı madde olarak yaz ve kalite etkisini söyle. Kaynak düşük çözünürlüklüyse (aktif görüntü < 720p) büyütmeden önce kullanıcıya sor; büyütülecekse `vlogkit upscale` / `vt.upscale` (Apple ML) kullan, lanczos değil. "Oranı koru" denirse kaynağın oranını ve boyutunu değiştirme.
- **Emoji:**
  - Shorts altyazılarında en fazla üç altyazıda bir emoji olsun, altyazı başına tek emoji ve sadece anlam katıyorsa (yer, nesne, duygu). Uzun videonun konuşma altyazısında (`Subtitle`) emoji olmaz.
  - `overlay` adımı kural aşılınca `!` ile uyarır (`graphics.emoji_notes`). Kullanıcı "Emoji kullanma" dediyse hiç kullanma.
  - Kullanıcıya yazdığın mesajlarda emoji kullanma.
- **Öneriler:** Bu iş için gerekmeyen ama sonraki editlerde işe yarayacak bir vlogkit geliştirmesi görürsen son mesajda tek satır "Öneri:" yaz, kendiliğinden yapma. (İşin kendisi için gereken eksikler 3. adımdaki gibi kütüphaneye eklenir.)
- **Müzik (Reels / Shorts):**
  - Telifli bir şarkıyı indirme (YouTube, Spotify) ve videoya gömme.
  - Kullanıcı kendi yasal kopyasını verirse şarkı sadece ritim rehberi olur: kurgu ona göre yapılır, teslim edilecek dosya müziksizdir. Şarkı Instagram ya da YouTube uygulamasının kendi kütüphanesinden eklenir; `.instagram.txt` başlangıç saniyesini söyler.
  - İşletme hesabı yalnız Meta Sound Collection kullanabilir.
  - Telifsiz müzik (CC0, Pixabay, lisanslı; manifest'e kayıtlı) videoya gömülebilir.
  - Yeni Pixabay parçası: "Authentic only" filtresiyle ara (yapay zekâ üretimini eler), sayfasında "Content ID Registered" rozeti olanı alma, sayfa adresini manifest'e `page` olarak yaz (sonradan talep gelirse Pixabay lisansıyla itiraz edilir). Vokal, mırıltı ya da vokal kesiti olabilir: kullanıcıya `music` ile dinlet.
- **Telif:** Sadece kendi çekimler, sentez efektler ve manifest'teki CC0 / Pixabay / Pexels dosyaları. Yeni medya eklersen kaynak, lisans ve yazarla manifest'e yaz; Pixabay müziğinde sayfanın Content ID rozeti olmadığını gördüğün günü `checked = "YYYY-AA-GG"` olarak ekle. Her derleme kullandığı kütüphane dosyalarını kaydeder ve videonun yanına `<video>.lisans.md` yazar (lisans, sayfa, itiraz metni); medyayı `ctx.asset(id)` ile al ki kayda girsin. Film, dizi, spor ya da viral kullanıcı videosu kullanma.
- **vlogkit'i geliştirince:**
  - Kodu ekle, sonra bir test yaz.
  - `docs/workflow.md` (yeni tuzak varsa), `README.md` ve `CHANGELOG.md`'yi güncelle.
  - `docs/prompts.md`'yi güncelle, sonra `uv run python scripts/build_prompts_page.py --out <scratchpad>/p.html` ile sayfayı üret ve prompt artifact'ini aynı adrese yeniden yayınla. Adres `docs/prompts.md` içindeki meta satırında.
  - Kurulu kopyaları etkileyen bir değişiklikse (yeni bağımlılık, yeni araç ya da model, yeni ayar dosyası) Stüdyo'nun kurulum adımlarını (`ui/setup.py` `steps`), `KURULUM.md`'yi ve herkese açık sayfayı (`docs/public/README.md`) da güncelle. `install.sh` yalnız Stüdyo'yu kurar; ağır parçalar kurulum ekranından gelir. Kullanıcıya ait yeni bir dosya türü (proje verisi gibi) eklersen yayın reposunda git dışında kalmalı: `scripts/release.py` içindeki `IGNORE_EXTRA`.
  - **Yayın:** Kullanıcı `main`'e birleştirmeyi istediğinde, birleştirdikten sonra `uv run python scripts/release.py` çalıştır: araç kodu herkese açık `vlogkit-studio` reposuna yeni sürüm etiketiyle gider, kurulu kopyalar Stüdyo'dan günceller. Aynı sürüm numarası ikinci kez yayınlanmaz; yeni yayın için sürümü artır. Yayın kişisel bir terim bulup durursa (`scripts/private-terms.txt`) o yeri genelleştir (kişi adı, kişisel süre, özel video adı yerine genel ifade), terimi listeden çıkarma. Kişi adlarını ve özel ayrıntıları docs/ ve kod yorumlarına baştan yazma.
- **Kontroller:** `uv run pytest` ve `uv run ruff check .` temiz kalmalı.
- **Git:**
  - Geliştirici reposu private, ana dal `main` (geliştirme `dev` dalında).
  - Commit ve push'u kullanıcı istediğinde yap.
  - Commit mesajları İngilizce, kısa başlık + madde madde gövde. Sonunda Co-Authored-By satırı olsun.
  - Medya ve build dosyaları asla commit'lenmez.
