import Foundation
import AVFoundation
import ARKit
import CoreLocation
import UIKit

// MARK: - Location Manager

class LocationService: NSObject, ObservableObject, CLLocationManagerDelegate {
    @Published var currentLocation: CLLocation?
    @Published var authorizationStatus: CLAuthorizationStatus = .notDetermined

    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        manager.desiredAccuracy = kCLLocationAccuracyBest
        manager.requestWhenInUseAuthorization()
    }

    func startUpdating() {
        manager.startUpdatingLocation()
    }

    func stopUpdating() {
        manager.stopUpdatingLocation()
    }

    func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {
        currentLocation = locations.last
    }

    func locationManager(_ manager: CLLocationManager, didChangeAuthorization status: CLAuthorizationStatus) {
        authorizationStatus = status
        if status == .authorizedWhenInUse || status == .authorizedAlways {
            startUpdating()
        }
    }
}

// MARK: - ARKit LiDAR Capture Session

class LiDARCaptureService: NSObject, ObservableObject, ARSessionDelegate {
    @Published var isLiDARAvailable = false
    @Published var currentDepthMap: CVPixelBuffer?
    @Published var currentFrame: ARFrame?

    let session = ARSession()

    override init() {
        super.init()
        isLiDARAvailable = ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth)
        session.delegate = self
    }

    func startSession() {
        guard isLiDARAvailable else { return }

        let config = ARWorldTrackingConfiguration()
        config.frameSemantics = [.sceneDepth, .smoothedSceneDepth]
        config.planeDetection = [.horizontal]
        session.run(config)
    }

    func stopSession() {
        session.pause()
    }

    func captureCurrentData() -> (image: UIImage?, depthData: Data?, lidarMeasurements: [String: Double]?) {
        guard let frame = session.currentFrame else {
            return (nil, nil, nil)
        }

        // Capture RGB image
        let ciImage = CIImage(cvPixelBuffer: frame.capturedImage)
        let context = CIContext()
        guard let cgImage = context.createCGImage(ciImage, from: ciImage.extent) else {
            return (nil, nil, nil)
        }
        let image = UIImage(cgImage: cgImage)

        // Capture depth map
        var depthData: Data?
        var measurements: [String: Double]?

        if let sceneDepth = frame.smoothedSceneDepth ?? frame.sceneDepth {
            let depthMap = sceneDepth.depthMap
            depthData = pixelBufferToData(depthMap)
            measurements = processDepthMap(depthMap)
        }

        return (image, depthData, measurements)
    }

    // MARK: - ARSessionDelegate

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        DispatchQueue.main.async {
            self.currentFrame = frame
            self.currentDepthMap = frame.smoothedSceneDepth?.depthMap ?? frame.sceneDepth?.depthMap
        }
    }

    // MARK: - Depth Processing

    private func pixelBufferToData(_ buffer: CVPixelBuffer) -> Data {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }

        let width = CVPixelBufferGetWidth(buffer)
        let height = CVPixelBufferGetHeight(buffer)
        let bytesPerRow = CVPixelBufferGetBytesPerRow(buffer)

        guard let baseAddress = CVPixelBufferGetBaseAddress(buffer) else {
            return Data()
        }

        return Data(bytes: baseAddress, count: height * bytesPerRow)
    }

    private func processDepthMap(_ buffer: CVPixelBuffer) -> [String: Double] {
        CVPixelBufferLockBaseAddress(buffer, .readOnly)
        defer { CVPixelBufferUnlockBaseAddress(buffer, .readOnly) }

        let width = CVPixelBufferGetWidth(buffer)
        let height = CVPixelBufferGetHeight(buffer)

        guard let baseAddress = CVPixelBufferGetBaseAddress(buffer) else {
            return [:]
        }

        let floatBuffer = baseAddress.assumingMemoryBound(to: Float32.self)
        let count = width * height

        var values: [Float] = []
        for i in 0..<count {
            let val = floatBuffer[i]
            if val.isFinite && val > 0 {
                values.append(val)
            }
        }

        guard !values.isEmpty else { return [:] }

        values.sort()
        let median = values[values.count / 2]
        let p75 = values[Int(Double(values.count) * 0.75)]
        let minDepth = values.first ?? 0

        // Estimate damage metrics
        let referencePlane = Double(p75)
        let maxDepression = Double(p75 - minDepth)

        // Count damage pixels (below threshold)
        let threshold: Float = 0.02
        let damagePixels = values.filter { (p75 - $0) > threshold }.count
        let pixelSize: Double = 0.005

        let area = Double(damagePixels) * pixelSize * pixelSize
        let avgDepression = values.filter { (p75 - $0) > threshold }
            .map { Double(p75 - $0) }
            .reduce(0, +) / max(Double(damagePixels), 1)

        return [
            "depth_m": maxDepression,
            "width_m": sqrt(area) * 1.2,
            "length_m": sqrt(area) * 1.2,
            "surface_area_m2": area,
            "volume_m3": area * avgDepression
        ]
    }
}
