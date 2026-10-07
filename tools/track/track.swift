// vlogkit-track: follow things through video frames with Apple's Vision framework.
//
//   ffmpeg ... -vf fps=F:round=up:start_time=0,scale=W:H,format=bgra -f rawvideo - | vlogkit-track W H faces [GRID]
//   ffmpeg ... (same) | vlogkit-track W H object X Y BW BH [MINCONF] [PATIENCE]
//
// Frames come in as raw BGRA (W x H) on stdin, exactly as ffmpeg decoded them (rotation, 10-bit,
// frame rate and size are ffmpeg's job), so frame i of the output is frame i of the decode.
// (`round=up:start_time=0` makes frame i the one on screen at i/F; the default rounding hands
// over a frame ~half a sample late.)
// One JSON line per frame on stdout; boxes are normalised (0-1) with a top-left origin, like
// vlogkit-vision:
//
//   faces   {"i": 3, "faces": [[x, y, w, h, conf], ...]}     VNDetectFaceRectanglesRequest on the
//           whole frame and on a GRID x GRID of overlapping tiles (default 3; 1 = whole frame
//           only). A face can appear more than once (tiles overlap); the caller merges them.
//   object  {"i": 3, "box": [x, y, w, h], "conf": 0.93}       VNTrackObjectRequest, started from
//           the box X Y BW BH on frame 0. Confidence below MINCONF (default 0.3) for PATIENCE
//           frames in a row (default 8) means the object is gone: {"i": first weak frame,
//           "lost": true} and the tool stops reading (the decoder upstream ends on EPIPE).
//
// The last line is always {"done": frames read, "lost": true|false}.
import CoreVideo
import Foundation
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 4, let W = Int(args[1]), let H = Int(args[2]), W > 0, H > 0 else {
    fail("usage: vlogkit-track W H faces | W H object X Y BW BH [MINCONF] [PATIENCE]")
}
let mode = args[3]
let frameBytes = W * H * 4
let stdin = FileHandle.standardInput
let sequence = VNSequenceRequestHandler()

func readFrame() -> Data? {
    var data = Data(capacity: frameBytes)
    while data.count < frameBytes {
        let chunk = stdin.readData(ofLength: frameBytes - data.count)
        if chunk.isEmpty { return data.count == frameBytes ? data : nil }
        data.append(chunk)
    }
    return data
}

func makeBuffer(_ data: Data) -> CVPixelBuffer {
    var buf: CVPixelBuffer?
    let attrs = [kCVPixelBufferIOSurfacePropertiesKey: [:]] as CFDictionary
    CVPixelBufferCreate(kCFAllocatorDefault, W, H, kCVPixelFormatType_32BGRA, attrs, &buf)
    guard let pb = buf else { fail("cannot allocate a frame buffer") }
    CVPixelBufferLockBaseAddress(pb, [])
    let dst = CVPixelBufferGetBaseAddress(pb)!.assumingMemoryBound(to: UInt8.self)
    let rowBytes = CVPixelBufferGetBytesPerRow(pb)
    data.withUnsafeBytes { (src: UnsafeRawBufferPointer) in
        let s = src.bindMemory(to: UInt8.self).baseAddress!
        for y in 0..<H { memcpy(dst + y * rowBytes, s + y * W * 4, W * 4) }
    }
    CVPixelBufferUnlockBaseAddress(pb, [])
    return pb
}

/// Vision rect (bottom-left origin) -> "x,y,w,h" with a top-left origin.
func box(_ r: CGRect) -> String {
    String(format: "%.5f,%.5f,%.5f,%.5f", r.minX, 1 - r.maxY, r.width, r.height)
}

func emit(_ line: String) {
    print(line)
    fflush(stdout)
}

var frames = 0
var lost = false

switch mode {
case "faces":
    // Vision shrinks the whole frame to its own input size, so crowd faces of 40-80 px go
    // missing. The full frame + a GRID x GRID of overlapping tiles (regionOfInterest; results
    // come back in full-frame coordinates) finds several times more. The same face seen in two
    // tiles comes out twice: the caller merges them.
    let grid = args.count > 4 ? max(1, Int(args[4]) ?? 3) : 3
    var rois = [CGRect(x: 0, y: 0, width: 1, height: 1)]
    if grid > 1 {
        let side = (1 + 0.2 * Double(grid - 1)) / Double(grid)  // 20 % overlap
        for i in 0..<grid {
            for j in 0..<grid {
                let step = (1 - side) / Double(grid - 1)
                rois.append(CGRect(x: Double(i) * step, y: Double(j) * step, width: side, height: side))
            }
        }
    }
    let requests = rois.map { roi -> VNDetectFaceRectanglesRequest in
        let r = VNDetectFaceRectanglesRequest()
        r.regionOfInterest = roi
        return r
    }
    while let data = readFrame() {
        let pb = makeBuffer(data)
        var faces: [String] = []
        if (try? sequence.perform(requests, on: pb)) != nil {
            for r in requests {
                faces += (r.results ?? []).map { "[\(box($0.boundingBox)),\(String(format: "%.3f", $0.confidence))]" }
            }
        }
        emit("{\"i\":\(frames),\"faces\":[\(faces.joined(separator: ","))]}")
        frames += 1
    }

case "object":
    guard args.count >= 8, let x = Double(args[4]), let y = Double(args[5]),
          let bw = Double(args[6]), let bh = Double(args[7]), bw > 0, bh > 0
    else { fail("object: X Y BW BH (0-1, top-left origin)") }
    let minConf = args.count > 8 ? Float(args[8]) ?? 0.3 : 0.3
    let patience = args.count > 9 ? Int(args[9]) ?? 8 : 8
    let start = CGRect(x: x, y: 1 - y - bh, width: bw, height: bh)
    var observation = VNDetectedObjectObservation(boundingBox: start)
    let request = VNTrackObjectRequest(detectedObjectObservation: observation)
    var weak = 0
    var firstWeak = 0
    while let data = readFrame() {
        let pb = makeBuffer(data)
        request.inputObservation = observation
        var conf: Float = 0
        var rect = observation.boundingBox
        if (try? sequence.perform([request], on: pb)) != nil,
           let result = request.results?.first as? VNDetectedObjectObservation {
            observation = result  // continue this tracker on the next frame
            conf = result.confidence
            rect = result.boundingBox
        }
        if frames == 0 { conf = max(conf, 1); rect = start }  // the given box is the truth
        emit("{\"i\":\(frames),\"box\":[\(box(rect))],\"conf\":\(String(format: "%.3f", conf))}")
        if conf < minConf {
            if weak == 0 { firstWeak = frames }
            weak += 1
            if weak >= patience {
                emit("{\"i\":\(firstWeak),\"lost\":true}")
                lost = true
                request.isLastFrame = true
                frames += 1
                break
            }
        } else {
            weak = 0
        }
        frames += 1
    }

default:
    fail("mode: faces | object")
}
emit("{\"done\":\(frames),\"lost\":\(lost)}")
