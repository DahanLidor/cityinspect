import Foundation
import CoreMotion
import CoreLocation
import AVFoundation
import ARKit

/// Collects device sensor data at capture time: IMU, compass, lens intrinsics, device meta.
/// Usage: create instance, call `startCollecting()`, then `snapshot()` to get current readings.
class SensorCollector: ObservableObject {

    // MARK: - Published state
    @Published var isCollecting = false

    // MARK: - Private
    private let motionManager = CMMotionManager()
    private let altimeter = CMAltimeter()

    // Latest readings (updated at 30Hz)
    private var latestAccel: CMAcceleration?
    private var latestGyro: CMRotationRate?
    private var latestAttitude: CMAttitude?
    private var latestHeading: Double?
    private var latestPressure: Double?

    // MARK: - Start / Stop

    func startCollecting() {
        guard !isCollecting else { return }
        isCollecting = true
        UIDevice.current.isBatteryMonitoringEnabled = true

        // Device Motion (fused accelerometer + gyroscope + magnetometer)
        if motionManager.isDeviceMotionAvailable {
            motionManager.deviceMotionUpdateInterval = 1.0 / 30.0
            motionManager.startDeviceMotionUpdates(using: .xTrueNorthZVertical, to: .main) { [weak self] motion, _ in
                guard let motion = motion else { return }
                self?.latestAccel = motion.userAcceleration
                self?.latestGyro = motion.rotationRate
                self?.latestAttitude = motion.attitude
                self?.latestHeading = motion.heading  // true north heading
            }
        }

        // Barometric pressure
        if CMAltimeter.isRelativeAltitudeAvailable() {
            altimeter.startRelativeAltitudeUpdates(to: .main) { [weak self] data, _ in
                if let data = data {
                    self?.latestPressure = (data.pressure as NSNumber).doubleValue * 10.0 // kPa -> hPa
                }
            }
        }
    }

    func stopCollecting() {
        motionManager.stopDeviceMotionUpdates()
        altimeter.stopRelativeAltitudeUpdates()
        isCollecting = false
    }

    // MARK: - Snapshot

    /// Returns a dictionary with all current sensor readings, ready for JSON encoding.
    func snapshot(location: CLLocation?, arFrame: ARFrame? = nil) -> [String: Any] {
        var result: [String: Any] = [:]

        // 1. IMU
        var imu: [String: Any] = [:]
        if let a = latestAccel {
            imu["accel"] = [round3(a.x), round3(a.y), round3(a.z)]
        }
        if let g = latestGyro {
            imu["gyro"] = [round3(g.x), round3(g.y), round3(g.z)]
        }
        if let att = latestAttitude {
            imu["tilt_deg"] = round3(att.pitch * 180.0 / .pi)
        }
        if !imu.isEmpty { result["imu"] = imu }

        // 2. Camera pose (heading, pitch, roll)
        var camera: [String: Any] = [:]
        if let heading = latestHeading, heading >= 0 {
            camera["heading"] = round3(heading)
        }
        if let att = latestAttitude {
            camera["pitch"] = round3(att.pitch * 180.0 / .pi)
            camera["roll"] = round3(att.roll * 180.0 / .pi)
        }
        if !camera.isEmpty { result["camera"] = camera }

        // 3. Lens intrinsics (from ARFrame if available)
        if let frame = arFrame {
            var lens: [String: Any] = [:]
            let intrinsics = frame.camera.intrinsics
            // focal length in pixels → approximate mm (sensor width ~6.3mm for iPhone)
            let focalPx = Double(intrinsics[0][0])
            let imageWidth = Double(frame.camera.imageResolution.width)
            // Approximate: focal_mm = focal_px * sensor_width_mm / image_width_px
            let sensorWidthMm = 6.3 // approximate for most iPhones
            lens["focal_length_mm"] = round3(focalPx * sensorWidthMm / imageWidth)
            lens["focal_length_px"] = round3(focalPx)
            lens["fov_deg"] = round3(2.0 * atan(imageWidth / (2.0 * focalPx)) * 180.0 / .pi)
            lens["image_resolution"] = [Int(frame.camera.imageResolution.width),
                                         Int(frame.camera.imageResolution.height)]

            // Lens type heuristic
            let fovDeg = 2.0 * atan(imageWidth / (2.0 * focalPx)) * 180.0 / .pi
            if fovDeg > 100 { lens["type"] = "ultra_wide" }
            else if fovDeg > 65 { lens["type"] = "wide" }
            else { lens["type"] = "tele" }

            result["lens"] = lens
        }

        // 4. LiDAR availability
        var lidar: [String: Any] = [:]
        lidar["available"] = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)
        result["lidar"] = lidar

        // 5. Device meta
        var device: [String: Any] = [:]
        device["model"] = deviceModelName()
        device["os"] = UIDevice.current.systemVersion
        device["battery"] = round3(Double(UIDevice.current.batteryLevel))
        result["device"] = device

        // 6. Environment from sensors
        var env: [String: Any] = [:]
        if let pressure = latestPressure {
            env["pressure_hpa"] = round3(pressure)
        }
        if let loc = location {
            env["gps_accuracy_m"] = round3(loc.horizontalAccuracy)
            env["altitude_m"] = round3(loc.altitude)
            env["speed_mps"] = round3(max(0, loc.speed))
        }
        // Ambient light from ARFrame
        if let frame = arFrame, let lightEstimate = frame.lightEstimate {
            env["lux"] = round3(lightEstimate.ambientIntensity)
        }
        if !env.isEmpty { result["environment"] = env }

        // 7. Capture timestamp
        result["capture_timestamp_ms"] = Int64(Date().timeIntervalSince1970 * 1000)

        return result
    }

    // MARK: - Helpers

    private func round3(_ v: Double) -> Double {
        (v * 1000).rounded() / 1000
    }

    private func deviceModelName() -> String {
        var systemInfo = utsname()
        uname(&systemInfo)
        let machineMirror = Mirror(reflecting: systemInfo.machine)
        let identifier = machineMirror.children.reduce("") { id, element in
            guard let value = element.value as? Int8, value != 0 else { return id }
            return id + String(UnicodeScalar(UInt8(value)))
        }
        return identifier // e.g. "iPhone16,1"
    }
}
