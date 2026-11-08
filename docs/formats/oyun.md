# Format: Oyun reklamı tarzı soru (`"format": "oyun"`)

Mobil oyun reklamlarının dili ("Sadece %1'i bunu çözebilir"), ama bir oyun satmıyoruz: gerçek,
hayat kurtaran ya da şaşırtan bir bilgiyi soru olarak soruyoruz. Ekranda numaralı seçenekler
belirir, önce yanlış seçilir ve sonucu gösterilir (patlama, sel, kaos), sonra doğrusu ve nedeni.
25-45 sn, 6-12 cümle, 2-3 kelimelik altyazı. Ekran kuralları ve kit: `docs/3d.md`.

Bir oyunun adını, karakterini, arayüzünü ya da logosunu kullanma; "oyun reklamı" yalnızca
anlatım biçimi (seviye rozeti, seçenek, YANLIŞ/DOĞRU damgası).

## Neden tutar

- **Meydan okuma:** "Sadece %1'i doğru yapıyor" izleyiciyi kendini sınamaya çağırır; cevabını
  verip sonucu görmek için kalır.
- **Yanlışın bedeli:** yanlış seçimin sonucu ekranda büyük ve komik (patlayan tava, taşan
  banyo): en çok paylaşılan an.
- **Gerçek bilgi:** doğrusu ve nedeni bir cümlede; "bunu bilmiyordum" yorumu.
- **Seri:** her video bir seviye; sonda bir sonraki seviye vaadi.

## Anlatım kalıbı

1. **Meydan okuma (ilk cümle):** "Sadece yüzde 1'i bunu doğru yapıyor." İlk karede tehlike
   başlamış olsun (tavada alev).
2. **Soru:** durum tek cümle + "Hangisini kullanırsın?" Soru kelimesinde `choices` (2-3
   seçenek, `"dur": 2.4`); o beat'e `"hold": 1.2` (izleyici seçsin).
3. **Yanlış seçim (1-2 kez):** "Su mu? Yanlış!" `choices` yeniden, `"pick": {"n": 1, "at": "Su",
   "ok": false}` (satır kırmızı yanar) + `"stamp": {"text": "YANLIŞ", "at": "Yanlış"}` + olayın
   kendisi (`explosion`, `fire`, `flood`). Ardından nedeni tek cümle, gerçek ve kaynaklı.
4. **Doğrusu:** "Doğrusu: ocağı kapat, üstünü ıslak havluyla ört." `pick` ile `"ok": true` +
   `"stamp": {"text": "DOĞRU", "at": "...", "ok": true}` + sonuç (`smoke`, alev söner).
5. **Neden (tek cümle):** "Alev havasız kalır ve söner."
6. **Sonraki seviye:** "Seviye 8 daha zor. Hazır mısın?" Bitiş kartı: `"end": {"tag":
   "SIRADAKİ", "title": "SEVİYE 8"}`.

Kurallar: soru gerçek ve doğrulanmış (NOTES.md'ye kaynak); yanlış seçenekler insanların gerçekten
yaptığı hatalar. Kısa cümle (3-9 kelime), ikinci tekil şahıs. Tehlikeli bir şeyi özendirme:
doğrusu her zaman güvenli olan.

## Ekranda

- **Seviye rozeti:** `"hud": {"label": "SEVİYE 7"}` (sayı göstermeden etiket olarak kalır).
- **Mekân:** tehlikenin mekânı (kitchen, bathroom, room, street, park); tek mekân.
- **Seçenekler:** `choices` ekranın ortasında, altyazı o sürede durur. Seçenekler kısa (en çok
  18 harf) ve somut (SU / UN / ISLAK HAVLU).
- **Damga:** `stamp` YANLIŞ kırmızı, DOĞRU yeşil (`"ok": true`); 1,3 sn.
- **Olay:** yanlışın sonucu büyük (`explosion`, `fire`, `flood`, `smoke`), kamera sarsıntısı
  (`shake`), vuruş sesi (`sfx` impact/boom).
- **Kamera:** tehlikeye yakın plan → kahramanın yüzü → olay; her 2 sn yeni plan.

## Kontrol listesi

- [ ] İlk karede tehlike, ilk cümlede meydan okuma.
- [ ] Soru beat'inde `choices` + `hold`; seçenekler gerçek hatalar.
- [ ] Yanlış seçimde `pick` (ok: false) + `stamp` YANLIŞ + olay; nedeni gerçek ve kaynaklı.
- [ ] Doğrusu güvenli; `pick` (ok: true) + `stamp` DOĞRU.
- [ ] Bitiş kartı sonraki seviyeyi söylüyor.

Başlangıç: `uv run vlogkit 3d new <proje> --format oyun` çalışılmış örnekle (tavada yağ yangını) açar.
