# vlogkit-track

Follows things through video frames with Apple's Vision framework. No model download.

You don't build it by hand. `vlogkit.video.redact.ensure_built()` compiles it into
`build/bin/vlogkit-track` on first use, and again whenever this source changes:

    swiftc -O tools/track/track.swift -o build/bin/vlogkit-track

It is a filter in a pipe. Raw BGRA frames go in, one JSON line per frame comes out:

    ffmpeg -ss S -t D -i IN -vf fps=8:round=up:start_time=0,scale=W:H,format=bgra -f rawvideo - \
      | vlogkit-track W H faces 3

    ffmpeg -ss S -i IN -vf fps=30:round=up:start_time=0,scale=W:H,format=bgra -f rawvideo - \
      | vlogkit-track W H object 0.42 0.44 0.13 0.43

ffmpeg does the decoding, so line i is decode frame i (rotation and size are ffmpeg's job). Boxes
are normalised (0-1) with a top-left origin. `vlogkit.video.redact` runs this pipe (media-engine
decode + GPU scale, software fallback) and caches the output in `build/redact/cache`.

## Modes

| mode | request | output |
|---|---|---|
| `faces [GRID]` | `VNDetectFaceRectanglesRequest` on the whole frame + a GRID x GRID of overlapping tiles (default 3) | `{"i", "faces": [[x, y, w, h, conf], ...]}`; a face can appear twice (tiles overlap) |
| `object X Y W H [MINCONF] [PATIENCE]` | `VNTrackObjectRequest` from the box on frame 0 | `{"i", "box", "conf"}`; after PATIENCE frames below MINCONF: `{"i", "lost": true}` and it stops |

The last line is always `{"done": frames, "lost": true|false}`.

- **Tiles:** Vision shrinks the whole frame to its own input size, so crowd faces of 40-80 px are
  missed. On a 1080x1920 start-line shot the tiles found 5-12 faces per frame where the whole
  frame found 0-5. Results of a `regionOfInterest` request come back in full-frame coordinates.
- **The `fps` filter needs `round=up:start_time=0`:** with the default rounding, sample k at 8/s
  is the frame ~0.05 s after k/8, and the boxes trail a panning crowd.
- **Lost:** a stopped tool leaves the decoder with a broken pipe; that is expected.

Speed (M5 Pro): faces at 8/s with 3x3 tiles, 4K HEVC: 14 s of video in 3.5 s. Object at 30/s,
4K decoded to 1280 px: 8 s in 1.6 s.
