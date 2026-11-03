import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count > 1 else {
    print("")
    exit(0)
}

let imagePath = CommandLine.arguments[1]
guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    print("")
    exit(1)
}

let request = VNRecognizeTextRequest { request, error in
    guard let observations = request.results as? [VNRecognizedTextObservation] else { return }
    let strings = observations.compactMap { $0.topCandidates(1).first?.string }
    print(strings.joined(separator: " "))
}

request.recognitionLevel = .accurate
request.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
try? handler.perform([request])
