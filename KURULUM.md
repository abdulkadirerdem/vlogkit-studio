# vlogkit kurulumu

vlogkit, videolarını bir yapay zekâ ajanıyla kurgulamanı sağlar. Ne istediğini **vlogkit Stüdyo**'ya yazarsın, Claude Code ya da Codex kurguyu yapar, sen sonucu izleyip düzeltme istersin. Her şey kendi bilgisayarında çalışır; videoların hiçbir yere yüklenmez.

## Neler gerekiyor

- **Apple Silicon bir Mac** (M1, M2, M3, M4 ve sonrası) ve **macOS 14 (Sonoma)** ya da sonrası.
- **Bir abonelik:** Claude Pro / Max (Claude Code için) ya da ChatGPT Plus / Pro (Codex için). Biri yeter. Kurgu bu abonelikten çalışır, ayrıca ücret ödenmez.
- **Yer:** kurulum için ~6 GB. Kurgu sırasında 4K videolar büyük ara dosyalar yazar; 50 GB boş yer rahat çalışmak için iyi bir başlangıç.
- Mac'inin şifresi (Homebrew kurulurken bir kez sorulur) ve internet.

## Kurulum (bir kez, ~20-40 dakika)

1. **Terminal**'i aç: ⌘ + boşluk, "Terminal" yaz, Enter.
2. Aşağıdaki satırı kopyala, Terminal'e yapıştır ve Enter'a bas:

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/abdulkadirerdem/vlogkit-studio/main/install.sh)"
   ```

3. Şifre sorarsa Mac şifreni yaz (yazarken ekranda görünmez) ve Enter'a bas. "Command Line Tools" kurulumu için bir pencere açılırsa "Yükle"ye bas.
4. Bekle. Kurulum şunları yapar: Homebrew'u, video ve ses araçlarını (ffmpeg, whisper, aubio, uv) ve konuşma modelini (~1,6 GB) kurar, vlogkit'i `~/yt-vlogs/vlogkit` klasörüne indirir, lisanslı müzik ve ses kütüphanesini indirir, masaüstüne **vlogkit Stüdyo** uygulamasını koyar ve Stüdyo'yu tarayıcıda açar.

Bir adım yarıda kalırsa aynı satırı tekrar çalıştır: kurulu olanı geçer, eksik olanı tamamlar.

## İlk açılış

Stüdyo ilk açıldığında bir karşılama ekranı çıkar:

1. Aboneliğin hangisindeyse onun satırında **Kur**'a bas (Claude Code ya da Codex).
2. Sonra **Giriş yap**'a bas. Terminal açılır ve tarayıcıda hesabının giriş sayfası gelir; orada onayla.
3. Stüdyo girişi kendisi görür ve "Hazır" der. **Başla**'ya bas.

Sonraki seferlerde masaüstündeki **vlogkit Stüdyo**'ya çift tıklaman yeter.

## Kullanım

- Videolarını `~/yt-vlogs` klasörüne koy (ör. `~/yt-vlogs/tatil/ham/`). Stüdyo'da **Video** düğmesiyle seç ya da pencereye sürükle.
- Ne istediğini yaz: "Bu klasördeki ham çekimlerden 40 saniyelik bir Short yap" gibi. **Görev** menüsünde hazır istekler var.
- Kurgu bitince video Stüdyo'da oynar. Altındaki zaman çizelgesinden bir anı seçip yorum yazabilir ya da kesilecek kelimeleri işaretleyebilirsin.
- Kullanılan telifsiz müziklerin lisansları videonun yanındaki `.lisans.md` dosyasında ve Stüdyo'nun sağ üstündeki **Lisanslar** kartında durur. Platform telif talebi gönderirse oradaki itiraz metnini kullan.

## İsteğe bağlı: yerel video modeli

Ayarlar (⋯) > **Yerel video modeli** bölümünden bilgisayarına bir video modeli kurabilirsin. Bu model ham çekimlerini parça parça izleyip ne olduğunu not eder ve ajanın doğru anı bulmasına yardım eder. Şart değil: kurulu olmasa da her şey çalışır.

| Model | İndirme | Bellek | Not |
|---|---|---|---|
| Qwen3.5 2B | 1,8 GB | 8 GB | Hafif, kaba gözlem |
| Qwen3.5 4B | 3,1 GB | 16 GB | Dengeli |
| Qwen3.5 9B | 6 GB | 16 GB (24 GB rahat) | En iyisi |

Ekran Mac'inin belleğine göre hangisinin uyduğunu gösterir. Birden fazlasını kurabilir, hangisinin kullanılacağını seçebilirsin.

## Güncellemeler

Yeni bir sürüm çıkınca Stüdyo'nun sol alt köşesinde **Güncelleme var** yazar. Tıklarsan yeniliklerin listesi açılır, **Güncelle**'ye basınca Stüdyo kendini günceller ve yeniden açılır. Projelerin, videoların ve ayarların değişmez. Bir iş çalışırken güncelleme yapılmaz.

## Sorun çıkarsa

- **Stüdyo açılmıyor:** Terminal'de `cd ~/yt-vlogs/vlogkit && uv run vlogkit open` çalıştır; hata varsa ekrana yazar. Günlük dosyası: `~/yt-vlogs/vlogkit/build/ui/server.log`.
- **Bir araç eksik görünüyor:** Kurulum satırını tekrar çalıştır.
- **Her şeyi kontrol et:** `cd ~/yt-vlogs/vlogkit && uv run vlogkit doctor` hangi parçanın eksik olduğunu listeler.
- **Disk doluyor:** Ayarlar (⋯) > **Ara dosyalar** eski derlemelerin büyük ara dosyalarını siler. Teslim videoların kalır.

## Kaldırma

1. Masaüstündeki **vlogkit Stüdyo** uygulamasını ve `~/yt-vlogs/vlogkit` klasörünü sil. `~/yt-vlogs` içindeki videoların ve teslim dosyaların kalır.
2. İstersen indirilen modelleri de sil: `~/.cache/whisper-cpp` (konuşma modeli) ve `~/.cache/huggingface` (yerel video modeli).
3. Homebrew araçlarını kaldırmak istersen: `brew uninstall ffmpeg-full whisper-cpp aubio uv`.

## Lisans

vlogkit'in hakları geliştiricisine aittir ([LICENSE](LICENSE), PolyForm Noncommercial 1.0.0 ve ek izin). Kendi videolarını yapıp yayınlamak için, para kazanan kanallarda da serbestçe kullanabilirsin. Yazılımı satmak, ücretli hizmet olarak sunmak ya da ticari bir ürüne katmak için yazılı izin gerekir. Fontlar ve kütüphanedeki medya kendi lisanslarıyla gelir.
