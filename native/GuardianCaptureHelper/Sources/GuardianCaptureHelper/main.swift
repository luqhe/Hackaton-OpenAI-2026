import AppKit
import CoreMedia
import Foundation
import ScreenCaptureKit

enum CaptureError: LocalizedError {
    case displayUnavailable
    case pngEncodingFailed

    var errorDescription: String? {
        switch self {
        case .displayUnavailable:
            return "No capturable display is available."
        case .pngEncodingFailed:
            return "The captured frame could not be encoded as PNG."
        }
    }
}

struct ScreenCaptureService {
    func capturePrimaryDisplay(to destination: URL) async throws {
        let content = try await SCShareableContent.excludingDesktopWindows(
            false,
            onScreenWindowsOnly: true
        )
        guard let display = content.displays.first else {
            throw CaptureError.displayUnavailable
        }

        let configuration = SCStreamConfiguration()
        configuration.width = display.width
        configuration.height = display.height
        configuration.pixelFormat = kCVPixelFormatType_32BGRA
        configuration.showsCursor = true
        configuration.capturesAudio = false

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let image = try await SCScreenshotManager.captureImage(
            contentFilter: filter,
            configuration: configuration
        )
        let bitmap = NSBitmapImageRep(cgImage: image)
        guard let png = bitmap.representation(using: .png, properties: [:]) else {
            throw CaptureError.pngEncodingFailed
        }

        try FileManager.default.createDirectory(
            at: destination.deletingLastPathComponent(),
            withIntermediateDirectories: true
        )
        try png.write(to: destination, options: .atomic)
    }
}

@main
struct GuardianCaptureHelper {
    static func main() async {
        do {
            let arguments = CommandLine.arguments
            guard arguments.count == 3, arguments[1] == "capture" else {
                throw ValidationError(
                    "Usage: guardian-capture-helper capture /absolute/path/frame.png"
                )
            }
            let destination = URL(fileURLWithPath: arguments[2]).standardizedFileURL
            guard destination.pathExtension.lowercased() == "png" else {
                throw ValidationError("Capture destination must use the .png extension.")
            }
            try await ScreenCaptureService().capturePrimaryDisplay(to: destination)
        } catch {
            FileHandle.standardError.write(Data("Guardian capture failed: \(error.localizedDescription)\n".utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }
}

struct ValidationError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? { message }
}
