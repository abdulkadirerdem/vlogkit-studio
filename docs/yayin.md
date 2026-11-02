# Yayın paketi: YouTube Shorts, Instagram Reels, TikTok

Bitmiş bir dikey video üç platforma elle yüklenir; platform API'si ve uygulama onayı yok. Senin
işin metinleri ve kapakları izlenmeyi en yükseğe çıkaracak şekilde hazırlamak. Stüdyo videonun
altındaki **Paylaş: YouTube / Instagram / TikTok** düğmeleriyle her platformun metnini Kopyala
düğmeleriyle, kapağı ve yükleme sayfasını gösterir; kişi videoyu sürükler, yapıştırır, paylaşır.

## Akış

1. `uv run vlogkit yayin <video.mp4> --taslak`: paket yoksa taslak yazar. Video bir senaryodan
   üretildiyse (`projects/_senaryolar/`) senaryonun başlıkları, etiketleri, açılışı ve kapanış
   sorusu taslağa gelir; senaryo yoksa alanlar boş gelir.
2. Videonun açılışına bak (ilk 2 saniye, anlatımın ilk cümlesi: `<video>.anlatim.txt`) ve paketi
   aşağıdaki kurallarla yaz: `<video>.yayin.json`.
3. Kapak: `uv run vlogkit yayin-kapak <video.mp4> --text "3-5 KELİME"` (3B videoda kare verilmezse
   sayacın en büyük olduğu an seçilir; başka bir an için `--at SN`). Kapağa Read ile bak: yazı
   okunuyor mu, ana olay görünüyor mu. Gerekirse başka bir kareyle tekrar et.
4. `uv run vlogkit yayin-kontrol <video.mp4>`: `!` kalmayana kadar düzelt, `uyarı:`ları ya düzelt
   ya da nedenini yaz.
5. Rapor: üç platformun başlığını/ilk satırını tek tabloda göster; "Çıktılar:" altında kapak
   dosyalarının mutlak yolları.

## Paket

```json
{"video": "ziplama.mp4", "scenario": "herkes-ayni-anda-ziplasa", "cover_text": "HERKES ZIPLARSA?",
 "cover_at": 12.4,
 "youtube": {"title": "Herkes aynı anda zıplarsa Dünya'ya ne olur?",
             "description": "8 milyar insan aynı saniyede zıplıyor...\n\nSen olsan zıplar mıydın?",
             "tags": ["peki ya", "what if", "bilim"], "hashtags": ["#shorts", "#pekiya", "#bilim"],
             "cover": "ziplama.kapak-youtube.jpg"},
 "instagram": {"caption": "8 milyar insan aynı anda zıplasa ne olur? 🌍\n\nSen olsan zıplar mıydın? Yoruma yaz 👇",
               "hashtags": ["#pekiya", "#whatif", "#bilim"], "cover": "ziplama.kapak-instagram.jpg"},
 "tiktok": {"caption": "Herkes aynı anda zıplasa... sonuna kadar izle 😳",
            "hashtags": ["#pekiya", "#whatif", "#keşfet"], "cover": "ziplama.kapak-tiktok.jpg"}}
```

Etiketler (`hashtags`) ayrı tutulur; Stüdyo onları açıklamanın sonuna ekleyip tek parça kopyalatır.
`posted` alanını Stüdyo yazar ("Paylaşıldı" işareti), sen dokunma.

## Kurallar (erişim için)

- **Vaat açılışla aynı:** başlık ve kapak videonun ilk 2 saniyesinde ne görünüyorsa onu vaat eder.
  Videoda olmayan bir şeyi vaat etme (izleyen hemen kaydırır, platform bunu ölçer).
- **Merak boşluğu:** sonucu söyleme, soruyu sor ya da sonucun ölçeğini ima et ("...Dünya'ya ne
  olur?", "3. saniyede her şey değişiyor"). Sayı varsa sayı kullan (8 milyar, 1.000 km/sa).
- **Türkçe, konuşma dili, kısa.** Büyük harfle bağırma yok (kapak hariç); en fazla 1-2 emoji.
- **YouTube Shorts:** `title` ≤ 60 karakter akışta tam görünür (sınır 100). Ana anahtar kelime
  başta. `description` 2-4 cümle: olayın özeti (aramada bulunsun diye anahtar kelimelerle) + yorum
  sorusu. `hashtags` 3-5 (`#shorts` dahil, `#pekiya` kanal etiketi). `tags` 5-10 arama ifadesi
  (Türkçe ve İngilizce: "peki ya", "what if").
- **Instagram Reels:** `caption` ilk satırı ≤ 125 karakter (sonrası "...devamı"nda kalır): kanca
  cümlesi. Sonra boş satır, yorum sorusu ("Sen olsan ne yapardın? 👇"). `hashtags` 3-5 (Instagram
  en fazla 5'e izin veriyor): 1 geniş (#whatif), 2-3 konu (#uzay, #bilim), 1 kanal (#pekiya).
- **TikTok:** `caption` 1-2 kısa cümle, merak + izleme çağrısı ("sonuna kadar izle"). `hashtags`
  3-5: kanal (#pekiya), konu, 1 geniş/gündemde olan (#keşfet, #fyp yerine konuya yakın olanı tercih
  et). TikTok'un web yüklemesinde kapak videodaki bir kareden seçilir: `cover_at` saniyesini yaz,
  kapak yazısını oraya TikTok'un yazı aracıyla ekletirsin (Stüdyo bunu söyler).
- **Kapak (`cover_text`):** 3-5 kelime, büyük harf, 1,5 saniyede okunmalı; telefonda küçük
  görünür. Yazı yüzün altında, ortadaki bantta (`yayin-kapak` oraya koyar): üstte ve altta
  platform düğmeleri var, Instagram profil ızgarası ortadaki 3:4'ü gösterir. Kare: olayın en çarpıcı anı (patlama, dev sayaç, şaşkın yüz), karanlık
  ya da boş kare değil.
- **Yorum sorusu her platformda:** iki taraflı, cevabı kolay ("Sen olsan zıplar mıydın?").
- **Sonraki video:** varsa senaryonun `next_teaser`'ını açıklamanın sonuna bir cümleyle ekle
  ("Sıradaki: Dünya dönmeyi bıraksaydı?") ve kanala takip çağrısı yap.
- **Güvenlik:** gerçek kişiler hakkında iddia, korku/şiddet abartısı, sağlık tavsiyesi yok;
  bilimsel sayılar senaryodaki kaynaklara dayansın.
