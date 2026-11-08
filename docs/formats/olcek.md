# Format: Uzay ve ölçek (`"format": "olcek"`)

Akıl almaz bir ölçek sorusu ("Dünya ile Ay arasına kaç Dünya sığar?"). İzleyici tahmin eder,
video gerçek sayıları sayaçla verir ve kanıtı ekranda dizer (30 Dünya yan yana). Sonuç tahminden
çok farklı çıkar. 30-55 sn, 7-14 cümle, 2-3 kelimelik altyazı. Ekran kuralları ve kit:
`docs/3d.md`.

## Neden tutar

- **Tahmin:** soru izleyiciyi bir sayı söylemeye zorlar; cevabı görmek için kalır.
- **Sayaç:** büyük sayılar ekranda akarak gelir; okunur ve akılda kalır.
- **Kanıt:** sayıyı söylemekle kalmaz, ekranda gösterir (dizilen gezegenler, yan yana boylar).
- **İkinci şok:** sonuçtan sonra daha büyük bir gerçek ("ve bütün gezegenler de sığar").

## Anlatım kalıbı

1. **Soru (ilk cümle):** "Dünya ile Ay arasına kaç Dünya sığar?" İlk karede ikisi birden
   görünür; soru kelimesinde `choices` ile tahmin seçenekleri (`"dur": 2.2`).
2. **Yaygın tahmin:** "Çoğu insan 5 ya da 10 der."
3. **Sayılar (2-3 cümle):** her biri bir `count` ile: "Ay, bizden 384 bin kilometre uzakta."
   (`"count": {"from": 0, "to": 384400, "unit": "KM", "label": "UZAKLIK", "at": "384"}`).
4. **Sonuç:** "Yani araya tam 30 Dünya dizilir." Kanıt ekranda: aynı anda dizilen 30 küre
   (`globe` prop'ları, `scale` 0.01 → 1 ile tek tek belirir) ve sayaç 0 → 30.
5. **İkinci şok:** daha büyük ve doğru bir gerçek ("Güneş sistemindeki bütün gezegenler de bu
   boşluğa sığar.") ve bir terim ya da sayı.
6. **Kapanış:** bir sonraki ölçek sorusu `choices` ile ("Sence Güneş'in içine kaç Dünya
   sığar?"), bitiş kartı cevabı bir sonraki videoya bırakır.

Kurallar: her sayı hesaplanmış ve kaynaklı (NASA, ESA; NOTES.md'ye yaz). Yuvarlamayı söyle
("yaklaşık"). Kısa cümle (3-10 kelime). Sayıları rakamla yaz, seslendirme okur.

## Ekranda

- **Mekân:** `space` (yıldızlar, aşağıda Dünya) ya da `world`; karşılaştırma için koyu bir
  `studio` fonu (`"set_opts": {"color": "#0b1020"}`).
- **Kürelerin dizilişi:** `{"kind": "globe", "id": "d1", "r": 0.12, "at": [x, 0, 1.2]}` aralıklı;
  `moon` (`r`) dizinin sonunda. Kamera dizinin yanından `pan` ya da `zoom_out`.
- **Sayaç:** `count` (sayı olayla birlikte akar), `term` (öğrenilen kelime).
- **Kamera:** büyük ölçeklerde `zoom_out`; dizilişte `pan`; her 2 sn yeni plan.

## Kontrol listesi

- [ ] İlk cümle soru, ilk karede iki şey birden görünüyor; tahmin seçenekleri ekranda.
- [ ] Her sayı `count` ile ekranda ve NOTES.md'de kaynaklı.
- [ ] Sonuç ekranda kanıtla (dizilen küreler) gösteriliyor.
- [ ] İkinci şok var; kapanış bir sonraki soruyu soruyor.

Başlangıç: `uv run vlogkit 3d new <proje> --format olcek` çalışılmış örnekle (Dünya-Ay) açar.
