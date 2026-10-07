// vlogkit-ocr: on-screen text in still frames, with Apple's Vision framework (no model download).
// Usage: vlogkit-ocr [--accurate] IMAGE...
// Prints one JSON object per image: {"file": ..., "texts": [{"text", "conf", "box": [x, y, w, h]}]}
// Boxes are normalised (0-1) with the origin at the top-left.
import Foundation
import ImageIO
import Vision

var accurate = false
var files: [String] = []
for arg in CommandLine.arguments.dropFirst() {
    if arg == "--accurate" { accurate = true } else { files.append(arg) }
}

for file in files {
    var texts: [[String: Any]] = []
    let url = URL(fileURLWithPath: file)
    if let src = CGImageSourceCreateWithURL(url as CFURL, nil),
       let image = CGImageSourceCreateImageAtIndex(src, 0, nil) {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = accurate ? .accurate : .fast
        request.usesLanguageCorrection = false
        request.recognitionLanguages = ["tr-TR", "en-US"]
        try? VNImageRequestHandler(cgImage: image, options: [:]).perform([request])
        for obs in request.results ?? [] {
            guard let top = obs.topCandidates(1).first else { continue }
            let b = obs.boundingBox
            texts.append([
                "text": top.string,
                "conf": Double(top.confidence),
                "box": [Double(b.minX), Double(1 - b.maxY), Double(b.width), Double(b.height)],
            ])
        }
    }
    let line: [String: Any] = ["file": file, "texts": texts]
    if let data = try? JSONSerialization.data(withJSONObject: line),
       let s = String(data: data, encoding: .utf8) {
        print(s)
    }
}
