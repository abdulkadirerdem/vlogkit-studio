// vlogkit-segment: subject / person mask of an image with Apple's Vision framework.
//
//   vlogkit-segment IN OUT.png [--person] [--largest]
//
// Default: the foreground subject mask Photos uses for "lift subject" (macOS 14+,
// VNGenerateForegroundInstanceMaskRequest), at full image resolution: hair, hands and anything
// the person holds stay in. --largest: only the biggest subject (the creator in front, not the
// friends behind). --person: VNGeneratePersonSegmentationRequest (accurate), people only.
// OUT is an 8-bit grayscale PNG the size of IN (255 = subject).
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

func fail(_ msg: String) -> Never {
    FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
    exit(1)
}

let args = CommandLine.arguments
guard args.count >= 3 else { fail("usage: vlogkit-segment IN OUT.png [--person]") }
let input = URL(fileURLWithPath: args[1])
let output = URL(fileURLWithPath: args[2])
let personOnly = args.contains("--person")
let largestOnly = args.contains("--largest")

guard let src = CGImageSourceCreateWithURL(input as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(src, 0, nil)
else { fail("cannot read \(input.path)") }

let handler = VNImageRequestHandler(cgImage: image, options: [:])
var buffer: CVPixelBuffer? = nil
do {
    if !personOnly, #available(macOS 14.0, *) {
        let request = VNGenerateForegroundInstanceMaskRequest()
        try handler.perform([request])
        guard let obs = request.results?.first else { fail("no subject found") }
        var instances = obs.allInstances
        if largestOnly && instances.count > 1 {
            // the instance mask labels each pixel with its instance index (0 = background)
            let labels = obs.instanceMask
            CVPixelBufferLockBaseAddress(labels, .readOnly)
            let w = CVPixelBufferGetWidth(labels), h = CVPixelBufferGetHeight(labels)
            let row = CVPixelBufferGetBytesPerRow(labels)
            let base = CVPixelBufferGetBaseAddress(labels)!.assumingMemoryBound(to: UInt8.self)
            var counts = [Int: Int]()
            for y in 0..<h { for x in 0..<w { let v = Int(base[y * row + x]); if v > 0 { counts[v, default: 0] += 1 } } }
            CVPixelBufferUnlockBaseAddress(labels, .readOnly)
            if let best = counts.max(by: { $0.value < $1.value })?.key { instances = IndexSet(integer: best) }
        }
        buffer = try obs.generateScaledMaskForImage(forInstances: instances, from: handler)
    } else {
        let request = VNGeneratePersonSegmentationRequest()
        request.qualityLevel = .accurate
        request.outputPixelFormat = kCVPixelFormatType_OneComponent8
        try handler.perform([request])
        guard let obs = request.results?.first else { fail("no person found") }
        buffer = obs.pixelBuffer
    }
} catch {
    fail("vision failed: \(error)")
}

var mask = CIImage(cvPixelBuffer: buffer!)
let sx = CGFloat(image.width) / mask.extent.width
let sy = CGFloat(image.height) / mask.extent.height
if abs(sx - 1) > 0.001 || abs(sy - 1) > 0.001 {
    mask = mask.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
}
let context = CIContext()
let rect = CGRect(x: 0, y: 0, width: image.width, height: image.height)
guard let gray = CGColorSpace(name: CGColorSpace.linearGray),
      let out = context.createCGImage(mask, from: rect, format: .L8, colorSpace: gray)
else { fail("cannot render mask") }
guard let dest = CGImageDestinationCreateWithURL(output as CFURL, UTType.png.identifier as CFString, 1, nil)
else { fail("cannot write \(output.path)") }
CGImageDestinationAddImage(dest, out, nil)
if !CGImageDestinationFinalize(dest) { fail("cannot write \(output.path)") }
