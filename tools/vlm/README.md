# vlogkit yerel video modeli (worker)

`worker.py`, mlx-vlm'in kendi `uv tool` ortamında çalışır; vlogkit'in venv'ine MLX ve transformers girmez.

- **Kurulum:** `uv run vlogkit extras install vlm`
  - `uv tool install mlx-vlm` (~0,3 GB);
  - `mlx-community/Qwen3.5-9B-MLX-4bit` modeli (~5,6 GB, Apache-2.0) Hugging Face önbelleğine iner.
- **Kullanım:** Doğrudan değil, `vlogkit.analysis.localvlm` üzerinden:
  - `vlogkit log KLASÖR --vlm`: her parçaya "model" sütunu;
  - `vlogkit ask VIDEO "soru" --start S --end E`.
- **Girdi:** `{"model", "fps", "max_tokens", "jobs": [{"id", "video", "prompt"}]}`.
- **Çıktı:** Her iş için bir JSON satırı `{"id", "text", "seconds"}`, sonunda `{"done", "load_seconds", "total_seconds"}`.
- Model bir kez yüklenir (~2 sn). Düşük öncelikle (`nice`) çalışır.
- **Başka model:** `VLOGKIT_VLM_MODEL` ile verilir (ör. `mlx-community/Qwen3-VL-8B-Instruct-4bit`). MoE Qwen3-VL modellerinde mlx-vlm video hatası açık; dense model seçin.
