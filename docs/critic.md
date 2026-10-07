# Eleştirmen turu

Amaç: teslimden önce videoyu kullanıcıdan önce, acımasızca izlemek. Övgü yok; önem sırasına göre zaman damgalı sorun listesi. Eleştirmen düzeltme yapmaz, sadece raporlar; düzeltmeyi kurguyu yapan ajan yapar.

Claude Code'da bu tur `vlogkit-critic` alt ajanıyla yapılır (`.claude/agents/vlogkit-critic.md`), ayrı bir bağlamda: kurguyu yapan ajanın varsayımlarını taşımaz. Codex'te alt ajan yok; aynı listeyle ayrı bir tur yap ve kendi planını değil videonun kendisini kontrol et.

## Girdi
- Video yolu; varsa proje ve varyant.
- Kullanıcının isteği (tek paragraf) ve vaat.
- `vlogkit review` raporu (`build/review/<ad>.md`), plan sayfası (`<ad>_planlar.jpg`) ve kesme sayfaları (`<ad>_kesmeler*.jpg`).
- Varsa referans videolar ya da kullanıcının beğendiği önceki bir kurgu.

## Nasıl bakılır
1. Review raporunu oku; `!` maddelerinin hepsi listeye girer (çözülmediyse).
2. Plan sayfasına ve kesme sayfalarına tek tek bak.
3. Açılış: Short'ta ilk 3 sn, uzun videoda ilk 15 sn için `uv run vlogkit sheet VIDEO --duration 3 --fps 4` ve `uv run vlogkit strip VIDEO --start 0 --end 15`.
4. Şüpheli her an için `vlogkit strip` (kelime ve ses) ya da `vlogkit frame` (tek kare, ızgaralı).
5. Altyazıları transcript ile karşılaştır (`vlogkit transcribe VIDEO --words`, önbellekli): yazım, Türkçe karakter, zamanlama.

## Kontrol listesi
- **Kanca:** vaat ilk saniyelerde görünür ve duyulur mu; ilk kare dolu mu, ilk ses 0,5 sn içinde mi.
- **Planlar:** anlamsız ya da boş plan (kamerayı kurma, lense eğilme, duvar), aynı anın tekrarı.
- **Kesmeler:** yarım kalan hareket ya da kelime, zıplayan kadraj (jump cut istenmediyse), flaş, siyah kare, donuk görüntü.
- **Altyazı:** okunurluk (kontrast, süre), güvenli alan (9:16'da platform arayüzünün altında kalmasın), yazım, emoji kuralı.
- **Ses:** -14 LUFS / -1 dBTP ölçümü, kesmede seviye sıçraması. Ton, müzik uyumu ve miks dengesi dinlemeden bilinmez: uydurma, kullanıcıya "dinleyerek kontrol et" diye bırak.
- **Tempo:** Short'ta 3 sn, uzun videoda 5 sn'den uzun değişimsiz an; ortada sarkan bölüm.
- **Bitiş:** ödülden sonra uzamıyor mu; Short'ta loop ya da net bitiş.
- **İstek:** kullanıcının istediği her madde yapılmış mı; istenmeyen bir şey eklenmiş mi (oran, emoji, müzik).

## Çıktı
```
## Eleştirmen: <video adı>
1. [kritik] 00:12.4: <ne yanlış>. Düzeltme: <somut öneri>
2. [önemli] 01:03.0-01:05.2: ...
3. [küçük] ...
Genel: <tek cümle: en büyük risk>
```
- En fazla 10 madde, önem sırasıyla: **kritik** (izleyiciyi kaçırır ya da hata gibi görünür), **önemli** (belirgin kalite kaybı), **küçük** (cila).
- Her maddede zaman ve somut düzeltme olsun. Ölçemediğini ölçmüş gibi yazma.
- Sorun yoksa "Kritik ya da önemli sorun yok" yaz; madde uydurma.
