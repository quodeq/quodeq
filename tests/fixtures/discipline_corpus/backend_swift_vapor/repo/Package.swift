// swift-tools-version:5.9
import PackageDescription
let package = Package(
  name: "x",
  dependencies: [
    .package(url: "https://github.com/vapor/vapor.git", from: "4.0.0"),
  ]
)
