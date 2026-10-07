// vlogkit-matte: a per-frame person matte for video with Apple's Vision framework.
//
//   ffmpeg ... -f rawvideo -pix_fmt bgra - | vlogkit-matte W H MODE | ffmpeg -f rawvideo -pix_fmt gray -s WxH -i - ...
//
// Frames come in as raw BGRA (W x H) on stdin, exactly as ffmpeg decoded them (rotation,
// 10-bit and colour conversion are ffmpeg's job, so the matte is frame-aligned by construction).
// For every frame one W x H 8-bit matte (255 = person) goes out on stdout.
//
// MODE:
//   fg        VNGenerateForegroundInstanceMaskRequest ("lift subject"): sharp edges, any subject
//   accurate  VNGeneratePersonSegmentationRequest .accurate: people only, softer edges
//   balanced  VNGeneratePersonSegmentationRequest .balanced (video-oriented, faster)
//   hybrid    the default in vlogkit: fg edges, but only where a person is (fg x dilated person
//             mask) + the person's solid interior near fg. Presence comes from fg: on an empty
//             curtain the person masks hallucinate soft blobs, fg correctly finds nothing.
import CoreImage
import CoreVideo
import Foundation
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 4, let W = Int(args[1]), let H = Int(args[2]) else {
    fail("usage: vlogkit-matte W H fg|accurate|balanced|hybrid")
}
let mode = args[3]
let frameBytes = W * H * 4
let context = CIContext(options: [.workingColorSpace: NSNull(), .outputColorSpace: NSNull()])
let rect = CGRect(x: 0, y: 0, width: W, height: H)
let sequence = VNSequenceRequestHandler()
let personRequest = VNGeneratePersonSegmentationRequest()
personRequest.qualityLevel = mode == "accurate" ? .accurate : .balanced
personRequest.outputPixelFormat = kCVPixelFormatType_OneComponent8

let stdin = FileHandle.standardInput
let stdout = FileHandle.standardOutput
var out = [UInt8](repeating: 0, count: W * H)

func readFrame() -> Data? {
    var data = Data(capacity: frameBytes)
    while data.count < frameBytes {
        let chunk = stdin.readData(ofLength: frameBytes - data.count)
        if chunk.isEmpty { return data.isEmpty ? nil : data }
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

/// A mask image scaled to exactly W x H.
func fit(_ mask: CIImage) -> CIImage {
    let sx = CGFloat(W) / mask.extent.width, sy = CGFloat(H) / mask.extent.height
    if abs(sx - 1) < 0.0001 && abs(sy - 1) < 0.0001 { return mask }
    return mask.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
}

func personMask(_ pb: CVPixelBuffer) -> CIImage? {
    do { try sequence.perform([personRequest], on: pb) } catch { return nil }
    guard let obs = personRequest.results?.first else { return nil }
    return fit(CIImage(cvPixelBuffer: obs.pixelBuffer))
}

func foregroundMask(_ pb: CVPixelBuffer) -> CIImage? {
    guard #available(macOS 14.0, *) else { return nil }
    let handler = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
    let request = VNGenerateForegroundInstanceMaskRequest()
    do {
        try handler.perform([request])
        guard let obs = request.results?.first else { return nil }
        let m = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler)
        return fit(CIImage(cvPixelBuffer: m))
    } catch { return nil }
}

let black = CIImage(color: CIColor(red: 0, green: 0, blue: 0)).cropped(to: rect)
let dilateRadius = Double(max(W, H)) * 0.015  // how far fg edges may reach past the person mask
let coreRadius = Double(max(W, H)) * 0.025  // person mask shrunk this much = surely inside
let nearRadius = Double(max(W, H)) * 0.03  // the core may only fill holes this close to fg
let maxHold = 2  // fg lost for a frame or two while someone was in frame: keep the last matte
var failed = false  // a Vision error (not "nobody in frame") repeats the last matte: no one-frame flash
var hold = 0
var lastHadSubject = false

func boost(_ img: CIImage, _ k: CGFloat) -> CIImage {
    img.applyingFilter("CIColorMatrix", parameters: [
        "inputRVector": CIVector(x: k, y: 0, z: 0, w: 0),
        "inputGVector": CIVector(x: 0, y: k, z: 0, w: 0),
        "inputBVector": CIVector(x: 0, y: 0, z: k, w: 0),
    ]).applyingFilter("CIColorClamp")
}

/// Cheap "is anything in this matte" check on the rendered bytes (every 7th pixel).
func hasSubject(_ m: [UInt8]) -> Bool {
    var n = 0
    var i = 0
    while i < m.count {
        if m[i] > 128 { n += 1; if n > 50 { return true } }
        i += 7
    }
    return false
}

while let data = readFrame() {
    if data.count < frameBytes { break }
    let pb = makeBuffer(data)
    var mask: CIImage?
    failed = false
    switch mode {
    case "fg":
        mask = foregroundMask(pb)  // nil also when nothing salient is in frame -> empty matte
    case "accurate", "balanced":
        mask = personMask(pb)
        failed = mask == nil
    default:  // hybrid: presence from fg (person masks hallucinate soft blobs on an empty curtain)
        guard let fg = foregroundMask(pb) else {
            if lastHadSubject && hold < maxHold {
                hold += 1
                failed = true  // repeat the last matte
            }
            break  // mask stays nil -> empty
        }
        hold = 0
        guard let person = personMask(pb) else { mask = fg; break }
        // clamped: the frame border must not count as "background" for the morphology
        let clamped = person.clampedToExtent()
        // the gate says only "a person is here": x4 + clamp, because the person mask fades
        // softly where the body leaves the frame (a see-through sweater at the bottom otherwise)
        let grown = boost(clamped, 4).applyingFilter("CIMorphologyMaximum", parameters: ["inputRadius": dilateRadius])
            .cropped(to: rect)
        // the person's deep interior is solid (fills holes in fg), but only near fg: never a blob
        let near = fg.clampedToExtent().applyingFilter("CIMorphologyMaximum", parameters: ["inputRadius": nearRadius])
            .cropped(to: rect)
        let core = clamped.applyingFilter("CIMorphologyMinimum", parameters: ["inputRadius": coreRadius])
            .cropped(to: rect)
            .applyingFilter("CIMultiplyCompositing", parameters: [kCIInputBackgroundImageKey: near])
        mask = fg.applyingFilter("CIMultiplyCompositing", parameters: [kCIInputBackgroundImageKey: grown])
            .applyingFilter("CIMaximumCompositing", parameters: [kCIInputBackgroundImageKey: core])
    }
    if !failed {
        let image = (mask ?? black).cropped(to: rect)
        out.withUnsafeMutableBytes { ptr in
            context.render(image, toBitmap: ptr.baseAddress!, rowBytes: W, bounds: rect, format: .L8, colorSpace: nil)
        }
        lastHadSubject = mask != nil && hasSubject(out)
    }
    // Rendering to a bitmap writes rows top-down, like the raw frames: no flip (checked on footage).
    out.withUnsafeBytes { stdout.write(Data($0)) }
}
