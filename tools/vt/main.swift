// vlogkit-vt: Apple VideoToolbox frame processing for vlogkit (macOS 26+, Apple silicon).
//
//   vlogkit-vt info
//   vlogkit-vt upscale     IN OUT [--scale 4] [--denoise] [--strength 0.5] [--codec prores|hevc]
//   vlogkit-vt denoise     IN OUT [--strength 0.5]
//   vlogkit-vt interpolate IN OUT [--factor 2] [--slowmo]
//   vlogkit-vt motionblur  IN OUT [--blur 50]
//
// Video only: the Python side (vlogkit.video.vt) muxes the audio back. Frames keep their
// presentation times (upscale / denoise / motionblur); interpolate writes factor x frames,
// either at factor x the frame rate (same duration) or, with --slowmo, at the source rate.
// Output: ProRes 422 HQ .mov (10-bit, what the rest of vlogkit uses), or HEVC with --codec hevc.
// Built on demand by vlogkit.video.vt.ensure_built() (swiftc -O -swift-version 5).

import AVFoundation
import CoreMedia
import CoreVideo
import Foundation
import VideoToolbox

struct Failure: Error, CustomStringConvertible {
    let description: String
    init(_ s: String) { description = s }
}

func log(_ s: String) { FileHandle.standardError.write((s + "\n").data(using: .utf8)!) }

/// Processors that use optical flow (frame rate conversion, motion blur) crash while being torn
/// down on macOS 26.4 (CFRelease inside DeepVideoProcessingCore's VEOpticalFlowEstimator
/// dealloc, after all frames are done). They are never ended or released: the file is finished
/// first and the process exits right after.
nonisolated(unsafe) var keepAlive: [AnyObject] = []

// MARK: - arguments

struct Options {
    var command = ""
    var input: URL?
    var output: URL?
    var scale = 4
    var denoise = false
    var strength: Float = 0.5
    var factor = 2
    var slowmo = false
    var blur = 50
    var codec = "prores"
}

func parse(_ argv: [String]) throws -> Options {
    var o = Options()
    var rest = Array(argv.dropFirst())
    guard !rest.isEmpty else { throw Failure("usage: vlogkit-vt info|upscale|denoise|interpolate|motionblur IN OUT [options]") }
    o.command = rest.removeFirst()
    var positional: [String] = []
    var i = 0
    func value() throws -> String {
        i += 1
        guard i < rest.count else { throw Failure("missing value for \(rest[i - 1])") }
        return rest[i]
    }
    while i < rest.count {
        switch rest[i] {
        case "--scale": o.scale = Int(try value()) ?? 4
        case "--denoise": o.denoise = true
        case "--strength": o.strength = Float(try value()) ?? 0.5
        case "--factor": o.factor = Int(try value()) ?? 2
        case "--slowmo": o.slowmo = true
        case "--blur": o.blur = Int(try value()) ?? 50
        case "--codec": o.codec = try value()
        default: positional.append(rest[i])
        }
        i += 1
    }
    if o.command != "info" {
        guard positional.count == 2 else { throw Failure("\(o.command): IN and OUT are required") }
        o.input = URL(fileURLWithPath: positional[0])
        o.output = URL(fileURLWithPath: positional[1])
    }
    return o
}

// MARK: - pixel buffers

func makePool(_ attributes: [String: Any]) throws -> CVPixelBufferPool {
    var pool: CVPixelBufferPool?
    let st = CVPixelBufferPoolCreate(kCFAllocatorDefault, nil, attributes as CFDictionary, &pool)
    guard st == kCVReturnSuccess, let pool else { throw Failure("CVPixelBufferPoolCreate failed (\(st))") }
    return pool
}

func newBuffer(_ pool: CVPixelBufferPool) throws -> CVPixelBuffer {
    var pb: CVPixelBuffer?
    let st = CVPixelBufferPoolCreatePixelBuffer(kCFAllocatorDefault, pool, &pb)
    guard st == kCVReturnSuccess, let pb else { throw Failure("CVPixelBufferPoolCreatePixelBuffer failed (\(st))") }
    return pb
}

/// Copies/converts decoded frames into buffers a processor accepts (format, IOSurface backing).
final class Converter {
    let session: VTPixelTransferSession
    let pool: CVPixelBufferPool
    let tags: [String: Any]?  // colour tags of the destination: the transfer converts into them
    init(attributes: [String: Any], tags: [String: Any]? = nil) throws {
        self.tags = tags
        var s: VTPixelTransferSession?
        let st = VTPixelTransferSessionCreate(allocator: kCFAllocatorDefault, pixelTransferSessionOut: &s)
        guard st == noErr, let s else { throw Failure("VTPixelTransferSessionCreate failed (\(st))") }
        session = s
        pool = try makePool(attributes)
    }
    func convert(_ src: CVPixelBuffer) throws -> CVPixelBuffer {
        let dst = try newBuffer(pool)
        if let tags { CVBufferSetAttachments(dst, tags as CFDictionary, .shouldPropagate) }
        let st = VTPixelTransferSessionTransferImage(session, from: src, to: dst)
        guard st == noErr else { throw Failure("pixel transfer failed (\(st))") }
        if tags == nil { CVBufferPropagateAttachments(src, dst) }
        return dst
    }
}

func osType(_ s: String) -> OSType { s.utf8.reduce(0) { ($0 << 8) | OSType($1) } }

/// BT.709 colour tags (what the phones and the rest of vlogkit use). The processors' tone does
/// not depend on them (checked: linear vs 709 tags on the half-float input give the same
/// result); the super resolution model itself shifts the tone a little, which the Python side
/// measures and corrects.
func rec709() -> [String: Any] {
    [
        kCVImageBufferColorPrimariesKey as String: kCVImageBufferColorPrimaries_ITU_R_709_2,
        kCVImageBufferTransferFunctionKey as String: kCVImageBufferTransferFunction_ITU_R_709_2,
        kCVImageBufferYCbCrMatrixKey as String: kCVImageBufferYCbCrMatrix_ITU_R_709_2,
    ]
}

/// 10-bit 4:2:2, what the ProRes 422 HQ encoder wants.
func writerAttributes(_ w: Int, _ h: Int) -> [String: Any] {
    [
        kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_422YpCbCr10BiPlanarVideoRange,
        kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h,
        kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
    ]
}

func frame(_ pb: CVPixelBuffer, _ t: CMTime) throws -> VTFrameProcessorFrame {
    guard let f = VTFrameProcessorFrame(buffer: pb, presentationTimeStamp: t) else {
        throw Failure("VTFrameProcessorFrame init failed")
    }
    return f
}

func run(_ processor: VTFrameProcessor, _ parameters: any VTFrameProcessorParameters) throws {
    let done = DispatchSemaphore(value: 0)
    var failure: Error?
    processor.process(parameters: parameters) { _, error in
        failure = error
        done.signal()
    }
    done.wait()
    if let failure { throw Failure("frame processing failed: \(failure)") }
}

// MARK: - reading / writing

final class Reader {
    let reader: AVAssetReader
    let output: AVAssetReaderTrackOutput
    let width: Int
    let height: Int
    let frameDuration: CMTime
    let estimatedFrames: Int
    private var origin: CMTime?

    init(url: URL) async throws {
        let asset = AVURLAsset(url: url)
        guard let track = try await asset.loadTracks(withMediaType: .video).first else {
            throw Failure("no video track in \(url.path)")
        }
        let (size, transform, rate, minDuration) = try await track.load(
            .naturalSize, .preferredTransform, .nominalFrameRate, .minFrameDuration)
        guard transform.isIdentity else {
            throw Failure("rotated source (preferredTransform); render it upright with ffmpeg first")
        }
        width = Int(size.width.rounded())
        height = Int(size.height.rounded())
        frameDuration = minDuration.isValid && minDuration.seconds > 0
            ? minDuration : CMTime(value: 1001, timescale: 30000)
        let duration = try await asset.load(.duration)
        estimatedFrames = max(1, Int((duration.seconds * Double(rate > 0 ? rate : 30)).rounded()))
        reader = try AVAssetReader(asset: asset)
        output = AVAssetReaderTrackOutput(track: track, outputSettings: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange,
            kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
        ])
        output.alwaysCopiesSampleData = false
        reader.add(output)
        guard reader.startReading() else { throw Failure("cannot read \(url.path): \(String(describing: reader.error))") }
    }

    /// Next decoded frame with its time relative to the first frame (output starts at 0).
    func next() -> (CVPixelBuffer, CMTime)? {
        while let sample = output.copyNextSampleBuffer() {
            guard let pb = CMSampleBufferGetImageBuffer(sample) else { continue }
            let t = CMSampleBufferGetPresentationTimeStamp(sample)
            if origin == nil { origin = t }
            return (pb, CMTimeSubtract(t, origin!))
        }
        return nil
    }
}

final class Writer {
    let writer: AVAssetWriter
    let input: AVAssetWriterInput
    let adaptor: AVAssetWriterInputPixelBufferAdaptor
    private(set) var count = 0
    let expected: Int

    init(url: URL, width: Int, height: Int, codec: String, expected: Int) throws {
        try? FileManager.default.removeItem(at: url)
        writer = try AVAssetWriter(outputURL: url, fileType: .mov)
        var settings: [String: Any] = [
            AVVideoWidthKey: width,
            AVVideoHeightKey: height,
            AVVideoColorPropertiesKey: [
                AVVideoColorPrimariesKey: AVVideoColorPrimaries_ITU_R_709_2,
                AVVideoTransferFunctionKey: AVVideoTransferFunction_ITU_R_709_2,
                AVVideoYCbCrMatrixKey: AVVideoYCbCrMatrix_ITU_R_709_2,
            ],
        ]
        if codec == "hevc" {
            settings[AVVideoCodecKey] = AVVideoCodecType.hevc
            settings[AVVideoCompressionPropertiesKey] = [AVVideoAverageBitRateKey: width * height * 30 / 2]
        } else {
            settings[AVVideoCodecKey] = AVVideoCodecType.proRes422HQ
        }
        input = AVAssetWriterInput(mediaType: .video, outputSettings: settings)
        input.expectsMediaDataInRealTime = false
        adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: nil)
        guard writer.canAdd(input) else { throw Failure("writer rejects \(codec) \(width)x\(height)") }
        writer.add(input)
        guard writer.startWriting() else { throw Failure("cannot write \(url.path): \(String(describing: writer.error))") }
        writer.startSession(atSourceTime: .zero)
        self.expected = expected
    }

    func append(_ pb: CVPixelBuffer, _ t: CMTime) throws {
        while !input.isReadyForMoreMediaData { usleep(500) }
        guard adaptor.append(pb, withPresentationTime: t) else {
            throw Failure("append failed at \(t.seconds)s: \(String(describing: writer.error))")
        }
        count += 1
        if count % 30 == 0 || count == expected { log("frame \(count)/\(expected)") }
    }

    func finish() throws {
        input.markAsFinished()
        let done = DispatchSemaphore(value: 0)
        writer.finishWriting { done.signal() }
        done.wait()
        guard writer.status == .completed else { throw Failure("finish failed: \(String(describing: writer.error))") }
    }
}

// MARK: - processing stages

protocol Stage: AnyObject {
    func push(_ f: VTFrameProcessorFrame) throws
    func finish() throws
}

/// Converts frames to what the next stage accepts (formats differ: the ML processors work in
/// half-float RGBA 'RGhA', the noise filter in compressed 4:2:0, the encoder in 10-bit 4:2:2).
final class Convert: Stage {
    let converter: Converter
    let next: Stage
    init(_ attributes: [String: Any], tags: [String: Any]? = nil, next: Stage) throws {
        converter = try Converter(attributes: attributes, tags: tags)
        self.next = next
    }
    func push(_ f: VTFrameProcessorFrame) throws {
        try next.push(try frame(try converter.convert(f.buffer), f.presentationTimeStamp))
    }
    func finish() throws { try next.finish() }
}

/// End of the chain: frames go to the file with their own presentation times.
final class Sink: Stage {
    let writer: Writer
    init(_ writer: Writer) { self.writer = writer }
    func push(_ f: VTFrameProcessorFrame) throws { try writer.append(f.buffer, f.presentationTimeStamp) }
    func finish() throws { try writer.finish() }
}

/// ML super resolution. Sequential video mode: each frame also sees the previous input and output.
final class SuperResolution: Stage {
    let processor = VTFrameProcessor()
    let config: VTSuperResolutionScalerConfiguration
    let inPool: CVPixelBufferPool
    let outPool: CVPixelBufferPool
    let next: Stage
    private var previous: VTFrameProcessorFrame?
    private var previousOut: VTFrameProcessorFrame?

    init(width: Int, height: Int, scale: Int, next: Stage) throws {
        guard VTSuperResolutionScalerConfiguration.isSupported else { throw Failure("super resolution not supported on this Mac") }
        guard width <= 1920, height <= 1080 || (height <= 1920 && width <= 1080) else {
            throw Failure("super resolution input must be at most 1920x1080 (got \(width)x\(height))")
        }
        guard let c = VTSuperResolutionScalerConfiguration(
            frameWidth: width, frameHeight: height, scaleFactor: scale, inputType: .video,
            usePrecomputedFlow: false, qualityPrioritization: .normal,
            revision: VTSuperResolutionScalerConfiguration.defaultRevision)
        else { throw Failure("no super resolution configuration for \(width)x\(height) x\(scale)") }
        config = c
        try SuperResolution.ensureModel(c)
        try processor.startSession(configuration: c)
        inPool = try makePool(c.sourcePixelBufferAttributes)
        outPool = try makePool(c.destinationPixelBufferAttributes)
        self.next = next
    }

    /// The ML model is downloaded by the system on first use.
    static func ensureModel(_ c: VTSuperResolutionScalerConfiguration) throws {
        if c.configurationModelStatus == .ready { return }
        log("downloading the super resolution model…")
        let done = DispatchSemaphore(value: 0)
        var failure: Error?
        c.downloadConfigurationModel { error in failure = error; done.signal() }
        while done.wait(timeout: .now() + 5) == .timedOut {
            log(String(format: "model %.0f%%", c.configurationModelPercentageAvailable * 100))
        }
        if let failure { throw Failure("model download failed: \(failure)") }
        guard c.configurationModelStatus == .ready else { throw Failure("model not ready after download") }
    }

    func push(_ f: VTFrameProcessorFrame) throws {
        let dst = try frame(try newBuffer(outPool), f.presentationTimeStamp)
        guard let p = VTSuperResolutionScalerParameters(
            sourceFrame: f, previousFrame: previous, previousOutputFrame: previousOut,
            opticalFlow: nil, submissionMode: .sequential, destinationFrame: dst)
        else { throw Failure("super resolution parameters rejected") }
        try run(processor, p)
        CVBufferPropagateAttachments(f.buffer, dst.buffer)
        previous = f
        previousOut = dst
        try next.push(dst)
    }

    func finish() throws {
        processor.endSession()
        try next.finish()
    }
}

/// Temporal noise filter: needs a few frames before and after the current one.
final class Denoise: Stage {
    let processor = VTFrameProcessor()
    let config: VTTemporalNoiseFilterConfiguration
    let outPool: CVPixelBufferPool
    let strength: Float
    let next: Stage
    let prevCount: Int
    let nextCount: Int
    private var window: [VTFrameProcessorFrame] = []  // previous..current..next
    private var current = 0  // index of the next frame to filter within `window`

    init(width: Int, height: Int, format: OSType, strength: Float, next: Stage) throws {
        guard VTTemporalNoiseFilterConfiguration.isSupported else { throw Failure("temporal noise filter not supported") }
        guard let c = VTTemporalNoiseFilterConfiguration(frameWidth: width, frameHeight: height, sourcePixelFormat: format)
        else { throw Failure("no noise filter configuration for \(width)x\(height)") }
        config = c
        let pc: Int? = c.previousFrameCount
        let nc: Int? = c.nextFrameCount
        prevCount = pc ?? 2
        nextCount = nc ?? 2
        try processor.startSession(configuration: c)
        outPool = try makePool(c.destinationPixelBufferAttributes)
        self.strength = strength
        self.next = next
    }

    private func filter(at i: Int) throws {
        let lo = max(0, i - prevCount)
        let hi = min(window.count, i + 1 + nextCount)
        let prev = Array(window[lo..<i])
        let nxt = Array(window[(i + 1)..<hi])
        let src = window[i]
        let dst = try frame(try newBuffer(outPool), src.presentationTimeStamp)
        guard let p = VTTemporalNoiseFilterParameters(
            sourceFrame: src, nextFrames: nxt, previousFrames: prev, destinationFrame: dst,
            filterStrength: strength, hasDiscontinuity: false)
        else { throw Failure("noise filter parameters rejected") }
        try run(processor, p)
        CVBufferPropagateAttachments(src.buffer, dst.buffer)
        try next.push(dst)
    }

    func push(_ f: VTFrameProcessorFrame) throws {
        window.append(f)
        while current + nextCount < window.count {
            try filter(at: current)
            current += 1
            let drop = max(0, current - prevCount)
            if drop > 0 { window.removeFirst(drop); current -= drop }
        }
    }

    func finish() throws {
        while current < window.count {  // the last frames have fewer "next" frames
            try filter(at: current)
            current += 1
        }
        processor.endSession()
        try next.finish()
    }
}

/// Frame rate conversion: (factor - 1) new frames between every pair; the last frame is held.
final class Interpolate: Stage {
    let processor = VTFrameProcessor()
    let config: VTFrameRateConversionConfiguration
    let outPool: CVPixelBufferPool
    let factor: Int
    let step: CMTime  // time between output frames
    let next: Stage
    private var previous: VTFrameProcessorFrame?
    private var index = 0

    init(width: Int, height: Int, factor: Int, frameDuration: CMTime, slowmo: Bool, next: Stage) throws {
        guard VTFrameRateConversionConfiguration.isSupported else { throw Failure("frame rate conversion not supported") }
        guard let c = VTFrameRateConversionConfiguration(
            frameWidth: width, frameHeight: height, usePrecomputedFlow: false,
            qualityPrioritization: .quality, revision: VTFrameRateConversionConfiguration.defaultRevision)
        else { throw Failure("no frame rate conversion configuration for \(width)x\(height)") }
        config = c
        try processor.startSession(configuration: c)
        outPool = try makePool(c.destinationPixelBufferAttributes)
        self.factor = factor
        step = slowmo ? frameDuration : CMTimeMultiplyByRatio(frameDuration, multiplier: 1, divisor: Int32(factor))
        self.next = next
    }

    private func emit(_ pb: CVPixelBuffer) throws {
        try next.push(try frame(pb, CMTimeMultiply(step, multiplier: Int32(index))))
        index += 1
    }

    func push(_ f: VTFrameProcessorFrame) throws {
        defer { previous = f }
        guard let a = previous else { return }
        let phases = (1..<factor).map { Float($0) / Float(factor) }
        let dsts = try phases.map { _ in try frame(try newBuffer(outPool), a.presentationTimeStamp) }
        guard let p = VTFrameRateConversionParameters(
            sourceFrame: a, nextFrame: f, opticalFlow: nil, interpolationPhase: phases,
            submissionMode: .sequential, destinationFrames: dsts)
        else { throw Failure("frame rate conversion parameters rejected") }
        try run(processor, p)
        for d in dsts { CVBufferPropagateAttachments(a.buffer, d.buffer) }
        try emit(a.buffer)
        for d in dsts { try emit(d.buffer) }
    }

    func finish() throws {
        if let last = previous {
            for _ in 0..<factor { try emit(last.buffer) }  // exactly factor x the input frames
        }
        keepAlive.append(processor)  // see keepAlive: no endSession / dealloc
        try next.finish()
    }
}

/// Motion blur from the motion between neighbouring frames (strength 1-100).
final class MotionBlur: Stage {
    let processor = VTFrameProcessor()
    let config: VTMotionBlurConfiguration
    let outPool: CVPixelBufferPool
    let strength: Int
    let next: Stage
    private var frames: [VTFrameProcessorFrame] = []

    init(width: Int, height: Int, strength: Int, next: Stage) throws {
        guard VTMotionBlurConfiguration.isSupported else { throw Failure("motion blur not supported") }
        guard let c = VTMotionBlurConfiguration(
            frameWidth: width, frameHeight: height, usePrecomputedFlow: false,
            qualityPrioritization: .quality, revision: VTMotionBlurConfiguration.defaultRevision)
        else { throw Failure("no motion blur configuration for \(width)x\(height)") }
        config = c
        try processor.startSession(configuration: c)
        outPool = try makePool(c.destinationPixelBufferAttributes)
        self.strength = max(1, min(100, strength))
        self.next = next
    }

    private func blur(_ src: VTFrameProcessorFrame, prev: VTFrameProcessorFrame?, nxt: VTFrameProcessorFrame?) throws {
        let dst = try frame(try newBuffer(outPool), src.presentationTimeStamp)
        guard let p = VTMotionBlurParameters(
            sourceFrame: src, nextFrame: nxt, previousFrame: prev, nextOpticalFlow: nil,
            previousOpticalFlow: nil, motionBlurStrength: strength, submissionMode: .sequential,
            destinationFrame: dst)
        else { throw Failure("motion blur parameters rejected") }
        try run(processor, p)
        CVBufferPropagateAttachments(src.buffer, dst.buffer)
        try next.push(dst)
    }

    func push(_ f: VTFrameProcessorFrame) throws {
        frames.append(f)
        if frames.count == 2 { try blur(frames[0], prev: nil, nxt: frames[1]) }
        if frames.count == 3 {
            try blur(frames[1], prev: frames[0], nxt: frames[2])
            frames.removeFirst()
        }
    }

    func finish() throws {
        if frames.count == 1 { try blur(frames[0], prev: nil, nxt: nil) }
        if frames.count == 2 { try blur(frames[1], prev: frames[0], nxt: nil) }
        keepAlive.append(processor)  // see keepAlive: no endSession / dealloc
        try next.finish()
    }
}

// MARK: - commands

func fourcc(_ t: OSType) -> String {
    let bytes = [24, 16, 8, 0].map { UInt8((t >> UInt32($0)) & 0xff) }
    return String(bytes: bytes, encoding: .ascii) ?? "\(t)"
}

func info() {
    let v = ProcessInfo.processInfo.operatingSystemVersion
    var sr: [String: Any] = ["supported": VTSuperResolutionScalerConfiguration.isSupported]
    if VTSuperResolutionScalerConfiguration.isSupported {
        sr["scales"] = VTSuperResolutionScalerConfiguration.supportedScaleFactors
        if let c = VTSuperResolutionScalerConfiguration(
            frameWidth: 640, frameHeight: 360, scaleFactor: 4, inputType: .video, usePrecomputedFlow: false,
            qualityPrioritization: .normal, revision: VTSuperResolutionScalerConfiguration.defaultRevision) {
            sr["model"] = ["downloadRequired", "downloading", "ready"][max(0, min(2, c.configurationModelStatus.rawValue))]
            sr["formats"] = c.supportedPixelFormats.map(fourcc)
        }
    }
    let out: [String: Any] = [
        "macos": "\(v.majorVersion).\(v.minorVersion).\(v.patchVersion)",
        "super_resolution": sr,
        "max_input": [1920, 1080],
        "frame_rate_conversion": VTFrameRateConversionConfiguration.isSupported,
        "frame_rate_conversion_formats": VTFrameRateConversionConfiguration(
            frameWidth: 640, frameHeight: 360, usePrecomputedFlow: false, qualityPrioritization: .quality,
            revision: VTFrameRateConversionConfiguration.defaultRevision)?.supportedPixelFormats.map(fourcc) ?? [],
        "motion_blur_formats": VTMotionBlurConfiguration(
            frameWidth: 640, frameHeight: 360, usePrecomputedFlow: false, qualityPrioritization: .quality,
            revision: VTMotionBlurConfiguration.defaultRevision)?.supportedPixelFormats.map(fourcc) ?? [],
        "temporal_noise_filter": VTTemporalNoiseFilterConfiguration.isSupported,
        "temporal_noise_filter_formats": VTTemporalNoiseFilterConfiguration.isSupported
            ? VTTemporalNoiseFilterConfiguration.supportedSourcePixelFormats.map(fourcc) : [],
        "motion_blur": VTMotionBlurConfiguration.isSupported,
    ]
    let data = try! JSONSerialization.data(withJSONObject: out, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

func process(_ o: Options) async throws {
    let reader = try await Reader(url: o.input!)
    let w = reader.width, h = reader.height
    var outW = w, outH = h, expected = reader.estimatedFrames
    switch o.command {
    case "upscale": outW = w * o.scale; outH = h * o.scale
    case "interpolate": expected *= o.factor
    case "denoise", "motionblur", "roundtrip": break
    default: throw Failure("unknown command \(o.command)")
    }
    let writer = try Writer(url: o.output!, width: outW, height: outH, codec: o.codec, expected: expected)
    let sink = try Convert(writerAttributes(outW, outH), tags: rec709(), next: Sink(writer))

    // Build the chain back to front; `inAttributes` = what its first stage wants as input.
    var head: Stage
    var inAttributes: [String: Any]
    let noiseFormat = osType("&xv0")  // lossless-compressed 10-bit 4:2:0 (the filter's own formats)
    switch o.command {
    case "upscale":
        let sr = try SuperResolution(width: w, height: h, scale: o.scale, next: sink)
        head = sr
        inAttributes = sr.config.sourcePixelBufferAttributes
        if o.denoise {
            let toSR = try Convert(sr.config.sourcePixelBufferAttributes, tags: rec709(), next: sr)
            let dn = try Denoise(width: w, height: h, format: noiseFormat, strength: o.strength, next: toSR)
            head = dn
            inAttributes = dn.config.sourcePixelBufferAttributes
        }
    case "denoise":
        let dn = try Denoise(width: w, height: h, format: noiseFormat, strength: o.strength, next: sink)
        head = dn
        inAttributes = dn.config.sourcePixelBufferAttributes
    case "roundtrip":  // debug: decode -> RGhA -> encode, no processing (checks the conversions)
        inAttributes = [
            kCVPixelBufferPixelFormatTypeKey as String: osType("RGhA"),
            kCVPixelBufferWidthKey as String: w, kCVPixelBufferHeightKey as String: h,
            kCVPixelBufferIOSurfacePropertiesKey as String: [String: Any](),
        ]
        head = sink
    case "interpolate":
        let ip = try Interpolate(width: w, height: h, factor: max(2, o.factor), frameDuration: reader.frameDuration,
                                 slowmo: o.slowmo, next: sink)
        head = ip
        inAttributes = ip.config.sourcePixelBufferAttributes
    default:
        let mb = try MotionBlur(width: w, height: h, strength: o.blur, next: sink)
        head = mb
        inAttributes = mb.config.sourcePixelBufferAttributes
    }
    let convert = try Converter(attributes: inAttributes, tags: rec709())
    let started = Date()
    var n = 0
    while let (pb, t) = reader.next() {
        try head.push(try frame(try convert.convert(pb), t))
        n += 1
    }
    try head.finish()
    let secs = Date().timeIntervalSince(started)
    log(String(format: "done: %d input frames -> %d output frames in %.1f s (%.1f input fps)",
               n, writer.count, secs, Double(n) / max(secs, 0.001)))
}

do {
    let o = try parse(CommandLine.arguments)
    if o.command == "info" { info() } else { try await process(o) }
    exit(0)  // skip tearing down the processors (see keepAlive)
} catch {
    log("error: \(error)")
    exit(1)
}
