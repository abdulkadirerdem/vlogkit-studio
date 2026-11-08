# Format: Kesitten inşa (`"format": "kesit"`)

Bir bahçe, pasta gibi kesilmiş bir blok: üstte çim ve ev, önde toprak katmanları. Gündelik bir şey
(havuz, kuyu, yol, bodrum...) bu kesitte adım adım inşa edilir. Her cümle ya bir sorun gösterir ya
da çözümü sahneye ekler. Bu yapıdaki bir İngilizce sayfa ilk 48 videosunda 58,6 milyon izlenme aldı
(TikTok, Ekim 2026); biz formatı kendi kitimiz ve Türkçe anlatımla yeniden kuruyoruz. Konuyu,
metni ve görüntüyü kopyalamıyoruz.

## Neden tutar

- **Açık döngü:** her "Ama…" yeni bir soru açar; izleyici çözümü görmek için kalır.
- **Ödül:** "Buna ___ denir." Bilmediği bir kelimeyi öğrenmek, yorumlarda "bunu bilmiyordum".
- **Kesit:** yerin altını görmek tatmin edici; değişiklik bir saniyede okunur.
- **Doğal katmanlar baştan yerinde:** yeraltı suyu bandı, kaya, kil gibi zeminin kendisi olan
  katmanlar inşanın ilk beat'inde (`remove: all`'dan hemen sonra) eklenir, bahsedildiği cümlede
  değil. Bahsedildiği cümlede ok, `term` kartı, kamera ile **vurgulanır**; sonradan bir anda
  beliren bir bant kesme hatası gibi görünür.
- **Biriken sahne:** video sonunda başta olmayan, eksiksiz bir yapı var (önce/sonra).

## Anlatım kalıbı (45-65 sn, 110-160 kelime, 12-22 cümle)

1. **Açılış (ilk 3 sn):** önce sonuç: bitmiş yapı çalışırken (pompadan su fışkırır, havuzda
   balık yüzer) tek cümle: "Bu kuyu bahçene bedava su verir. Peki nasıl yapılır?" Sonraki beat
   `"remove": "all"` ile boş bahçeye döner ve inşa başlar: "Bahçene bir çukur kazarsan…".
   Kaydırmayı durduran şey ilk karede görünen ödüldür, toprak duvar değil.
   **İlk plan bir dalış:** `"move": "dive"`, `"on"` yer altındaki ödül (kuyunun suyu),
   `"from"` yüzeyde çalışan şey (pompa): kamera bahçeyi gösterip tek hareketle kesitin içinden
   ödüle iner. Başlık (`hook`) inişle birlikte gelsin: `"hook": {"text": "...", "at": 1.4}`.
2. **Turlar (4-6 kez):**
   - `Ama` + sorun (tek cümle, somut, gerçek): "Ama ilk yağmurda duvarlar içine çöker."
   - `O yüzden` + çözüm, sahneye eklenen şey: "O yüzden duvarları taşla örersin."
   - Bazı turlarda isim (1-3 kez, en ilginç terimler): cümlenin içinde, ayrı bir beat değil:
     "Çünkü taşların arasında [yeraltı suyu] denen bir su katmanı var." O kelimede terim
     ekranda büyük sarı bir kart olarak belirir: `"term": {"text": "YERALTI SUYU", "at":
     "yeraltı"}`. Sahneye 3B tabela koyma: küçük ve düz kalır, okunmaz.
   - Gerekirse neden: "Çünkü …" (bilgi cümlesi, sayıyla).
3. **Zaman dönüşü (sondan önce):** "Ama sonra kış gelir…" (mevsim, yıllar, fırtına).
4. **Kapanış:** "Tebrikler, artık bir ___ var." ve numaralı bir yorum sorusu: "Sence ilk hangisi
   bozulur?" Soru kelimesinde ekranda 2-4 numaralı seçenek belirir, izleyici yoruma yalnız
   numarayı yazar (yorum yazmak bir tuş kadar kolay olunca yorum gelir):
   `"choices": {"at": "Sence", "title": "İLK HANGİSİ BOZULUR?", "items": ["TAŞ DUVAR", "POMPA",
   "BORU"], "ask": "NUMARASINI YORUMA YAZ"}` ve okunsun diye o beat'e `"hold": 2.2`. Seçenekler
   videoda inşa edilen parçalar olsun (izleyici hepsini gördü, fikri var).

Kurallar:
- İkinci tekil şahıs, geniş/şimdiki zaman, kısa cümleler (4-12 kelime). Sakin ama hızlı.
- Her sorun gerçek ve doğrulanmış (NOTES.md'ye kaynak); sayılar rakamla yazılır.
- Her cümle ekranda bir değişiklik. Görüntüsü olmayan cümleyi yeniden yaz.
- Ünlem azdır; anlatım sakin, merak cümlenin yapısından gelir.

## Ekranda

- **Mekân:** `"set": "cutaway"` (ilk beat'te; sonrakiler taşır). `set_opts.season`: summer |
  autumn | winter (kış dönüşünde çim karla örtülür, gökyüzü griye döner).
- **Biriken sahne:** bu formatta `carry` açıktır: her beat önceki beat'lerin eşyalarıyla başlar
  (hareketleri bittiği yerde). Bir beat yalnızca **eklediğini ya da değiştirdiğini** yazar; aynı
  `id` ile yazılan eşya eskisinin yerine geçer (ör. suyun rengini değiştirmek için aynı id'li
  layer); `"remove": ["id"]` çıkarır, `anim` içinde `hide` kaybeder.
- **Kazı ve dolgu:**
  - `{"kind": "pit", "id": "kuyu", "shape": "box", "size": [1.4, 1.4, 5.0], "at": [0, 0]}`:
    şekiller bowl (havuz çanağı), box, shelf (bitki rafı olan havuz), trench (hendek, yol), tunnel
    (yatay tünel: `z` derinlik). `at` y = 0 çukurun ortasını kesite koyar: yarısı kesilmiş görünür.
  - `{"kind": "layer", "id": "su", "pit": "kuyu", "material": "water", "from": -5.0, "to": -3.6}`:
    malzemeler water, green_water, murky, aquifer, sand, gravel, stone, concrete, asphalt, soil,
    clay, liner (ince kaplama), ice, snow, sludge, oil, lava, foam. Bir çukur bu katmanın içinden
    geçiyorsa (yeraltı suyu bandının içinden geçen kuyu) `"except": ["kuyu"]`: katman o çukurda
    boş kalır, iki dolgu aynı yeri kaplamaz.
  - **Su kendiliğinden canlı görünür:** water / green_water / murky yüzeyde açık, dipte koyu,
    içinden aydınlanan bir gövde; üstünde oynayan ışık desenleri (kostik), yüzeyde parlak bir
    çizgi. Temiz suda kabarcıklar yükselir (`"bubbles": false` kapatır), bulanıkta kum zerreleri
    süzülür. Renk vermek gerekmez; verilirse (`color`) yüzey o rengin açığı, dip koyusu olur.
  - **Yeraltı suyu bandı:** `"material": "aquifer"`: yuvarlak taşlar ve aralarında parlayan
    mavi su. Kuyu, kaynak, sondaj konularında bunu kullan; gri çakıl ya da düz mavi bant değil. `shell: true` duvarlara `t` kalınlığında
    kaplama (taş örgü, beton). Dolarak gelmesi için: `"scale": [1, 1, 0.01]` ve
    `"anim": [{"at": "kelime", "scale": [1, 1, 1], "dur": 1.2}]` (katman tabandan yükselir).
  - Diğer: pipe (`path`, `r`), tank (filtre, depo: `text`, `material`: concrete | wood | rust |
    brick), hand_pump (`"pump": {"at": "kelime", "dur": 2}` ile kolu iner kalkar), fish, lily_pad,
    arrow (sorunun yönünü gösteren beyaz ok: `"color": "#ffffff"`), sign, water_jet.
  - Gerçek modeller (kütüphane 3): bucket (kova; `"rope": [x, y, z]` ile ipten sarkar, ip onu
    izler), barrel, spade, pickaxe, watering_can, compost_bags, crate, ladder, stump, boulder,
    rocks, roots, grass_tuft, utility_box, manhole_cover, planter_box.
- **Sorun anları gerçekten olur:** `collapse` (çukurun duvarları çöker: topraklar kopup düşer, dip
  dolar, toz kalkar; `target`: pit id, `to`: dolgunun üstü), `burst` (boru/tank patlar: çatlak,
  fışkıran su, sızıntı; `pos`), crack, debris, pour, smoke, flood, shake. Sorun cümlesini bir
  efekt ya da bir hareket olmadan bırakma: altyazıda kalan sorun izleyiciyi tutmaz. Format her
  "Ama…" cümlesinin son kelimesine (fiil: "çöker", "donar") kendiliğinden kısa bir kamera
  sarsıntısı ve çarpma sesi koyar; işler iyiye dönen bir "Ama" ise (`"Ama toprak 1 metreden
  derinde donmaz."`) o beat'e `"punch": false`. Renk değişimi (water → green_water / murky) aynı id'li layer ile.
- **Sayı olayla birlikte:** kazı, doldurma, maliyet gibi bir miktar büyürken ekranda sayılsın:
  kazı beat'ine `"count": {"from": 0, "to": 6, "unit": "M", "label": "DERİNLİK", "at": "kazarsan",
  "dur": 1.5}` (sayı `dig` efektiyle aynı anda başlar).
- **Görüntü:** kesit mekânı kendiliğinden sığ odaklıdır (konu net, ev ve arka bahçe yumuşak:
  minyatür görünümü), ışığı sıcak ana ışık + serin dolgu. Bir planda her şey net olsun
  istenirse kamerada `"dof": false`.
- **Önce/sonra:** bir sorunun çözüldüğü an (bulanık → berrak, çatlak → onarılmış) tek bakışta
  okunsun: çözümün planına `"wipe": {"labels": ["BULANIK", "BERRAK"]}` yaz. Önceki planın son
  karesi durur, yeni durum sağdan gelir, ikisi ortadan bölünmüş ~1 sn yan yana kalır, sonra yeni
  durum kareyi alır. İki plan **aynı kamerayla** olmalı (aynı `on`, `angle`, `frame`; önceki plan
  orbit ise bitiş açısı), yoksa karşılaştırma okunmaz; planı en az 2 sn tut.
- **Kamera:** tek mekân, sert kesme yerine **her 2-3 sn yeni açı** (`shots` + `cue`). Kesit hep
  görünür: açı -50..50 arası, arkadan asla.
  - Genel: `{"frame": "wide", "on": "kuyu", "angle": -20, "tilt": 0.6, "zoom": 0.6, "move": "push"}`
  - Yandan: `angle` 35-45, `move: "orbit"`; yakın kesit: `frame` medium/close, `on` çukur ya da
    `[x, 0, z]`; tepeden plan: `frame: "top"`.
  - Yeni eklenen şeyi yeni açıyla göster; aynı açı iki plan üst üste gelmez.
  - Her 3-4 planda bir geniş plan (bahçe, ev ve kesit birlikte): izleyici yerini kaybetmesin.
  - Yer altındaki bir şeyi (boru, kök, tünel) yakından göstermek için `"level": true`: kamera
    hedefle aynı yükseklikte, kesite dümdüz bakar. Eksi `tilt` kullanma: aşağıdan yukarı bakan
    kamera evi çarpık ve dev gösterir.
- **Altyazı:** tek kelime, ekranın ortasında (format varsayılanı). Vurgulu kelime `[köşeli]`.
- **Sayaç:** genelde yok. Hikâye bir sayıyla ilerliyorsa (maliyet, derinlik) `hud`.
- **Ses:** sakin bir müzik yatağı; her ekleme `pop`, her sorun `impact` (kelimeye bağlı:
  `{"id": "impact", "at": "çöker"}`). Vuruş kelimenin hemen arkasındaki boşluğa düşer.

## Konu seçimi

Gündelik, herkesin gördüğü ama içini bilmediği şeyler: havuz, kuyu, yol, bodrum, septik çukur,
yağmur suyu deposu, ağaç kökleri, temel, sığınak, tünel, kompost, sulama, şömine bacası, otopark.
Kitte olmayan bir parça gerekiyorsa basit şekillerle (tank, pipe, layer) temsil et; olmuyorsa konuyu
değiştir.

## Kontrol listesi (render'dan önce)

- [ ] İlk karede bitmiş yapı çalışıyor (ödül), ilk plan `dive` ile ödüle iniyor, başlık inişte;
      ilk cümlede soru; sonra `remove: all` ile inşa.
- [ ] En az bir `wipe` (sorunun çözüldüğü an, aynı kamerayla).
- [ ] Son beat'te `choices` (2-4 numaralı seçenek) ve `hold`.
- [ ] Her terim `term` kartıyla ekranda.
- [ ] Zeminin parçası olan katmanlar (yeraltı suyu, kaya) inşanın ilk beat'inden beri sahnede.
- [ ] Her beat sahneye bir değişiklik getiriyor (`3d plan` çıktısında beat başına yeni eşya ya da efekt).
- [ ] 4-6 "Ama / O yüzden" turu, 1-3 "Buna ___ denir"; "Ama" cümlesi en çok 8 kelime.
- [ ] Sorunlar gerçek, kaynaklı (NOTES.md).
- [ ] Hiçbir plan 3 saniyeden uzun değil; komşu planların açısı farklı.
- [ ] Kesit hiçbir planda arkadan ya da yandan kaybolmuyor.
- [ ] Son kare bitmiş yapıyı gösteriyor.

Başlangıç: `uv run vlogkit 3d new <proje> --format kesit` çalışılmış örnekle (kuyu) açar.
