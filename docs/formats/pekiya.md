# Format: Peki ya? (`"format": "pekiya"`, varsayılan)

Bir "Peki ya…?" sorusu ve sonuçları. Sonuçlar tırmanarak ekranda olur: oda → sokak → şehir →
Dünya → uzay. 30-60 sn, 6-16 cümle, 2-3 kelimelik altyazı. Ekran kuralları ve kit: `docs/3d.md`.

## Hikâye kalıbı (7 adım)

1. **Soğuk açılış (0-3 sn):** soru ve ilk olay aynı anda. "Peki ya herkes aynı anda
   zıplasaydı?" derken ilk karede biri zıplıyor. Giriş, selam, açıklama yok.
2. **Kurallar (1-2 cümle):** sorunun koşulları net ("8 milyar insan, aynı saniye").
3. **Eğlenceli kısım (2-4 cümle):** ilk sonuçlar, giderek büyür; her biri bir öncekinden daha
   şaşırtıcı. Sayaç burada çalışır.
4. **Gerçek bilim (1-2 cümle):** gerçek bir sayı, hesaplanmış ve kaynaklı ("Bu gerçek.").
5. **Dönüş:** beklenmeyen sonuç; büyük olay (patlama, bölünme, kalabalık) burada.
6. **İnsani an (isteğe bağlı):** sonuç birine dokunur ("ve sen…"): ölçekten kişiye dal.
7. **Kapanış:** çözülmemiş bir soru ya da tehdit, yorum sorusu, sonraki video ipucu. Asla
   "ve herkes mutlu yaşadı" ile bitme.

## Cümle kuralları

- İkinci tekil şahıs, şimdiki/geniş zaman, kısa cümle (3-10 kelime). Toplam 70-140 kelime.
- **Her cümle bir resim:** görüntüsü olmayan cümleyi yeniden yaz.
- Güç/olayın bir kelimesi, bir sesi ve bir görünüşü olur ve her tekrarında aynıdır.
- Tek bir gerçek sayı en az bir kez: önce hesapla, NOTES.md'ye kaynağıyla yaz, sonra cümleye koy.
- Soru işareti merak, ünlem heyecan, üç nokta gerilim (ses bunu taşır).

## Ekranda

- Yaklaşık 2 saniyede bir plan (`shots` + `cue`); kesme cümlenin vurgulu kelimesine.
- Komşu iki plan aynı boy ve açıda olmaz (geniş → yakın → olayın kendisi → tepki).
- Olay o kelimede olur (`from`, `at`); vuruş sesi kelimenin hemen arkasındaki boşluğa düşer.
- Ölçek tırmanışı: büyük sayılarda `zoom_out`, uzay ve Dünya sahneleri sona doğru.
- Hikâye araçları: haber (`look: news`), viral telefon (`look: phone`), güvenlik kamerası
  (`look: security`), gazete, ARANIYOR afişi, harita.
- Dönüşten önce kısa bir sessizlik (müzik kesilir), dönüşte `boom`.

## Kontrol listesi

- [ ] İlk karede hareket, ilk cümlede soru.
- [ ] Her cümle ekranda bir olay; hiçbir plan 3 sn'den uzun değil (`3d plan`).
- [ ] Sayılar kaynaklı (NOTES.md), sayaç tek bir şeyi sayıyor.
- [ ] Son cümle yorum sorusu ya da tehdit; bitiş kartı sonraki videoyu söylüyor.
- [ ] `3d kontak` → render → `3d kontrol` → `3d puanla` (50/70 altıysa düzelt).
