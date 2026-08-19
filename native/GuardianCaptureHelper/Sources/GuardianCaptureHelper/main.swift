import AppKit
import CoreGraphics
import CoreMedia
import Foundation
import ScreenCaptureKit
import Vision

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

struct ActiveWindow: Encodable {
    let application: String
    let bundleIdentifier: String?
    let processIdentifier: Int32
    let windowTitle: String
}

struct ActiveWindowService {
    func current() throws -> ActiveWindow {
        guard let application = NSWorkspace.shared.frontmostApplication else {
            throw ValidationError("No frontmost application is available.")
        }

        let processIdentifier = application.processIdentifier
        let windows = CGWindowListCopyWindowInfo(
            [.optionOnScreenOnly, .excludeDesktopElements],
            kCGNullWindowID
        ) as? [[String: Any]] ?? []
        let windowTitle = windows.first { window in
            let ownerPID = window[kCGWindowOwnerPID as String] as? Int32
            let layer = window[kCGWindowLayer as String] as? Int ?? -1
            return ownerPID == processIdentifier && layer == 0
        }?[kCGWindowName as String] as? String ?? ""

        return ActiveWindow(
            application: application.localizedName ?? application.bundleIdentifier ?? "Unknown application",
            bundleIdentifier: application.bundleIdentifier,
            processIdentifier: processIdentifier,
            windowTitle: windowTitle
        )
    }
}

struct TextRecognitionService {
    func recognizeText(in imageURL: URL) throws -> [String] {
        guard
            let image = NSImage(contentsOf: imageURL),
            let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
        else {
            throw ValidationError("OCR input must be a readable image.")
        }

        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = true
        request.recognitionLanguages = ["pt-BR", "en-US"]
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])

        return (request.results ?? []).compactMap { observation in
            observation.topCandidates(1).first?.string
        }
    }
}

@main
struct GuardianCaptureHelper {
    static func main() async {
        do {
            let arguments = CommandLine.arguments
            guard arguments.count >= 2 else {
                throw ValidationError(usage)
            }

            switch arguments[1] {
            case "capture":
                guard arguments.count == 3 else {
                    throw ValidationError(usage)
                }
                let destination = URL(fileURLWithPath: arguments[2]).standardizedFileURL
                guard destination.pathExtension.lowercased() == "png" else {
                    throw ValidationError("Capture destination must use the .png extension.")
                }
                try await ScreenCaptureService().capturePrimaryDisplay(to: destination)
            case "active-window":
                guard arguments.count == 2 else {
                    throw ValidationError(usage)
                }
                let encoder = JSONEncoder()
                encoder.outputFormatting = [.sortedKeys]
                let payload = try encoder.encode(ActiveWindowService().current())
                FileHandle.standardOutput.write(payload)
                FileHandle.standardOutput.write(Data("\n".utf8))
            case "ocr":
                guard arguments.count == 3 else {
                    throw ValidationError(usage)
                }
                let imageURL = URL(fileURLWithPath: arguments[2]).standardizedFileURL
                let lines = try TextRecognitionService().recognizeText(in: imageURL)
                FileHandle.standardOutput.write(Data(lines.joined(separator: "\n").utf8))
                FileHandle.standardOutput.write(Data("\n".utf8))
            default:
                throw ValidationError(usage)
            }
        } catch {
            FileHandle.standardError.write(Data("Guardian capture failed: \(error.localizedDescription)\n".utf8))
            Foundation.exit(EXIT_FAILURE)
        }
    }

    private static let usage = """
    Usage:
      guardian-capture-helper capture /absolute/path/frame.png
      guardian-capture-helper active-window
      guardian-capture-helper ocr /absolute/path/frame.png
    """
}

struct ValidationError: LocalizedError {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var errorDescription: String? { message }
}
