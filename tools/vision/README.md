# vlogkit-vision

Apple Vision on still frames: faces, human bodies, scene labels (`VNClassifyImageRequest`) and, on
macOS 15+, an aesthetics score (`CalculateImageAestheticsScoresRequest`). No model download.

Built on demand by `vlogkit.analysis.vision.ensure_built()` into `build/bin/vlogkit-vision`
(rebuilt when this source changes):

    swiftc -O -parse-as-library tools/vision/vision.swift -o build/bin/vlogkit-vision

Usage: `vlogkit-vision [--no-aesthetics] IMAGE...` prints one JSON object per image; boxes are
normalised (0-1) with a top-left origin. Used by the footage log (`analysis/footage.py`) to tell
real moments from camera handling.
