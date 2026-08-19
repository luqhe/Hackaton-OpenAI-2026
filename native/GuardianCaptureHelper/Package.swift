// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "GuardianCaptureHelper",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "guardian-capture-helper", targets: ["GuardianCaptureHelper"]),
    ],
    targets: [
        .executableTarget(name: "GuardianCaptureHelper"),
    ]
)
