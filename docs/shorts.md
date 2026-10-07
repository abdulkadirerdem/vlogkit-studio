# Shorts / Reels kuralları

## Teknik

| | Değer |
|---|---|
| Çözünürlük | 1080×1920, 29.97 fps (kaynak neyse o) |
| Encode | H.264 High 4.2, CRF 16, GOP 60, bt709, AAC 320k 48 kHz, `+faststart` (`export.encode.SHORTS`) |
| Yükleme dosyası | `export.encode.YOUTUBE_SHORTS`: YouTube'un önerdiği ayarlar ([1722171](https://support.google.com/youtube/answer/1722171)), yani 2 B-kare, kare hızının yarısı kadar kapalı GOP (15), CABAC, AAC-LC 384k. Projede `preset = YOUTUBE_SHORTS`. |
| Ses | -14 LUFS integrated, <= -1.5 dBTP |
| Süre | 60 sn altı en güvenli. 3 dakikaya kadar Shorts sayılıyor, telif iddiası kuralları farklı (aşağıda) |

## Güvenli alanlar (1080×1920)

- **Üst ~150 px:** arama ve kamera ikonları. Küçük etiketler y≈250'den başlar.
- **Alt %25–30:** başlık, kanal adı, açıklama. Altyazı merkezi **y≈1180** noktasında.
- **Sağ kenar (x > ~960, y 1000–1700):** beğen, yorum, paylaş butonları. Altyazı merkezi **x≈525**, en fazla **840 px** genişlik.
- **Büyük sayılar / meme üst yazısı:** y≈330.

## Tutunma (retention) notları

- **İlk 2 saniye:** Ses (insan sesi), hareket ve merak unsuru. Sonucu önce göstermek ("flash-forward") işe yarıyor.
- **Her sahneye bir bilgi:** Ekranda 2–4 sn'de bir yeni altyazı olsun. Sayıları vurgu rengiyle ver (04:05, 20, 08:00).
- **Emoji:** Az olsun. En fazla üç altyazıda bir, altyazı başına tek; her satırda emoji olunca hiçbiri göze çarpmıyor.
- **Döngü (loop):** Bitiş başlangıca bağlanırsa tekrar izlenme artar. Bitiş kartı serinin sonraki bölümüne yönlendirsin.

## Telif / lisans (araştırma: 28 Eylül 2026)

**Güvenli**
- Kendi çekimlerin ve kendi sesin.
- CC0 (Freesound), Pixabay Content License ve Pexels License dosyaları. Tümü `assets/manifest.toml` içinde ve kaynak göstermek gerekmiyor.
- ffmpeg ile sentezlenen efektler.
- **Ses efektleri ve CC lisanslı içerik Content ID referansı olamıyor** ([2605065](https://support.google.com/youtube/answer/2605065)). Yanlışlıkla telif iddiası gelirse manifest'teki kaynak sayfasıyla itiraz et.
- YouTube Audio Library (indirmek için YouTube Studio girişi gerekiyor).

**Riskli**
- Film, dizi, anime ve spor yayını klipleri (Surprised Pikachu, Travolta, Messi anları...). Hak sahipleri Content ID kullanıyor; LaLiga yılda 600 binden fazla videoya telif iddiası açıyor ve değiştirilmiş görüntüyü bile yakalıyor.
- Viral kullanıcı videoları ("Charlie Bit My Finger" gibi). Aile videoyu Viral Spiral üzerinden lisanslıyor.
- Orijinal meme müzikleri: To Be Continued/Roundabout, Coffin Dance/Astronomia, Curb/Frolic.
- "No copyright" yazan green-screen yüklemeleri hak sahibini değiştirmez. Kaynak göstermek veya "fair use" demek otomatik koruma sağlamaz.

**Kullanma**
- Myinstants gibi soundboard'lar. Sadece kişisel ve ticari olmayan kullanıma izin var, sesler de çoğunlukla başka yerden kopyalanmış.

**Viral klip kullanmanın yasal yolları**
1. **YouTube "Remix → Cut":** Uygun bir YouTube videosundan 1–5 sn alınır ve kaynak linkiyle gösterilir. Sadece mobil uygulamada çalışıyor, dosyaya gömülemez. Kurguyu vlogkit'te bitirip uygulamada Cut'la birleştir. Sahibi remix'i kapatmış olabilir. ([10623810](https://support.google.com/youtube/answer/10623810))
2. **Lisans satın almak:** Jukin Media, ViralHog, Storyful.

**Politika**
- **1 dk altı Short:** Telif iddiası gelirse hak sahibinin politikası uygulanır: gelir alma, takip veya bölgesel engel. Telif iddiası strike sayılmaz.
- **1–3 dk arası Short:** Aktif telif iddiası varken eskiden otomatik engelleniyordu. 24 Eylül 2026'dan itibaren artık otomatik engellenmiyor ([15424877](https://support.google.com/youtube/answer/15424877)).
- **Shorts gelir paylaşımı:** Sadece müzik gelir payını düşürüyor. Başkasının düzenlenmemiş film veya dizi klipleri gelir getirmez ([12504220](https://support.google.com/youtube/answer/12504220)).
- **YPP "reused content":** Kendi çekiminin içinde kısa eklemeler sorun değil ([1311392](https://support.google.com/youtube/answer/1311392)).
- **Pexels kuralı:** Tanınabilir kişileri küçük düşürecek şekilde kullanma.
