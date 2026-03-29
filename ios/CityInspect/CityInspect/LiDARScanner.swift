import ARKit
import RealityKit
import Combine

// MARK: - Point Cloud Data

struct PointCloudData {
    let points: [SIMD3<Float>]

    /// Export as ASCII PLY
    func toPLY() -> Data {
        var lines = [String]()
        lines.append("ply")
        lines.append("format ascii 1.0")
        lines.append("element vertex \(points.count)")
        lines.append("property float x")
        lines.append("property float y")
        lines.append("property float z")
        lines.append("end_header")
        for p in points {
            lines.append("\(p.x) \(p.y) \(p.z)")
        }
        return lines.joined(separator: "\n").data(using: .utf8) ?? Data()
    }
}

// MARK: - LiDAR Scanner

class LiDARScanner: NSObject, ObservableObject, ARSessionDelegate {
    let session = ARSession()

    @Published var isScanning = false
    @Published var pointCount = 0
    @Published var scannedData: PointCloudData?

    /// Camera transform at the moment the AR session started (approximates photo capture position)
    var currentCameraTransform: simd_float4x4? {
        session.currentFrame?.camera.transform
    }

    /// Latest AR frame — used for lens intrinsics and light estimation
    var latestARFrame: ARFrame? {
        session.currentFrame
    }

    private var meshAnchors: [ARMeshAnchor] = []

    override init() {
        super.init()
        session.delegate = self
    }

    var isSupported: Bool {
        ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)
    }

    func startScan() {
        guard isSupported else { return }
        meshAnchors = []
        pointCount = 0
        scannedData = nil
        isScanning = true

        let config = ARWorldTrackingConfiguration()
        config.sceneReconstruction = .mesh
        config.environmentTexturing = .none
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
    }

    func stopScan() {
        isScanning = false
        session.pause()
        scannedData = buildPointCloud()
    }

    // MARK: ARSessionDelegate

    func session(_ session: ARSession, didAdd anchors: [ARAnchor]) {
        updateMeshAnchors(anchors)
    }

    func session(_ session: ARSession, didUpdate anchors: [ARAnchor]) {
        updateMeshAnchors(anchors)
    }

    private func updateMeshAnchors(_ anchors: [ARAnchor]) {
        let mesh = anchors.compactMap { $0 as? ARMeshAnchor }
        for anchor in mesh {
            if let idx = meshAnchors.firstIndex(where: { $0.identifier == anchor.identifier }) {
                meshAnchors[idx] = anchor
            } else {
                meshAnchors.append(anchor)
            }
        }
        DispatchQueue.main.async {
            self.pointCount = self.meshAnchors.reduce(0) { $0 + $1.geometry.vertices.count }
        }
    }

    private func buildPointCloud() -> PointCloudData {
        var points = [SIMD3<Float>]()
        for anchor in meshAnchors {
            let geo = anchor.geometry
            let transform = anchor.transform
            let buf = geo.vertices
            for i in 0..<buf.count {
                let raw = buf.buffer.contents().advanced(by: buf.offset + buf.stride * i)
                var vertex = raw.assumingMemoryBound(to: SIMD3<Float>.self).pointee
                // Transform to world space
                let world = transform * SIMD4<Float>(vertex.x, vertex.y, vertex.z, 1)
                vertex = SIMD3<Float>(world.x, world.y, world.z)
                points.append(vertex)
            }
        }
        return PointCloudData(points: points)
    }
}
