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
- **Biriken sahne:** video sonunda başta olmayan, eksiksiz bir yapı var (önce/sonra).

## Anlatım kalıbı (55-80 sn, 140-190 kelime, 14-28 cümle)

1. **Açılış (ilk 3 sn):** önce sonuç: bitmiş yapı çalışırken (pompadan su fışkırır, havuzda
   balık yüzer) tek cümle: "Bu kuyu bahçene bedava su verir. Peki nasıl yapılır?" Sonraki beat
   `"remove": "all"` ile boş bahçeye döner ve inşa başlar: "Bahçene bir çukur kazarsan…".
   Kaydırmayı durduran şey ilk karede görünen ödüldür, toprak duvar değil.
2. **Turlar (5-7 kez):**
   - `Ama` + sorun (tek cümle, somut, gerçek): "Ama ilk yağmurda duvarlar içine çöker."
   - `O yüzden` + çözüm, sahneye eklenen şey: "O yüzden duvarları taşla örersin."
   - Bazı turlarda isim: "Buna ___ denir." (2-4 kez; en ilginç terimler için). O anda terim
     ekranda etiket olarak belirir: `{"kind": "sign", "id": "etiket1", "text": "YERALTI SUYU",
     "stand": false, "z": 0, "size": 0.3, "color": "#ffffff", "text_color": "#111111",
     "at": [x, -0.1, z]}` (kesitin önünde, gösterdiği şeyin yanında); sonraki beat `remove` eder.
   - Gerekirse neden: "Çünkü …" (bilgi cümlesi, sayıyla).
3. **Zaman dönüşü (sondan önce):** "Ama sonra kış gelir…" (mevsim, yıllar, fırtına).
4. **Kapanış:** "Tebrikler, artık bir ___ var." ya da bir yorum sorusu.

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
    malzemeler water, green_water, murky, sand, gravel, stone, concrete, asphalt, soil, clay,
    liner (ince kaplama), ice, snow, sludge, oil, lava, foam. `shell: true` duvarlara `t` kalınlığında
    kaplama (taş örgü, beton). Dolarak gelmesi için: `"scale": [1, 1, 0.01]` ve
    `"anim": [{"at": "kelime", "scale": [1, 1, 1], "dur": 1.2}]` (katman tabandan yükselir).
  - Diğer: pipe (`path`, `r`), tank (filtre, depo, pompa: `text`), fish, lily_pad, rock, plant,
    arrow (sorunun yönünü gösteren beyaz ok: `"color": "#ffffff"`), sign, water_jet.
- **Sorun anları:** ok + efekt: crack (çatlak), debris (çöken toprak), pour (sızan/akan su), smoke,
  flood, shake. Renk değişimi (water → green_water / murky) aynı id'li layer ile.
- **Kamera:** tek mekân, sert kesme yerine **her 2-3 sn yeni açı** (`shots` + `cue`). Kesit hep
  görünür: açı -50..50 arası, arkadan asla.
  - Genel: `{"frame": "wide", "on": "kuyu", "angle": -20, "tilt": 0.6, "zoom": 0.6, "move": "push"}`
  - Yandan: `angle` 35-45, `move: "orbit"`; yakın kesit: `frame` medium/close, `on` çukur ya da
    `[x, 0, z]`; tepeden plan: `frame: "top"`.
  - Yeni eklenen şeyi yeni açıyla göster; aynı açı iki plan üst üste gelmez.
  - Her 3-4 planda bir geniş plan (bahçe, ev ve kesit birlikte): izleyici yerini kaybetmesin.
  - Yer altındaki bir şeyi (boru, kök, tünel) yakından göstermek için kamerayı kesitin önüne
    indir: `tilt` eksi (ör. -2.4); yoksa çimin üstünden bakar ve göremez.
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

- [ ] İlk karede bitmiş yapı çalışıyor (ödül), ilk cümlede soru; sonra `remove: all` ile inşa.
- [ ] Her "Buna ___ denir" anında terim etiket olarak ekranda.
- [ ] Her beat sahneye bir değişiklik getiriyor (`3d plan` çıktısında beat başına yeni eşya ya da efekt).
- [ ] 5-7 "Ama / O yüzden" turu, 2-4 "Buna ___ denir".
- [ ] Sorunlar gerçek, kaynaklı (NOTES.md).
- [ ] Hiçbir plan 3 saniyeden uzun değil; komşu planların açısı farklı.
- [ ] Kesit hiçbir planda arkadan ya da yandan kaybolmuyor.
- [ ] Son kare bitmiş yapıyı gösteriyor.

Başlangıç: `uv run vlogkit 3d new <proje> --format kesit` çalışılmış örnekle (kuyu) açar.
