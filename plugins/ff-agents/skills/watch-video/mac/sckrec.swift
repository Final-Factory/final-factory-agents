// sckrec: record one process's largest window with ScreenCaptureKit (works while the window is
// covered). record_clip.py compiles it once into ~/.cache/watch_video/bin/sckrec.
// usage: sckrec <pid> <out.mov> <seconds> [fps=60]
// Prints "RECORDING" once the first frame is written, so the caller can fire the effect then.
// Needs the Screen Recording permission for the app that runs it (the terminal / agent host).
import Foundation
import ScreenCaptureKit
import AVFoundation
import CoreMedia
import AppKit

let a = CommandLine.arguments
guard a.count >= 4, Int32(a[1]) != nil, Double(a[3]) != nil else {
  print("usage: sckrec <pid> <out.mov> <seconds> [fps]"); exit(2)
}
let wantPid = Int32(a[1])!
let secs = Double(a[3])!
let outURL = URL(fileURLWithPath: a[2])
let fps = a.count > 4 ? Int32(a[4]) ?? 60 : 60

final class Rec: NSObject, SCStreamOutput {
  var writer: AVAssetWriter!
  var input: AVAssetWriterInput!
  var started = false
  var frames = 0
  var stream: SCStream!

  func start() async throws {
    let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
    let wins = content.windows.filter {
      $0.owningApplication?.processID == wantPid && $0.frame.width > 300 && $0.frame.height > 200
    }
    guard let w = wins.max(by: { $0.frame.width * $0.frame.height < $1.frame.width * $1.frame.height }) else {
      print("no window for pid \(wantPid)"); exit(3)
    }
    let scale = NSScreen.main?.backingScaleFactor ?? 2.0
    let W = Int(w.frame.width * scale) & ~1, H = Int(w.frame.height * scale) & ~1
    print("window \(w.windowID) '\(w.title ?? "")' \(W)x\(H)")
    let cfg = SCStreamConfiguration()
    cfg.width = W; cfg.height = H
    cfg.minimumFrameInterval = CMTime(value: 1, timescale: fps)
    cfg.showsCursor = false; cfg.queueDepth = 8; cfg.pixelFormat = kCVPixelFormatType_32BGRA
    cfg.ignoreShadowsSingleWindow = true
    writer = try AVAssetWriter(outputURL: outURL, fileType: .mov)
    input = AVAssetWriterInput(mediaType: .video, outputSettings: [
      AVVideoCodecKey: AVVideoCodecType.hevc, AVVideoWidthKey: W, AVVideoHeightKey: H,
      AVVideoCompressionPropertiesKey: [AVVideoAverageBitRateKey: 60_000_000,
                                        AVVideoExpectedSourceFrameRateKey: fps]])
    input.expectsMediaDataInRealTime = true
    writer.add(input)
    stream = SCStream(filter: SCContentFilter(desktopIndependentWindow: w), configuration: cfg, delegate: nil)
    try stream.addStreamOutput(self, type: .screen, sampleHandlerQueue: DispatchQueue(label: "rec"))
    try await stream.startCapture()
  }

  func stream(_ s: SCStream, didOutputSampleBuffer sb: CMSampleBuffer, of type: SCStreamOutputType) {
    // only frames with new content; an unchanged window sends none, and the 60 fps conversion
    // afterwards repeats the last frame (so a repeat can be the game's own, or a capture gap)
    guard type == .screen, sb.isValid,
      let att = CMSampleBufferGetSampleAttachmentsArray(sb, createIfNecessary: false) as? [[SCStreamFrameInfo: Any]],
      let raw = att.first?[.status] as? Int, let st = SCFrameStatus(rawValue: raw), st == .complete else { return }
    if !started {
      writer.startWriting(); writer.startSession(atSourceTime: sb.presentationTimeStamp); started = true
      print("RECORDING"); fflush(stdout)
    }
    if input.isReadyForMoreMediaData { input.append(sb); frames += 1 }
  }

  func stop() async {
    try? await stream.stopCapture()
    if started { input.markAsFinished(); await writer.finishWriting() }
    print("wrote \(frames) frames to \(outURL.path) status=\(writer.status.rawValue)")
  }
}

_ = NSApplication.shared
let r = Rec()
var stopRequested = false
signal(SIGINT, SIG_IGN)
let sigSrc = DispatchSource.makeSignalSource(signal: SIGINT, queue: .main)
sigSrc.setEventHandler { stopRequested = true }
sigSrc.resume()
Task {
  do { try await r.start() } catch { print("start error: \(error)"); exit(4) }
  let t0 = Date()
  while Date().timeIntervalSince(t0) < secs && !stopRequested { try? await Task.sleep(nanoseconds: 50_000_000) }
  await r.stop()
  exit(0)
}
dispatchMain()
