// vlogkit-vision: what is in a frame, with Apple's Vision framework (no model download).
// Usage: vlogkit-vision [--no-aesthetics] IMAGE...
// One JSON object per image:
//   {"file", "faces": [{"box": [x, y, w, h], "conf"}], "humans": [{"box", "conf"}],
//    "labels": [{"id", "conf"}], "aesthetics": {"overall", "utility"}}
// Boxes are normalised (0-1) with the origin at the top-left. Labels: VNClassifyImageRequest's
// taxonomy (English identifiers), top 5 above 0.1. Aesthetics: macOS 15+ only.
import Foundation
import ImageIO
import Vision

func box(_ r: CGRect) -> [Double] {
    [Double(r.minX), Double(1 - r.maxY), Double(r.width), Double(r.height)]
}

@main
struct Main {
    static func main() async {
        var aesthetics = true
        var files: [String] = []
        for arg in CommandLine.arguments.dropFirst() {
            if arg == "--no-aesthetics" { aesthetics = false } else { files.append(arg) }
        }
        for file in files {
            var out: [String: Any] = ["file": file]
            let url = URL(fileURLWithPath: file)
            guard let src = CGImageSourceCreateWithURL(url as CFURL, nil),
                  let image = CGImageSourceCreateImageAtIndex(src, 0, nil)
            else {
                out["error"] = "unreadable"
                emit(out)
                continue
            }
            let faces = VNDetectFaceRectanglesRequest()
            let humans = VNDetectHumanRectanglesRequest()
            humans.upperBodyOnly = false
            let classify = VNClassifyImageRequest()
            let handler = VNImageRequestHandler(cgImage: image, options: [:])
            try? handler.perform([faces, humans, classify])
            out["faces"] = (faces.results ?? []).map { ["box": box($0.boundingBox), "conf": Double($0.confidence)] }
            out["humans"] = (humans.results ?? []).map { ["box": box($0.boundingBox), "conf": Double($0.confidence)] }
            out["labels"] = (classify.results ?? [])
                .filter { $0.confidence >= 0.1 }
                .prefix(5)
                .map { ["id": $0.identifier, "conf": Double($0.confidence)] }
            if aesthetics, #available(macOS 15.0, *) {
                let request = CalculateImageAestheticsScoresRequest()
                if let r = try? await request.perform(on: image) {
                    out["aesthetics"] = ["overall": Double(r.overallScore), "utility": r.isUtility]
                }
            }
            emit(out)
        }
    }

    static func emit(_ obj: [String: Any]) {
        if let data = try? JSONSerialization.data(withJSONObject: obj),
           let s = String(data: data, encoding: .utf8) {
            print(s)
            fflush(stdout)
        }
    }
}
