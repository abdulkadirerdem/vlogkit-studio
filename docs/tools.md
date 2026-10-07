# Kaliteyi artırabilecek açık kaynak araçlar (araştırma: 29 Eylül 2026)

Bu belge henüz kurulmamış araçları değerlendirir. Kurulum kullanıcının onayıyla yapılır. Lisans kısmındaki uyarılar para kazanılan bir kanal için geçerli.

## Makinede zaten olanlar (ücretsiz, kurulum yok)

- **Donanım:** Apple M5 Pro, 48 GB.
- **Apple VTFrameProcessor** (macOS 26, Swift ile çağrılır):
  - ML Super Resolution: 4x, giriş en fazla 1920x1080;
  - kare hızı dönüştürme (gerçek ara kare ile yavaş çekim), zamansal gürültü azaltma, hareket bulanıklığı.
- **AUSoundIsolation:** Apple'ın yapay zekâlı ses izolasyonu.
- **ffmpeg-full 9.0.2:**
  - var: vidstab (stabilizasyon), deshake, afftdn, arnndn (model dosyası ayrıca indirilir), dialoguenhance, deesser, speechnorm, rubberband, nlmeans/bm3d, cas, lut3d, minterpolate;
  - yok: `sr` ve `dnn_processing`.
- **DaVinci Resolve 21.1** (ücretsiz sürüm):
  - FCPXML ve .otio içe aktarıyor;
  - Voice Isolation, SuperScale ve SpeedWarp yalnız Studio'da;
  - Film Looks LUT'ları (Kodak 2383, Fuji 3513) log girdi bekler, telefon görüntüsüne düşük oranda uygulanmalı.

## Kurulanlar (v0.8.0)

| Araç | Nerede | vlogkit'te | Lisans |
|---|---|---|---|
| vid.stab | ffmpeg-full içinde | `video/stabilize.py`, `vlogkit stabilize` | GPL (yerel ffmpeg derlemesi) |
| DeepFilterNet 0.5.6 | `~/.cache/vlogkit/bin/deep-filter` (28 MB) | `audio/denoise.py`, `vlogkit denoise` | MIT / Apache-2.0 |
| Demucs 4.1.0 | `uv tool` (~0,5 GB) + model (~89 MB) | `audio/separate.py`, `vlogkit separate` | MIT |
| Qwen3.5-9B (4-bit MLX) + mlx-vlm 0.7.4 | `uv tool` (mlx-vlm) + Hugging Face önbelleği (5,6 GB) | `analysis/localvlm.py`, `tools/vlm`, `vlogkit log --vlm`, `vlogkit ask` | Apache-2.0 |
| Apple VTFrameProcessor | macOS, `tools/vt` → `build/bin/vlogkit-vt` | `video/vt.py`, `vlogkit upscale` / `slowmo`: ML süper çözünürlük, ara kare, gürültü, hareket bulanıklığı | Sistem API'si |
| Apple Vision (yüz, gövde, sahne etiketi, estetik puan) | macOS, `tools/vision` → `build/bin/vlogkit-vision` | `analysis/vision.py`, `vlogkit log` | Sistem API'si |
| Apple Vision OCR | macOS, `tools/ocr` → `build/bin/vlogkit-ocr` | `analysis/ocr.py`: gömülü yazıyı bulur (montaj, kapak, kanca) | Sistem API'si |
| Apple Vision takip (yüz algılama + nesne takibi) | macOS, `tools/track` → `build/bin/vlogkit-track` | `video/redact.py`, `vlogkit redact`: yüz ve plaka bulanıklaştırma, tek kişiye spot ışığı | Sistem API'si |
| Apple Vision özne maskesi | macOS 14+, `tools/segment` → `build/bin/vlogkit-segment` | `analysis/segment.py`: kişiyi kareden keser (Fotoğraflar'daki "özneyi kaldır"), kapak kompozisyonu | Sistem API'si |
| Apple Vision video maskesi (ön plan + insan, hybrid) | macOS 14+, `tools/matte` → `build/bin/vlogkit-matte` | `video/background.py`, `vlogkit background`: konuşma çekiminin arkasını değiştirir | Sistem API'si |
| Qwen3.5-9B mimik (yüz yakın planı) | yerel model | `localvlm.expression`, `vlogkit face` | Apache-2.0 |

Kurulum ve durum: `vlogkit extras list`, `vlogkit extras install deepfilter|demucs`, `vlogkit doctor`.

## Öncelikli 5 öneri

1. **Apple VT yardımcı programı.** Küçük bir Swift komut satırı aracı olacak.
   - Düşük çözünürlüklü kaynakta önce zamansal gürültü azaltma, sonra ML 4x büyütme, sonra 1080'e indirme. Lanczos büyütmedeki "büyümüş blok" görüntüsü yerine gerçek kenarlar çıkar.
   - Aynı API hız rampasında gerçek ara kare, whip pan'de doğal hareket bulanıklığı verir.
   - Not: 464x262 kaynaktan 9:16 tam boy kırpma yapılırsa ~147 px genişlik kalır; bunu hiçbir büyütücü kurtaramaz. Böyle kaynakta "pencere + bulanık arka plan" düzeni kullanılır.
2. **DeepFilterNet3** (MIT/Apache, `deep-filter` arm64 binary'si, ~10 MB).
   - Dağdaki rüzgârı, nefesi ve kalabalık uğultusunu afftdn'nin "su altı" sesi olmadan temizler. AUSoundIsolation ile karşılaştırılır.
   - Zincir: highpass → DeepFilterNet → deesser → speechnorm → loudnorm.
3. **vidstab** (ffmpeg'de hazır). Koşarken çekilen telefon planları için 2 geçiş, `smoothing` 15-30 ve hafif zoom.
4. **Demucs htdemucs** (MIT, ~80 MB). Konuşmayı müzikten ayırır.
   - Yarış alanındaki hoparlör müziği atılır: Content ID riski düşer, konuşma netleşir, yerine temiz müzik konur.
5. **Apple Vision** (pyobjc, sistem API'si). Yüz ve insan takibiyle yumuşak bir kırpma yolu çıkarır.
   - 16:9 → 9:16'da koşucu ortada kalır.
   - Aynı API kapak için özneyi de ayırır.

**Sonraki dalga:**
- auto-editor ile PySceneDetect (tempo ve kesme);
- Apple kare hızı dönüştürme yetmezse RIFE (MIT);
- OpenTimelineIO çıktısı;
- Real-ESRGAN (BSD) ile Apple SR'ın A/B karşılaştırması.

## Değerlendirilen diğerleri

| Araç | İş | Karar | Neden |
|---|---|---|---|
| Real-ESRGAN ncnn | Kare kare 4x büyütme | Önerilir (Apple SR ile A/B) | BSD-3, macOS binary'si var. Son sürüm 2022. |
| SeedVR2-3B | Difüzyonla video restorasyonu | Belki | Apache, ama 6,8 GB ve yavaş. Kritik tek planlar için. |
| RIFE ncnn | Ara kare üretimi | Önerilir (yedek) | MIT. |
| audio-separator (UVR/Roformer) | Daha temiz vokal ayırma | Belki | Ağırlık lisansları belirsiz. Demucs tercih edilir. |
| auto-editor | Sessizlik kesme | Önerilir | Unlicense. vlogkit'in `gaps` aracıyla örtüşüyor; Resolve'a çıktı verebiliyor. |
| WhisperX | Kelime hizalama | Belki | ~1,2 GB. whisper.cpp kelime zamanları şimdilik yetiyor. |
| PySceneDetect | Sahne tespiti | Önerilir | BSD-3. Uyarlanabilir eşik kullanıyor. |
| MediaPipe | Yüz ve poz | Belki | Apple Vision yetmezse. |
| Ultralytics YOLO | Nesne takibi | Hayır | AGPL ya da ücretli lisans. |
| OpenColorIO + CC0 LUT'lar | Renk | Belki | `lut3d` ile. |
| Remotion / Manim | Kodla animasyon (rota, irtifa grafiği) | Belki | Remotion 4+ çalışanlı şirkete ücretli; Manim MIT. |
| Stable Audio Open / ACE-Step | SFX ve müzik üretimi | Belki | Stable Audio yıllık 1M$ gelir altında ticari serbest. ACE-Step MIT ama 5-10 GB. |
| Freesound CC0 + Sonniss GDC | SFX kütüphanesi | Önerilir | Yalnız CC0 al. Sonniss'i yapay zekâ eğitiminde kullanmak ve tek tek satmak yasak. |
| Chatterbox Multilingual | Türkçe konuşma sentezi ve ses klonu | Belki | MIT. Her çıktıya filigran gömülür. Yalnız kendi sesini klonla; YouTube'da "sentetik" etiketi gerekir. |
| rembg | Arka plan silme | Belki | u2net ve BiRefNet ticari serbest; isnet ve bria-RMBG değil. |

## Kullanma (para kazanılan kanal için)

- **Ticari kullanıma kapalı (NC):** MusicGen, F5-TTS, XTTS-v2 (çıktılar dahil), Upscayl'ın UltraSharp/Remacri/Ultramix modelleri, rembg'deki isnet ve bria-RMBG-2.0.
- **AGPL** (Ultralytics, whisper-timestamped, Upscayl, Video2X): Yerelde ayrı süreç olarak kullanılabilir. vlogkit dağıtılırsa ya da servis olarak sunulursa copyleft yükümlülüğü doğar.
- **Resolve LUT'ları:** Kendi render'larında kullanılabilir, ama dosyalar repoya konmaz.

## Kaynaklar

- https://developer.apple.com/documentation/videotoolbox/vtframeprocessor, https://developer.apple.com/videos/play/wwdc2025/300/
- https://github.com/Rikorose/DeepFilterNet, https://github.com/adefossez/demucs, https://github.com/GregorR/rnnoise-models
- https://github.com/xinntao/Real-ESRGAN-ncnn-vulkan, https://github.com/ByteDance-Seed/SeedVR, https://github.com/TNTwise/rife-ncnn-vulkan
- https://github.com/WyattBlue/auto-editor, https://github.com/Breakthrough/PySceneDetect, https://github.com/m-bain/whisperX
- https://github.com/AcademySoftwareFoundation/OpenTimelineIO, https://github.com/resemble-ai/chatterbox, https://github.com/danielgatis/rembg
- https://huggingface.co/stabilityai/stable-audio-open-1.0, https://github.com/ace-step/ACE-Step-1.5, https://sonniss.com/gdc-bundle-license/
- https://www.ultralytics.com/license, https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
