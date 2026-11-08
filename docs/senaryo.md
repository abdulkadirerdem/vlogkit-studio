# Senaryo araştırması: 3B "Peki ya?" kanalı

Stüdyo'daki **Senaryolar** sayfası buradan beslenir. Bir "Senaryo araştır" işi geldiğinde video
üretme: viral olabilecek fikirleri araştır, puanla, sahne sahne yaz, her birini
`projects/_senaryolar/<id>.json` olarak kaydet. Kullanıcı birini seçince ayrı bir 3B işi açılır
(`docs/3d.md`); o iş senaryodaki her cümleyi ekranda bir olaya çevirir.

## 1. Araştır (web)

- **Neyin tuttuğuna bak:** YouTube Shorts, TikTok ve Instagram Reels'te "what if", "peki ya",
  "ne olurdu" videoları. Türkçe ve yabancı kanallar; son 6-12 ayda en çok izlenenler, izlenme ve
  yorum sayısıyla. Hangi konu aileleri tekrar tekrar milyonlara ulaşıyor (vücut, uzay, para,
  hayvanlar, doğa olayları, gündelik hayatın kuralları bozulursa, tarih tersine dönse)?
- **Boşluğu bul:** çok izlenen ama Türkçesi yok ya da kötü yapılmış konular; gündemde olan bir
  olaya bağlanabilen sorular (yeni bir keşif, bir rekor, bir haber).
- **Gerçekleri topla:** her senaryonun sayıları ve sonuçları kaynaklı olsun (NASA, bilimsel
  makale, resmi istatistik, güvenilir ansiklopedi). Kaynakları `sources` alanına yaz. Kurgu
  kısmı serbest, sayılar gerçek.
- `projects/_senaryolar/` içindeki mevcut senaryolara bak: aynı fikri tekrar yazma.

## 2. Ele ve puanla

Her aday için 1-10 arası beş puan ver; sadece ortalaması **7.5 ve üstü** olanları yaz:

| Puan | Soru |
|---|---|
| `merak` | Başlığı gören kaydırmadan önce "ne olur ki?" diye durur mu? Soru tek cümlede anlaşılıyor mu? |
| `tirmanis` | Olaylar giderek büyüyor mu (ev → sokak → şehir → dünya → uzay)? Her 5-8 saniyede yeni bir basamak var mı? |
| `gorsel` | Her cümle ekranda net bir olay olarak gösterilebiliyor mu? Kitte (`uv run vlogkit 3d kit`) karşılığı var mı, yoksa Blender'da yapılabilir mi? |
| `hesap` | Şaşırtıcı ama doğru sayılar var mı (sayaç, oran, süre)? |
| `yorum` | Sonunda insanlar tartışır, arkadaşını etiketler, "ya şöyle olsaydı" der mi? |

Ele: platform kurallarına takılabilecekler (gerçek kişiler hakkında iftira, intihar/kendine zarar,
çocuklara yönelik risk, nefret), görselleştirilemeyecek kadar soyut olanlar, sayıları
doğrulanamayanlar.

## 3. Yaz: yapı

- **Süre:** 40-55 saniye, 8-14 sahne (`beats`). Bir sahne = bir anlatım cümlesi (≈3-5 sn).
- **Açılış (`hook`):** ilk 2 saniyede sorunun kendisi ve şaşırtıcı ilk görüntü. "Merhaba" yok,
  giriş yok.
- **Tırmanış:** her sahne bir öncekinden büyük. Ortada bir ters köşe (beklenmeyen sonuç).
- **Her cümle bir olay:** `visual` alanı "karakter duruyor" değil, ekranda ne olduğunu anlatır:
  kim ne yapıyor, hangi nesne kırılıyor/uçuyor/doluyor, kamera nereden bakıyor, hangi sayaç
  artıyor. Anlatımı görüntü göstermeli: telefon ekranında etiket, televizyonda son dakika bandı,
  gazete manşeti, güvenlik kamerası görüntüsü, harita gibi anlatım nesneleri iyi çalışır. Yaklaşık
  her 2 saniyede görüntü değişsin (bir cümlede 1-3 plan): `visual` alanında planları "→" ile
  sırala ve kesmenin olacağı kelimeyi yaz ("geniş: su klozetten taşar → 'herkes' kelimesinde
  sokakta kaçan kalabalık"). Kitin dili (`docs/3d.md`): efektler (çatlak, kırılan cam, patlama,
  duman, ateş, su baskını, para yağmuru, ikiye bölünme), görünümler (güvenlik kamerası, canlı
  haber, telefonda viral video, eski film, gece görüşü), kalabalık, elden ele geçen eşyalar,
  açılan kapı, uçan karakter. Bunlarla gösterilemeyecek bir olayı seçme.
- **Sayaç (`counter`):** hikâye bir sayıyla ilerliyorsa (gün, insan, metre, lira) sahnelere değer ver.
- **Efekt (`fx`):** çatlak, su taşması, kıvılcım, duman, kırılma, patlama, uçuş, ölçek gösterimi…
- **Kapanış (`ending`):** sonucu tek cümleyle bağla ve yorum sorusu sor ("Sen olsan ne yapardın?").
- **Sonraki video (`next_teaser`):** bir sonraki "Peki ya?" sorusunu kısaca ima et.
- **Dil:** konuşma dili, kısa cümleler, Türkçe. Sayıları rakamla yaz (seslendirme okur; "5. gün"
  "beşinci gün" okunur). Kanal sesi iki ünlü arasındaki "ğ"yi bazen yutar ("doğrusu" → "dorusu"):
  cümlenin vurgulu ilk kelimesini böyle bir kelimeyle başlatma ("Doğru olan şu:" gibi kur).
- **Yayın metni:** `titles.youtube` (3 alternatif, 60 karakter altı), `titles.instagram`,
  `titles.tiktok`, `hashtags` (5-8, `#pekiya` dahil).

## 4. Dosya

Format: `"format": "pekiya"` (varsayılan), `"kesit"`, `"hayatta"`, `"oyun"` ya da `"olcek"`;
formatın belgesindeki kalıba göre yaz (`docs/formats/<format>.md`; cümle sayısı formata göre:
pekiya 6-16, kesit 12-22, hayatta 8-16, oyun 6-12, olcek 7-14). Kimlik (`id`) dosya adıyla aynı: küçük harf, rakam, tire. `status` `"yeni"`, `created` bugünün
tarihi, `project` `null`.

```json
{"id": "herkes-ayni-anda-ziplasa", "title": "Peki ya herkes aynı anda zıplasaydı?",
 "hook": "8 milyar insan aynı saniyede zıplıyor.", "logline": "...", "duration_s": 48,
 "language": "tr", "scores": {"merak": 9, "tirmanis": 8, "gorsel": 9, "hesap": 8, "yorum": 8},
 "why": "Bu konu ailesindeki videolar ... izlenme aldı; Türkçesi yok.",
 "sources": [{"title": "...", "url": "https://..."}],
 "counter": {"label": "ZIPLAYAN İNSAN"},
 "beats": [{"say": "...", "visual": "...", "counter": "8.000.000.000", "fx": "yer sarsıntısı"}],
 "ending": "...", "next_teaser": "...",
 "titles": {"youtube": ["...", "...", "..."], "instagram": "...", "tiktok": "..."},
 "hashtags": ["#pekiya", "..."], "status": "yeni", "created": "2026-11-02", "project": null}
```

Her dosyadan sonra `uv run vlogkit 3d senaryo-kontrol <id>` (hepsini birden: `--tum`) çalıştır; sorun kalmayana kadar
düzelt. Son mesajda kısa bir liste ver: başlık, toplam puan, neden tutar (tek cümle). Kullanıcı
seçimini Senaryolar sayfasından yapar.

## 5. Seçildiğinde

Senaryolar sayfasındaki **Bu senaryoyu çek** düğmesi senaryoyu "seçildi" yapar ve bir 3B işi açar.
O iş `docs/3d.md`'yi izler, başlarken `uv run vlogkit 3d senaryo-durum <id> uretiliyor --proje <proje>`,
video teslim edilince `uv run vlogkit 3d senaryo-durum <id> uretildi` çalıştırır.
