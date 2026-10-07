# vlogkit Prompt Rehberi

<!-- meta: vlogkit=0.14.2; updated=2026-10-06; artifact=https://claude.ai/artifact/WQakjmnPnJ95AJ1kyQPdPW -->

Yeni bir vlog'u Claude'a vlogkit ile kurgulatırken kullanacağın hazır prompt'lar. Hepsi vlogkit'in bugünkü yeteneklerine göre yazıldı. vlogkit geliştikçe bu dosya da güncellenir: kaynak `docs/prompts.md`, sayfa `scripts/build_prompts_page.py` ile üretilip artifact olarak yayınlanır. Aynı dosya `vlogkit ui` arayüzündeki görev listesini de besler: arayüzde bir görevi seçince prompt buradan gelir ve seçtiğin video ile formdaki bağlam bilgileri doldurulur.

## İyi bir prompt'un iskeleti {#iskelet}

Claude en iyi işi şu 7 bilgiyle çıkarır. Bilmediğin alanı boş bırak; Claude analizden tamamlar ve varsayımlarını söyler.

```slate
KLASÖR:   ~/yt-vlogs/<vlog-klasörü>
KONU:     <1-2 cümle: ne oldu, nerede, kimler var>
HEDEF:    <uzun video | Short | Reels | Short serisi (kaç bölüm)>
KAYNAK:   <hangi dosya ne: ham çekim, müzikli kurgu, uzun kurgu, ses kaydı>
TARZ:     <kackar-short01 v1 gibi | daha sade | meme dozu düşük/orta/yüksek>
KISITLAR: <müziği koru, en fazla 60 sn, altyazı Türkçe, telifli klip yok>
SÜREÇ:    <önce analiz + plan göster, onayımı bekle | direkt derle>
```

- **KLASÖR ve KAYNAK:** vlogkit projeleri görüntülere `~/yt-vlogs` köküne göre bakar. Hangi dosyanın ham, hangisinin kurgulanmış olduğunu bilmek kararların yarısı.
- **KONU:** Altyazılar uydurma değil, gerçek bilgi olmalı. Claude bunları konuşmalardan (whisper) çıkarır ama bağlamı sen verirsen daha isabetli olur.
- **TARZ:** Mevcut bir projeyi referans göstermek ("kackar-short01 v1 gibi") en net tarif.
- **SÜREÇ:** Büyük işlerde önce plan iste, küçük düzeltmelerde direkt derlesin.

## Prompt'lar {#promptlar}

### Keşif {#kesif}

#### Yeni vlog klasörünü keşfet

Ne zaman: Yeni bir klasör geldiğinde, hiçbir şeye karar vermeden önce.

```text
~/yt-vlogs/<klasör> klasörüne yeni bir vlog koydum: <1-2 cümle konu>.
vlogkit ile her videoyu analiz et (vlogkit analyze): kesmeler, loş yerler, ses seviyesi, konuşmalar, vuruşlar.
Sonra bana şunları çıkar:
1) Her dosya ne, hangisi ham, hangisi kurgulanmış
2) Konuşmalardan çıkan gerçek bilgiler (saat, sayı, yer, şakalar)
3) Uzun video için bölüm yapısı önerisi
4) En güçlü 3-5 Short adayı (zaman aralığı + hook fikri)
Henüz hiçbir şey derleme, önce planı konuşalım.
```

Claude ne yapar: Her dosya için `vlogkit analyze` raporu, kontak sayfası ve transkript çıkarır (`build/analysis/`), sonra planı sunar. Video üretmez.

Varyasyonlar:
- Sadece `<dosya>` için yap.
- Konuşmalar İngilizce (transkript dilini değiştirir).
- Kontak sayfalarını bir artifact'te yan yana göster.

#### Tek videoya hızlı bakış

Ne zaman: Bir dosyanın durumunu hızlıca öğrenmek istediğinde.

```text
~/yt-vlogs/<klasör>/<dosya>.mp4 için vlogkit analyze çalıştır ve raporu 5 maddede özetle:
format, kesmeler, loş bölgeler, ses (LUFS / dBTP, clipping var mı), konuşma özeti.
```

Claude ne yapar: Tek rapor üretir. 10/12/16-bit çekimlerin parlaklığını ortak 8-bit (0–255) referansında ölçer; kaynak dosyayı değiştirmez. Whisper'ın müzikte uydurduğu satırları işaretleyip ayıklar.

### Short {#short}

#### Kurgulanmış Short'u parlat (Short 01 yöntemi)

Ne zaman: Elinde müzikli, kurgusu bitmiş dikey bir video var; hook, altyazı, renk ve ses istiyorsun.

```text
~/yt-vlogs/<klasör>/<dosya>.mp4 kurgulanmış bir Short. Müziğin zamanlamasına dokunmadan kackar-short01 v1 tarzında parlat:
- İlk 2 saniyeye güçlü bir hook (varsa aynı vlogdan daha çarpıcı bir an ya da ses)
- Konuşmalardan ve bağlamdan çıkan gerçek bilgilerle altyazılar (vurgu rengi, az emoji)
- Renk, loş sahneleri aydınlatma, sabit planlara hafif zoom
- Ses -14 LUFS, gerekirse küçük efektler
- Bitiş kartı serinin sonraki bölümüne: "<sonraki bölüm>"
Önce zaman çizelgesi tablosu olarak kısa bir plan göster, onaylarsam derle. Proje adı: <vlog>-short<NN>.
```

Claude ne yapar: Analiz ve plan tablosu çıkarır. Sonra `vlogkit new` ile `edit.py` açar ve derler. Kesmelerin kaynakla birebir aynı olduğunu doğrular, kritik anların kontak sayfasını gösterir.

Varyasyonlar:
- Hook için `<başka dosya>`'nın `<sn>` anını kullan.
- Altyazı yoğunluğu düşük olsun, sadece önemli anlar.
- Bitiş kartı olmasın, başa bağlanan döngü (loop) yap.

#### Ham çekimden sıfırdan Short

Ne zaman: Elinde kurgulanmamış klipler var; en iyi anların seçilip 30-45 sn'lik bir Short kurulmasını istiyorsun.

```text
~/yt-vlogs/<klasör>/ içindeki ham kliplerden <konu> hakkında 30-45 sn'lik bir Short kur.
Önce ham çekimi logla (vlogkit log) ve kamerayı kurduğum / lense eğildiğim anları kullanma.
En güçlü anları seç, ilk 2 saniye hook olsun, hikâye başlangıç, gelişme ve son izlesin.
Müzik: <kendi dosyam: ~/yt-vlogs/<klasör>/muzik.mp3 | telifsiz 3-5 aday öner, sahnenin altında dinleyip ben seçeyim | sessiz bırak, müziği YouTube'da ben eklerim | kliplerin kendi sesi>.
Kesmeleri müziğin vuruşlarına oturt (vlogkit beats).
Önce seçtiğin anları ve sırasını tablo olarak göster.
```

Not: YouTube Audio Library'ye Claude giremez. Telifsiz kütüphaneden (Pixabay, CC0) Claude aday bulur ama dinleyemez: seçimi sen yaparsın (aşağıda "Sahneye müzik seç"). Ham kliplerden kurgu vlogkit'te şimdilik şablon seviyesinde; Claude gerekirse kütüphaneye segment seçme yardımcıları ekler.

#### Uzun videodan Short'lar çıkar

Ne zaman: Yatay uzun video hazır, içinden dikey Short'lar üretmek istiyorsun.

```text
~/yt-vlogs/<klasör>/<uzun video>.mp4 yatay uzun video. Bundan <3> dikey Short çıkar:
her biri tek bir fikir ya da an, 30-60 sn.
16:9'dan 9:16'ya kırparken konuyu (yüz, hareket) takip et. Konuşma varsa kelime kelime karaoke altyazı koy.
Her Short'un sonunda diğerine ya da uzun videoya yönlendir.
Önce aday anları (zaman aralığı + hook cümlesi) puanlarıyla listele.
```

Claude ne yapar:
- `vlogkit moments` ile adayları çıkarır; her birine kanca, akış ve değer için 1-5 puan ve tek satır gerekçe verir. Bu bir tahmin değil, sıralamadır.
- Seçtiklerini 4K'dan yüzü takip eden kırpmayla kurar, Whisper'ın kelime zamanlarıyla karaoke altyazı koyar.
- İlk saniyelere vaadi tek satırla söyleyen bir kanca başlığı önerir; altyazı stili için galeriyi gösterir.

Örnek (`projects/rize25-shorts`): üç farklı biçim aynı videodan çıktı. Hikâye Short'u (açılış konuşmasındaki bir anekdot, B-roll üstüne ses, sonda fotoğrafla ödül), absürt plan Short'u (konuşmadaki cümleler her adımın görüntüsünün üstünde) ve müzik montajı (yarım ölçüde kesmeler). Prompt'a "biri hikâye, biri komik, biri müzikli olsun" diye yazabilirsin.

#### Short serisi planla

Ne zaman: Tek bir vlogdan birbirine bağlanan bir seri çıkaracaksın.

```text
~/yt-vlogs/<klasör> vlogundan tutarlı bir Short serisi planla (<N> bölüm).
Her bölüm için: kapsadığı aralık, hook, 3-5 altyazı fikri, sonraki bölüme bağlanan bitiş kartı.
Tasarım dili tüm seride aynı olsun (kackar-short01 v1). Plan onaylanınca bölümleri tek tek derleriz.
```

#### Meme / shitpost varyantı

Ne zaman: Onaylı versiyonun daha eğlenceli bir alternatifini denemek istiyorsun.

```text
<proje> için bir meme varyantı çıkar, onaylı v1'e dokunma.
Meme dozu: <düşük | orta | yüksek>.
Sadece lisanslı kaynak kullan (assets/manifest.toml). Gerekirse CC0 / Pixabay / Pexels'ten yeni ekle ve manifest'e yaz.
Fikirler: vine boom + ani zoom, siyah-beyaz "sigma" anı, stok klip araya kesme, ironik ses efektleri.
Film, dizi, spor yayını ya da viral kullanıcı videosu kullanma.
```

Claude ne yapar: `-v meme` varyantı açar. Ses efektlerini `Sfx` ile müziği kısarak yerleştirir, stok klipleri `Insert` ile araya keser. Yeni varlıkları lisanslarıyla manifest'e ekler.

#### Hook A/B denemesi

Ne zaman: Açılışın tutup tutmayacağından emin değilsen.

```text
<proje> için ilk 3 saniyenin 3 farklı varyantını hazırla:
A) sonucu önce göster (flash-forward), B) soru / merak cümlesi, C) büyük sayı ya da saat.
Geri kalanı aynı kalsın. Üçünün ilk 3 saniyesini yan yana kontak sayfası olarak göster.
```

#### Müziğe göre Reels

Ne zaman: Bir şarkının ritmine göre Instagram Reels (ya da Short) yapılacak.

```text
<şarkı dosyası> ile ~/yt-vlogs/<klasör>/ kliplerinden (kronolojik sırayla: <klip1>, <klip2>, ...)
<süre> saniyelik bir Reels yap. Önce şarkının yapısını göster (BPM, drop, enerji haritası) ve
şarkının hangi aralığını kullanacağını öner; drop ilk 3 saniyede gelsin. Kesmeler vuruşta olsun,
en güçlü an drop'a düşsün. Gömülü yazılı anları kullanma. Planı tablo olarak göster, onaylayınca derle.
```

Claude ne yapar:
- `vlogkit beats` ile şarkının yapısını çıkarır.
- `vlogkit reel` ile kesmeleri vuruşlara oturtur. Drop'ta punch-in ve flaş olur, drop öncesinde tempo ikiye katlanır, cümle sonlarında fill yapılır.
- Anları hareket, kalite ve hikâye sırasına göre seçer; gömülü yazılı anları OCR ile atlar.
- İstersen drop'a hız rampası, bölüm geçişine whip pan ekler.
- Teslim: şarkılı dosya (izlemek için), müziksiz dosya (yüklemek için) ve şarkıyı Instagram'da hangi saniyeden başlatacağını söyleyen not.

Şarkı: Telifli bir şarkıyı Claude indirmez. Satın aldığın dosyayı ver; kurgu ona göre yapılır, yüklerken aynı şarkıyı Instagram'ın kütüphanesinden eklersin (işletme hesabında sadece Meta Sound Collection). Telifsiz (CC0, lisanslı) müzik doğrudan gömülebilir; örnek: `assets/library/music/orchestral_trap_bertsz_fs524313.mp3`.

#### Trend şarkılarla Reels varyantları

Ne zaman: Elinde şarkı dosyası yok. Instagram'da o an popüler şarkıların havasına ve ritmine göre birkaç alternatif Reels istiyorsun.

```text
~/yt-vlogs/<klasör> serüvenini incele ve Instagram Reels için <4-5> farklı alternatif üret.
Instagram'da şu an trend olan şarkıları bul; her varyant bir şarkının havasına ve ritmine göre kurgulansın
(sert drop, sinematik yükseliş, neşeli, karanlık/atmosferik, Türkçe trend gibi farklı tonlar).
Onaylı versiyona dokunma, yeni proje/varyant aç. Soru sormadan sonuna kadar götür.
```

Claude ne yapar:
- Trend listelerini tarihleriyle araştırır.
- Her şarkının BPM'ini ve bölüm zamanlarını çıkarır: senkron söz zamanlarından (LRCLIB), şarkıyı indirmeden.
- Ham çekimi tarayıp anları seçer, kurguyu `music.grid` tempo haritasına göre yapar.
- Her varyantı `vlogkit review` ve `check` ile doğrular.
- Teslim: müziksiz dosya, rehber ritim sesli önizleme ve `.instagram.txt` (başlangıç saniyesi, hizalanacak kesme). Örnek: `projects/kackar-reels`.

Not: BPM ve söz zamanları topluluk verisi (~±0,3 sn). Şarkıyı uygulamada eklerken nottaki kesmeyi vuruşa hizalamak gerekir. Meta'nın Edits uygulamasında ses dalgasıyla hizalamak en kolayı. Şarkı işletme hesabında çıkmayabilir.

#### Beğendiğin bir kurgunun tarzıyla

Ne zaman: Önceki bir kurguyu çok beğendin, yeni videoyu da onun gibi istiyorsun.

```text
~/yt-vlogs/<klasör>/ham/ çekimlerinden <Short | Reels | uzun video> yap, <kackar-short01> kurgusunun tarzında:
aynı açılış hızı, plan ritmi, yazı stili ve efekt dozu. Önce tarifi göster, farkları söyle.
```

Claude ne yapar:
- `recipes/` altındaki tarifi okur; yoksa `vlogkit recipe` ile onaylı kurgudan çıkarır.
- Sayıları yeni malzemeye uyarlar: malzeme zayıfsa daha kısa planlar, konuşma çoksa daha sade yazı.
- Planda tariften nerede ayrıldığını tek satırla söyler.

### Uzun video {#uzun}

#### Ham kliplerden yatay vlog

Ne zaman: YouTube için 16:9 bir vlog kurgulanacak.

```text
~/yt-vlogs/<klasör>/ ham kliplerinden <süre> dakikalık yatay bir vlog kur.
Önce ham çekimi logla (vlogkit log; yerel video modeli kuruluysa --vlm, süresini önce söyle), her klibin sayfasına bak, parçalara ne olduğunu yaz.
Yapı: soğuk açılış (en güçlü an), giriş, <bölümler>, kapanış; her bölüm için o anı en iyi gösteren parçayı seç.
Konuşmaları transkript et, gereksiz ve tekrar eden kısımları çıkar (jump cut), sesi eşitle (-14 LUFS).
Bölüm kartları ve açıklama için YouTube bölüm zaman damgaları üret.
Önce bölüm planını ve seçtiğin klipleri tablo olarak göster.
```

Not: Yatay 16:9 düzen (`LANDSCAPE`), bölüm kartı, SRT ve bölüm listesi hazır. Konuşmalardaki boşluk ve dolgu kelimeler `vlogkit gaps` ile aday olarak listelenir; onayladıkların `jumpcut` ile kesilir.

#### Kurgusu bitmiş uzun videoyu cilala

Ne zaman: Kurgu hazır; renk, ses, altyazı ve bölümler eksik.

```text
~/yt-vlogs/<klasör>/<dosya>.mp4 kurgusu bitmiş uzun bir video. Kurguya dokunmadan:
renk düzelt (loş planlar), sesi -14 LUFS'a getir, konuşmalara Türkçe altyazı çıkar
(SRT olarak, istersen videoya gömülü), açıklama için bölüm zaman damgalarını yaz.
```

Claude ne yapar: Siyah bant ve değişken kare hızı varsa bulur, görüntüyü 1920x1080'e temizleyerek büyütür, loş planları plan plan aydınlatır (gece atmosferini koruyarak). Sesi kesmelere hizalı eşitleyip -14 LUFS'a getirir. Konuşmaları birden fazla whisper ayarıyla doğrular ve sadece tutarlı satırları konuşulan dilde altyazı yapar. Çıktının yanına `.srt` ve `.chapters.txt` yazar, kesmelerin kaynakla birebir aynı olduğunu `check --cuts` ile gösterir.

Varyasyonlar:
- Başa sonucu önce gösteren bir hook ekle (flash-forward + geri sarma), kurgu arkada aynen kalsın.
- Altyazılar sadece SRT olsun, videoya gömme.
- Dikey (9:16) teslim et, yazılar siyah bantlarda olsun.
- Kaynak 4K: 4K teslim et, yazılar da 4K çizilsin (`LANDSCAPE_4K`); başa göl/zirve anından soğuk açılış ve ortada başlık kartı (`TitleCard`) koy.

#### DaVinci Resolve ile ince ayar

Ne zaman: Son dokunuşları kendin Resolve'da yapmak istiyorsan.

```text
<proje> projesini DaVinci Resolve'a aktar (vlogkit resolve <proje> -v <varyant>).
Eksik build adımı varsa önce onu derle. Klasörün yolunu, kaç plan / katman / düzenlenebilir metin çıktığını
ve içe aktarma adımlarını kısaca yaz. Sesleri ayrı düzenlemek istersem hangi dosyayı açacağımı söyle.
```

Ne çıkar:
- Final video olduğu gibi kalır; yanına `<çıktı>_resolve/` klasörü yazılır.
- Görüntü plan plan bölünür (V1). Her altyazı ve grafik ayrı, şeffaf bir klip olur (V2 ve üstü); kaydırıp silebilir, zamanını değiştirebilirsin.
- En üstte her altyazının kapalı bir Resolve metni kopyası durur. Bir kelimeyi değiştirmek için onu açıp altındaki resmi kapatırsın.
- Sesler ayrı izlerde gelir (`_stems.fcpxml`). Resolve'da File > Import > Timeline ile açılır.
- Yazıların birebir görünümü resim katmanlarında. Resolve metninde kontur, gölge ve emoji aynı olmaz.

#### Konuşmalı çekimi toparla

Ne zaman: Kameraya konuştuğun uzun bir çekimde duraklamalar ve "ııı, eee"ler var.

```text
~/yt-vlogs/<klasör>/<dosya>.mp4'teki konuşmalarda boşlukları ve dolgu kelimeleri bul (vlogkit gaps).
Kesme adaylarını tablo olarak göster; "konuşmasız" bölümleri ve "yani/şey"leri ayrı işaretle.
Onayladıklarımı kes, nefes payı bırak, sesi tıklatma; altyazı ve efekt zamanlarını yeni kurguya taşı.
```

Claude ne yapar:
- Whisper kelime zamanları ve sessizlik ölçümünden adayları çıkarır: duraklama, dolgu, konuşmasız bölüm.
- Onayladıklarını kareye hizalı keser ve her kesmede 10 ms ses geçişi koyar.
- Kazanılan süreyi söyler.
- Koşu ya da manzara gibi konuşmasız aksiyonu varsayılan olarak kesmez.

#### Senaryolu konuşma çekimi: en iyi denemeler ve arka plan

Ne zaman: Bir senaryoyu kameraya birkaç deneme hâlinde anlattın, arkada siyah perde var.

```text
~/yt-vlogs/<klasör>/ham/ içindeki denemeleri ~/yt-vlogs/<klasör>/senaryo.md'ye göre kurgula.
Her senaryo satırı için denemeleri bul, mimiğe ve akıcılığa göre en iyisini seç, seçimleri tabloda göster.
Arka planı değiştir: <studio ışığı | bulanık manzara, ham/<klip>@<sn> | perdeyi koru, arka ışık>.
Önce plan göster, onaylamadan derleme.
```

Claude ne yapar:
- `transcribe` ile denemeleri senaryo satırlarına eşler; aynı satırın adaylarında `face` ile mimiği (ifade, enerji, gülümseme, kameraya bakış) karşılaştırır.
- Tonu ve espriyi transcript'ten değerlendirir; yerel model sesi duymaz.
- Onaydan sonra yalnız seçilen parçalarda `background` çalıştırır (1 dk ≈ 3 dk) ve kurguya koyar.

#### Anlatımı kurgulu videoya ekle (konuşma + ses + köşe penceresi)

Ne zaman: Kurgusu bitmiş bir videonun başına, arasına ve sonuna kameraya konuşma çektin; bazı yerlerde sen görüneceksin, bazı yerlerde sadece sesin.

```text
~/yt-vlogs/<klasör>/<konuşma-klasörü> içindeki denemeleri <proje> (<varyant>) videosuna anlatım olarak ekle.
Senaryo (zamanlar mevcut kurguya göre, konuşmalar birebir değil):
- Başlangıç: <açılış konuşması>
- <dk:sn>: <satır> (<kamerada | sadece ses | sol altta pencere>)
- Son: <kapanış satırı>, sonra kameranın önünden çıkarım, duvarda "<yazı>" belirir
Arka plan: <tam siyah | sıcak loş ışık | sen seç>. Kurguyu <1 | 3> farklı yapıda dene.
```

Claude ne yapar:
- Satırlara denemeleri ses zarfı + whisper ile eşler, adaylarda `face` ile mimik ve enerjiyi karşılaştırır, seçimleri nedenleriyle tabloya yazar.
- Görünen parçalarda arkayı değiştirir ve kişiye ayrı renk verir; atlama kesmelerini kadraj değişimiyle (geniş / orta / yakın) gizler.
- "Sadece ses" satırlarını ses dışı (VO) ya da L-cut olarak koyar, altında kamera sesini ve müziği kısar; "pencere" satırlarını `video.pip` ile köşeye yerleştirir.
- Onaylı kurguya dokunmaz: yeni proje ve varyantlar açar, altyazıyı `.srt`'ye yazar.

#### Tek çekim açılış konuşmasını toparla (telefon sesi + kesmeler + efektler)

Ne zaman: Kameraya tek seferde bir giriş konuşması çektin, sesi ayrıca telefonla kaydettin; videonun başına hızlı ve canlı bir şekilde girmesini istiyorsun.

```text
<konuşma>.MP4'ü (sesi <telefon-kaydı>.wav'dan) <proje> videosunun <sn>. saniyesine koy.
Baştaki hazırlığı ve "<son cümle>"den sonrasını at; nefes aralarını kes, ilk 15-30 sn hızlı aksın.
<dk:sn>-<dk:sn> arasını çıkar, sadece "<cümle>"yi tut ve ona <TV paraziti | yağmur | ...> efekti ver.
Bir-iki yerde "yakınlaş, yakınlaş, geri çekil" kamera hilesi yap. <dk:sn>'de bahsettiğim fotoğrafı sağ üstte küçük göster.
Konuşma bitince eski film gibi 3-2-1 geri sayımla asıl video başlasın.
```

Claude ne yapar:
- Telefon sesini kamera sesiyle zarf korelasyonuyla eşler (kaymayı ölçer), konuşmanın başını ve sonunu zarftan bulur.
- Nefes aralarını ve uzun duraklamaları keser; her kesmede kadrajı değiştirir (yüze ortalı yakın plan), espri anlarında çift yakınlaştırma yapar.
- Efektleri ve öğeleri ekler: `LOOKS` (parazit, yağmur), `PhotoInset`, `FilmLeader` (projektör sesi ve bip ile), son karede `SoftText`.
- Konuşmanın altına sesin ~15 LU altında hafif bir müzik koyar, esprili kısımlarda daha da kısar.

### Revizyon {#revizyon}

#### Somut geri bildirimle düzelt

Ne zaman: Derlenmiş bir versiyonda değiştirmek istediğin belirli şeyler var.

```text
<proje> (<varyant>) için düzeltmeler:
- 4.9 sn'deki altyazı "<yeni metin>" olsun
- 22 sn'deki "wow" sesi çok yüksek, yarıya indir
- 33-35 sn arasındaki köpek klibi kalsın, üst yazı "<yeni metin>" olsun
Sadece bunları değiştir, derle ve değişen anların önizlemesini göster.
```

Not: Zamanı saniye olarak ver ("şurası" yerine "32 sn'deki zoom"). Claude önce `vlogkit preview` ile gösterir, sonra derler.

#### İki varyantı karşılaştır

Ne zaman: v1 ile bir deneme arasında karar vereceksen.

```text
<proje> v1 ile <varyant> varyantını karşılaştır: aynı 8 anı yan yana kontak sayfası olarak göster,
ses seviyelerini (momentary LUFS) tablo halinde ver, hangisinin daha iyi tutacağını gerekçesiyle söyle.
```

#### Varyantlardan seçip birleştir

Ne zaman: Bir denemenin sadece bazı parçalarını beğendin.

```text
<proje> meme varyantından sadece şunları al: <vine boom anı, siyah-beyaz ayna sahnesi>.
Diğerleri v1'deki gibi kalsın. Bunu yeni bir varyant (v2) olarak çıkar, v1'e dokunma.
```

#### Sahneye müzik seç

Ne zaman: Bir sahnenin ya da tüm videonun müziği yok veya mevcut müzik sahneye uymuyor.

```text
<video ya da proje>'nin <12-42 sn> arasındaki sahnesi için telifsiz müzik öner: <sakin, yükselen, gitar | enerjik, vuruşlu>.
Kütüphaneden ve gerekirse Pixabay'den 3-5 aday çıkar, sahnenin altında dinletip bana seçtir.
```

Claude ne yapar:
- Adayları manifest'teki açıklamalardan ve `beats` analizinden seçer; yeni Pixabay parçasında "Content ID Registered" rozeti olmayanı alır ve manifest'e yazar.
- `vlogkit music` ile her aday için sahnenin altında kısa bir önizleme yapar; Stüdyo'da kartlar çıkar, birini oynatınca diğerleri durur.
- "Bunu seç" dediğin parçayı, önizlemedeki başlangıç saniyesiyle kurguya koyar. "Sen seç" dersen kendisi seçer ve nedenini yazar.

### Yayın {#yayin}

#### Başlık, açıklama, etiketler, kapak

Ne zaman: Video hazır, yüklemeden önce.

```text
<çıktı dosyası> için YouTube yayın paketi hazırla:
10 başlık (en fazla 50 karakter, videonun ilk saniyelerindeki vaatle aynı), açıklama (2-3 cümle + serinin diğer bölümleri),
5-8 hashtag. Kapak için kaynak videodan en iyi 3 kareyi seç (vlogkit thumbs) ve 3-5 kelimelik yazıyla 3 kapak yap;
YouTube'un Test & Compare aracında denenecek 3 başlık + kapak eşleşmesini öner.
```

Not: Kapak yazısı 1,5 saniyede okunmalı, en fazla 3-5 kelime. Kapak ve başlığın vaadi videonun açılışıyla aynı olmalı. `vlogkit thumbs` kareleri netlik, renk ve pozlamaya göre seçer, yazıyı görüntünün sakin tarafına koyar. Hikâyeye göre seçilen kareden tasarlanmış kapak kurar (yüze ışık, yazı yeri, rozet) ve üçünü telefonda göründüğü boyutlarda (168 px'e kadar), süre etiketiyle yan yana gösterir. İstersen seni bir kareden kesip (Apple Vision) başka bir manzaranın önüne koyar, başını hafifçe büyütür. Temaya uygun efekt de ekler: soğuk suyla ilgili bir kapakta köşelere kırağı ve buz küpü gibi.

#### Teslim öncesi kontrol

Ne zaman: Yüklemeden hemen önce, her seferinde.

```text
<çıktı dosyası> için teslim kontrolü yap: vlogkit review (kanca, tempo, bitiş, ses, emoji; vaat: "<kelimeler>")
ve vlogkit check --cuts (çözünürlük, kare sayısı, -14 LUFS / -1 dBTP, kesme hizası).
"!" maddelerini düzelt ya da neden kalması gerektiğini söyle.
```

### vlogkit'i geliştir {#sistem}

#### Yeni özellik ekle

Ne zaman: Bir iş vlogkit'te olmayan bir yetenek gerektirdiğinde.

```text
vlogkit'e <özellik> ekle (ör. whisper'dan otomatik karaoke / DaVinci export / timeline.yaml).
Kütüphaneye genel bir API olarak koy, bir projede kullan, test yaz, docs/workflow.md ve README'yi güncelle,
CHANGELOG'a yaz, sürümü artır, commit + push et.
docs/prompts.md'yi ve prompt artifact'ini yeni yeteneğe göre güncelle.
```

#### Öğrenileni kalıcı hale getir

Ne zaman: Bir işte yeni bir tuzakla karşılaşıldığında.

```text
Bu işte karşılaştığın <sorun>u vlogkit'e kalıcı olarak işle: docs/workflow.md'deki "Tuzaklar" listesine ekle,
mümkünse bir regresyon testi yaz, commit + push et.
```

#### Prompt rehberini güncelle

Ne zaman: vlogkit'e yeni bir şey eklendikten sonra.

```text
vlogkit'in son haline göre docs/prompts.md'yi gözden geçir: yeni komut ve özellikleri ekle, eskiyenleri düzelt,
sürüm ve tarihi güncelle. Prompt artifact'ini aynı adrese yeniden yayınla, commit + push et.
```

#### Öneriyi uygula

Ne zaman: Claude bir işin sonunda "Öneri:" satırı yazdığında ve fikri beğendiğinde.

```text
Az önce önerdiğin <öneri>yi vlogkit'e ekle. Kütüphaneye genel bir API olarak koy, bu işte kullan, test yaz,
docs/workflow.md, README ve CHANGELOG'u güncelle, sürümü artır. Prompt rehberini ve artifact'i güncelle, commit + push et.
```

## Ekler {#ekler}

Herhangi bir prompt'un sonuna ekleyebileceğin kısa talimatlar. Tıklayınca kopyalanır.

- Önce plan göster, onaylamadan derleme.
- Teslimden önce eleştirmen turu da yap.
- Onaylı versiyona dokunma, yeni varyant aç.
- Müziğin zamanlamasına dokunma.
- Meme dozu: düşük.
- Hook: sonucu önce göster.
- Altyazı yoğunluğu: sadece önemli anlar.
- Emoji kullanma.
- Oranı ve çözünürlüğü koru: kırpma, büyütme yapma.
- 4K kaynağı 4K teslim et.
- Kapanış planını 2-3 sn uzat: ara karelerle yavaşlat, karanlığa indir, müzik siyahta bitsin.
- Boşlukları ve dolgu kelimeleri kes (önce listele).
- Önce ham çekimi logla, her planın ne anlattığını tabloda yaz.
- Ham çekimi yerel video modeliyle de logla (--vlm; ham süreye yakın sürer).
- Konuşma sesini temizle (rüzgâr, uğultu).
- Bir-iki yerde efekt kullan: hız rampası, whip pan, glitch ya da freeze.
- Short'un sonunu başına bağla (loop).
- Kapak ve 10 başlık da hazırla.
- Titrek koşu planlarını sabitle (sadece ham görüntü).
- Yabancıların yüzlerini ve plakaları bulanıklaştır.
- Siyah perdeyi değiştir: stüdyo ışığı.
- Denemeler arasında mimiğe göre en iyisini seç.
- Konuşmayı müzikten ayır, müziği değiştir.
- Süre en fazla 45 sn olsun.
- Telifli klip ya da müzik kullanma.
- Sesi dinleyemediğin için ölçümleri (LUFS) tabloyla raporla.
- Bitince kritik anların kontak sayfasını göster.
- Yayın paketini de hazırla (başlık, açıklama, hashtag).
- Commit + push et.

## Bilinmesi gerekenler {#sinirlar}

- **Görme ve duyma:** Claude sesi duyamaz, videoyu gerçek zamanlı izleyemez. Kontak sayfası, spektrogram, LUFS ölçümü ve transkriptle çalışır. Son dinleme her zaman senden.
- **Telif:** Film, dizi, spor ve viral kullanıcı videoları Content ID ile yakalanır. Viral klip gerekiyorsa YouTube uygulamasında "Remix > Cut" ile 1-5 sn'yi sen eklersin; lisans almak (Jukin, ViralHog, Storyful) ücretli. Ayrıntı: `docs/shorts.md`.
- **Hesap gerektiren işler:** YouTube Studio ve Audio Library'ye Claude giremez. Müziği indirip dosya yolunu ver.
- **DaVinci Resolve (ücretsiz sürüm):** `vlogkit resolve` bir FCPXML ve medya klasörü üretir; Resolve'da File > Import > Timeline ile açarsın. Betik çalıştırmak gerekmez (Resolve 21.1 ücretsiz sürümde Python betiklerini kaldırdı).
- **Yol haritası:** Ham kliplerden otomatik kurgu ve YouTube istatistiklerinden öğrenme vlogkit'in yol haritasında. İlk ihtiyaçta Claude bunları vlogkit'e ekleyerek ilerler.
- **Viral şarkıyla Reels:** Telifli şarkı videoya gömülmez; müziksiz dosya yüklenir, şarkı Instagram'dan eklenir. Kurgu şarkıya göre yapıldığı için `.instagram.txt` başlangıç saniyesini ve drop kesmesinin zamanını söyler. Meta'nın Edits uygulamasında ses dalgasıyla hizalamak en kolayı.
- **İzlenme süresi kontrolü:** Her teslimde Claude `vlogkit review` çalıştırır: kanca, tempo, bitiş, ses, emoji. Loop ve kanca A/B denemesi isteğe bağlıdır, sadece istersen yapılır.
- **Müzikli videoda konuşma:** Whisper müziğin altındaki konuşmayı zor ayırır, dil tespitini şaşırır ve "中文字幕", "Altyazı M.K." gibi satırlar uydurur. Claude kısa pencerelerle birkaç ayarda dener, sadece tutarlı satırları kullanır ve çözemediği yerleri söyler. O satırları sen verirsen eklenir.
- **Sonradan elle düzenleme:** Altyazı ve grafikler final videoya gömülüdür, kalite için öyle kalır. `vlogkit resolve` aynı kurgunun katmanlı bir kopyasını DaVinci Resolve'a verir: her plan, her altyazı ve grafik ayrı klip; sesler ayrı izlerde; altyazıların düzenlenebilir metin kopyası üstte kapalı durur. Bir kelimeyi değiştirmek için ya o metni açarsın ya da Claude'a söylersin, sadece değişen adım yeniden derlenir.
- **Geliştirme önerileri:** Claude bir işte vlogkit'e eklenmeye değer bir şey görürse son mesajda tek satır "Öneri:" yazar, kendiliğinden eklemez. Beğenirsen "Öneriyi uygula" prompt'uyla ya da "Öneriyi uygula" diye yanıt vererek ekletirsin.
- **Oran ve kalite:** Claude kaynağı kırpmayı ya da büyütmeyi planda ayrı madde olarak yazar. Düşük çözünürlüklü kaynakta önce sorar. İstemiyorsan "Oranı ve çözünürlüğü koru" ekini kullan.
- **Codex:** Stüdyoda "⋯ > Ajan" menüsünden Claude Code yerine Codex (ChatGPT aboneliği) seçilebilir. Prompt'lar aynı. Güvenli modda Codex commit atamaz (`.git` sandbox'ta salt okunur). Commit için "Tam yetki" gerekir.
- **Kurulum ve güncelleme:** vlogkit başka bir Mac'e tek satırla kurulur (`KURULUM.md`). Kurulu kopyada yeni sürüm çıkınca Stüdyo'nun sol altında "Güncelleme var" yazar; projeler ve videolar güncellemeden etkilenmez.
- **Lisanslar:** Videoda kütüphaneden müzik ya da efekt varsa videonun yanında `.lisans.md` dosyası ve Stüdyo'nun sağ üstünde Lisanslar kartı olur. Platform telif talebi gönderirse "İtiraz metnini kopyala" yeter.
- **Yerel video modeli:** Ayarlar > Yerel video modeli. Mac'in belleğine uyan boyutu (2B, 4B, 9B) kur ve seç; şart değil.
- **Zaman çizelgesi:** Sıkışıksa +/−, ⌘ + tekerlek ya da çift tıkla yakınlaş; üstteki ince şeritte pencereyi sürükle.
- **Eforu değiştirmek:** Açık bir işte yazma kutusunun altındaki "Efor" seçimi iş çalışırken de değişir; Claude bir sonraki adımda, Codex sonraki turda alır.
- **İş sürerken yazmak:** Claude Code çalışırken yazdığın mesaj hemen iletilir; Claude onu bir sonraki adımda alır, işi bitirmeyi beklemez. Codex'te mesaj sıraya girer ve adım bitince gider.
- **Mesajı düzenlemek:** Gönderdiğin bir mesajın yanındaki "Düzenle" ile değiştirip gönderirsin; sonrası ayrılır ve konuşma oradan devam eder. Dosya değişiklikleri geri alınmaz, Claude'a hangi dosyaların değiştiği söylenir.
- **Müzik seçimi:** Claude müziği dinleyemez; telifsiz müzik gerektiğinde 3-5 aday çıkarıp sahnenin altında dinletir, seçimi sen yaparsın.
- **Disk:** Derlemeler büyük ara dosyalar yazar (4K'da 4 dakikaya ~27 GB). "⋯ > Ara dosyalar"dan eskileri temizlersin ya da 7/14/30 gün seçersin; teslim videoları kalır. Yer yetmeyecekse derleme hiç başlamaz.
- **Geçmiş:** İşler stüdyo kapansa da kalır, varsayılan olarak hiç silinmez. "⋯ > Geçmiş" menüsünden 3, 7 ya da 30 gün seçilebilir. Sabitlenen işler hiç silinmez. Silinen işin özeti video klasöründeki `VLOGKIT-NOTLAR.md` dosyasına yazılır.
- **Emoji:** Shorts altyazılarında en fazla üç altyazıda bir emoji olur, uzun videonun konuşma altyazısında hiç olmaz. Kural aşılırsa derleme uyarı verir. Hiç istemiyorsan "Emoji kullanma." ekini kullan.
- **Arka plan ve mimik:** `background` kişiyi Apple Vision ile ayırır; hızlı el hareketinde kolun çevresinde koyu kenar, ince saç tellerinde düzleşme olabilir. `face` yüzün yakın planını yerel modele gösterir; ifadeyi görür ama sesi duymaz, anların saniyeleri yaklaşıktır.
- **Zaman çizelgesi ve kelimeden kesme:** Stüdyo'da her videonun altında planlar ve yazılar izler hâlinde durur. Bir ana tıklayıp "Bu ana yorum" dersen mesaja zaman ve plan eklenir; "Kelimeler"den kesilecek kelimeleri seçip "Seçileni kes" dersin. Değişikliği Claude projede yapar ve yeniden derler.
- **Kurgu ayarı:** Yazma kutusundaki "Kurgu" çipiyle kesim sertliğini (temkinli, dengeli, sert), altyazı/müzik/ses efektini ve kısa bir notu bir kez seçersin; her yeni işe eklenir, Claude planın başında teyit eder.
- **Gizlilik:** "Yabancıların yüzlerini bulanıklaştır" dersen Claude yüzleri Apple Vision ile bulup takip eder, senin yüzünü açık bırakır. Kalabalıkta şapkalı, gözlüklü ya da yandan görünen yüzlerin bir kısmı kaçabilir; Claude sonucu sayfada kontrol eder, kaçanları elle ekler.
- **Ham çekimde arama:** "Göl kenarında ateş yaktığımız an" gibi bir anı tarif etmen yeterli. Claude ham klasörün kaydında arar (`vlogkit find`), bulduklarının karelerine bakıp seçer.
- **Tarif:** Beğendiğin bir kurguyu onayladığında Claude onun tarifini (açılış hızı, plan ritmi, yazı stili, efektler) `recipes/` altına yazar. Sonra "Kaçkar Short 01 gibi yap" demen yeter.
- **Proje hafızası:** Her projede bir `NOTES.md` var: kararlar, bu videoya özel tercihlerin ve açık işler. Yeni bir sohbette Claude önce onu okur ve geçen oturumu tek cümleyle özetler; "geçen sefer ne demiştik" diye anlatman gerekmez.
- **Öz-denetim:** Teslimden önce Claude her kesmeyi kare kare kontrol eder (artık plan, siyah kare, donuk görüntü, ses sıçraması). Yeni kurgularda ayrı bir eleştirmen ajanı videoyu baştan izler. En fazla 3 düzeltme turu yapılır; çözülemeyenler son mesajda "Açık kalanlar" diye yazılır.
- **Özel adlar:** Yer ve kişi adları `assets/vocab.txt` dosyasında; altyazıda yanlış yazılan bir ad görürsen ekletmen yeterli.
- **Görüntüler:** Ham görüntüler repoya girmez. Projeler `~/yt-vlogs` altındaki dosyalara bakar, çıktılar da oraya yazılır.

## Dolu örnek: Kaçkar Short 02 {#ornek}

Sıradaki video için iskeletin gerçek bilgilerle doldurulmuş hali. Bilgiler `vlogkit analyze` raporundan.

```text
KLASÖR:   ~/yt-vlogs/kackar
KONU:     Kaçkar yarışı sabahı start alanına varış. "Geldik, alandayız"; hava ~12 derece; sponsor çadırları ve parkur haritası var.
HEDEF:    Short (serinin 2. bölümü)
KAYNAK:   Kackar_Short_02.mp4 (müzikli kurgu, konuşma var), Full Copy V1.3.mp4 (uzun kurgu, ek sahneler için)
TARZ:     kackar-short01 v1 ile aynı tasarım dili
KISITLAR: müziğin zamanlaması aynı kalsın; konuşmalara karaoke altyazı; ses -14 LUFS (kaynak +1.5 dBTP'de clipping yapıyor); bitiş kartı Bölüm 3'e
SÜREÇ:    önce plan tablosu, onaylayınca derle. Proje adı: kackar-short02
```
