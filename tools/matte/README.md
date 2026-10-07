# vlogkit-matte

A per-frame person matte for video, made with Apple's Vision framework (macOS 14+). No model
download.

You don't build it by hand. `vlogkit.video.background.ensure_built()` compiles it into
`build/bin/vlogkit-matte` on first use, and again whenever this source changes:

    swiftc -O tools/matte/matte.swift -o build/bin/vlogkit-matte

It is a filter in a pipe. Raw BGRA frames go in, one 8-bit matte per frame comes out (255 =
person):

    ffmpeg -ss S -t D -i IN -vf scale=W:H,format=bgra -f rawvideo - \
      | vlogkit-matte W H hybrid \
      | ffmpeg -f rawvideo -pix_fmt gray -s WxH -framerate 30000/1001 -i - -c:v ffv1 matte.mkv

ffmpeg does the decoding, so the matte is frame-aligned by construction. Rotation, 10-bit and the
reduced size are ffmpeg's job, not the tool's. `vlogkit.video.background.matte()` runs this pipe
(media-engine decode + GPU scale, software fallback) and caches the result in `build/matte`.

## Modes

| mode       | request                                               | on the rize takes                                  |
|------------|-------------------------------------------------------|----------------------------------------------------|
| `fg`       | `VNGenerateForegroundInstanceMaskRequest`             | sharp, tight hair line; any salient subject        |
| `accurate` | `VNGeneratePersonSegmentationRequest` `.accurate`     | wispy hair, but a dark curtain halo + edge line    |
| `balanced` | `VNGeneratePersonSegmentationRequest` `.balanced`     | blurry edge halo; fades where the body leaves frame |
| `hybrid`   | fg × dilated person gate + the person's solid core     | **default**: fg edges, people only                 |

How `hybrid` combines them:

- **Presence comes from `fg`.** On an empty curtain both person masks hallucinate soft blobs, up to
  90 % of the frame; `fg` correctly finds nothing. If `fg` drops out for one or two frames while
  someone was in frame, the last matte is repeated.
- **The person mask is only a gate.** It is boosted ×4 and clamped, then dilated by 1.5 % of the
  frame. It fades softly at the bottom edge; used as a multiplier, that fade would make the
  sweater see-through.
- **The person's solid core.** The person mask eroded by 2.5 % fills holes in `fg`, but only within
  3 % of `fg`.

Speed on 4K HEVC 10-bit, matte at 1920x1080 (M-series): `hybrid` ~30 fps, including the decode.
