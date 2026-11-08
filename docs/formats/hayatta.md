# Format: Hayatta kalma günlüğü (`"format": "hayatta"`)

Bir kural ve bir ödül ("Bu odadan 30 gün çıkmazsan 1 milyon lira senin"), sonra günler. Her
gün yeni bir sorun çıkar, kahraman bir çözüm bulur; sorunlar giderek büyür. İzleyici "ben kaçıncı
günde pes ederdim?" diye kendini koyar. 35-60 sn, 8-16 cümle, 2-3 kelimelik altyazı. Ekran
kuralları ve kit: `docs/3d.md`.

## Neden tutar

- **Kendini koyma:** her sorun izleyicinin de başına gelebilecek bir şey (internet kesilir,
  yemek biter, uyku bozulur). İçinden "ben ne yapardım" diye cevap verir.
- **Sayaç:** gün sayısı ilerledikçe gerilim artar; izleyici 30. günü görmek ister.
- **Dönüş:** son günlerde kuralı zorlayan bir şey olur (kapı çalar, biri "süre doldu" der).
- **Yorum:** sonda numaralı seçenekler: yorum yazmak bir tuş kadar kolay.

## Anlatım kalıbı

1. **Kural ve ödül (ilk cümle):** "Bu odadan 30 gün çıkmazsan 1 milyon lira senin." İlk karede
   ödül görünür (para yağmuru, kahraman şaşkın).
2. **Gün 1 (kolay):** her şey yolunda görünür; sahne kurulur (yatak, buzdolabı, telefon).
3. **Günler (4-6 kez):** "Gün 5: İnternet kesiliyor." Sorun tek cümle, somut; ardından kahramanın
   çözümü ya da tepkisi tek cümle. Sorunlar giderek büyür: konfor → yemek → uyku → akıl sağlığı.
4. **Dönüş (son günler):** kuralı sınayan bir olay ("Gün 29: Kapı çalıyor.") ve bir ters köşe
   ("Ama takvime bakıyorsun: daha bir gün var.").
5. **Kapanış:** "Sen olsan kapıyı açar mıydın?" + `choices` (2-3 seçenek) + `hold`.

Kurallar: ikinci tekil şahıs, şimdiki zaman, kısa cümle (3-10 kelime). Gün sayıları rakamla.
Sorunlar gerçekçi; bir bilgi geçiyorsa (aç kalma süresi, uykusuzluğun etkisi) gerçek ve
kaynaklı (NOTES.md).

## Ekranda

- **Gün sayacı:** `"hud": {"label": "GÜN"}` en üstte; her gün beat'inde `"hud": {"value": 5,
  "at": "Gün"}`. Sayı yeni güne geçerken akar.
- **Mekân:** tek mekânda geçer (room, bedroom_night, kitchen, office, gym, elevator); gece
  günlerinde `bedroom_night`. Mekân değişirse hikâye bozulur.
- **Kahraman:** tek oyuncu (`cast`), her beat'te bir hareketle (`do`: shock, phone, sad, think,
  facepalm, sit, lie, scared, cheer). Yüz ifadesi (`face`) soruna göre.
- **Sorun anı:** her "Ama…" cümlesi kendiliğinden sarsıntı + çarpma sesiyle vurgulanır
  (`punch`); ayrıca bir efekt: telefon karardı (`flash`), çatlak (`crack`), duman (`smoke`).
- **Eşya:** sorunun nesnesi kadrajda olsun: buzdolabı, telefon, kapı (`"open"` ile açılır),
  takvim (`calendar`, `text` gün numarası).
- **Kamera:** her 2 saniyede yeni plan (`shots` + `cue`); geniş (oda) → yakın (yüz/eşya).
- **Kapanış:** `choices` (ör. AÇARDIM / AÇMAZDIM / GÖZETLERDİM) ve o beat'e `"hold": 2.2`.

## Kontrol listesi

- [ ] İlk cümle kural + ödül; ilk karede ödül görünüyor.
- [ ] Gün sayacı her gün beat'inde ilerliyor, sorunlar büyüyor.
- [ ] Her cümle ekranda bir olay; hiçbir plan 3 sn'den uzun değil (`3d plan`).
- [ ] Son günlerde dönüş ve ters köşe; kapanışta `choices`.
- [ ] `3d kontak` → render → `3d kontrol` → `3d puanla`.

Başlangıç: `uv run vlogkit 3d new <proje> --format hayatta` çalışılmış örnekle (30 gün oda) açar.
