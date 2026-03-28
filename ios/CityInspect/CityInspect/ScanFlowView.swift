import SwiftUI
import ARKit

// MARK: - Flow Steps

enum ScanStep {
    case camera
    case validating
    case lidar
    case uploading
    case success(Int, Bool)
    case failure(String)
}

// MARK: - ScanFlowView

struct ScanFlowView: View {
    let useCase: UseCase
    @Environment(\.dismiss) private var dismiss
    @StateObject private var location = LocationManager.shared
    @StateObject private var lidar = LiDARScanner()

    @State private var step: ScanStep = .camera
    @State private var capturedImage: UIImage? = nil
    @State private var validationCaption: String = ""
    @State private var showCamera = false
    @State private var cameraTransformAtCapture: simd_float4x4? = nil

    var body: some View {
        ZStack {
            Color(red: 0.039, green: 0.059, blue: 0.09).ignoresSafeArea()

            VStack(spacing: 0) {
                // Top bar
                HStack {
                    Button(action: { dismiss() }) {
                        Image(systemName: "chevron.right")
                            .foregroundColor(.white)
                            .padding(10)
                            .background(Color.white.opacity(0.1))
                            .clipShape(Circle())
                    }
                    Spacer()
                    VStack(spacing: 2) {
                        Text("\(useCase.icon) \(useCase.name_he)")
                            .font(.headline).foregroundColor(.white)
                        stepIndicator
                    }
                    Spacer()
                    Color.clear.frame(width: 40)
                }
                .padding()

                Divider().background(Color.white.opacity(0.1))

                // Content
                Group {
                    switch step {
                    case .camera:
                        cameraStep
                    case .validating:
                        validatingStep
                    case .lidar:
                        lidarStep
                    case .uploading:
                        loadingStep(icon: "arrow.up.circle", text: "שולח לענן...", color: .blue)
                    case .success(let id, let isNew):
                        successStep(ticketId: id, isNew: isNew)
                    case .failure(let msg):
                        failureStep(message: msg)
                    }
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .environment(\.layoutDirection, .rightToLeft)
        .sheet(isPresented: $showCamera) {
            CameraView(images: Binding(
                get: { capturedImage.map { [$0] } ?? [] },
                set: { imgs in
                    if let img = imgs.last {
                        capturedImage = img
                        cameraTransformAtCapture = lidar.currentCameraTransform
                    }
                }
            ))
        }
    }

    // MARK: - Steps UI

    @ViewBuilder
    private var cameraStep: some View {
        VStack(spacing: 24) {
            Spacer()

            if let img = capturedImage {
                Image(uiImage: img)
                    .resizable().scaledToFit()
                    .frame(maxHeight: 280)
                    .cornerRadius(16)
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.white.opacity(0.15)))
            } else {
                ZStack {
                    RoundedRectangle(cornerRadius: 20)
                        .fill(Color.white.opacity(0.05))
                        .frame(height: 240)
                    VStack(spacing: 12) {
                        Image(systemName: "camera.fill").font(.system(size: 48)).foregroundColor(.gray)
                        Text("צלם את התקלה").foregroundColor(.gray)
                    }
                }
                .padding(.horizontal)
            }

            Spacer()

            VStack(spacing: 12) {
                Button(action: { showCamera = true }) {
                    Label(capturedImage == nil ? "צלם תמונה" : "צלם שוב", systemImage: "camera.fill")
                        .frame(maxWidth: .infinity).padding()
                        .background(Color.blue.opacity(0.2))
                        .foregroundColor(.blue)
                        .cornerRadius(14)
                }

                if capturedImage != nil {
                    Button(action: validateImage) {
                        Label("אמת ✓", systemImage: "checkmark.shield.fill")
                            .frame(maxWidth: .infinity).padding()
                            .background(Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(14)
                            .font(.headline)
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 32)
        }
    }

    @ViewBuilder
    private var lidarStep: some View {
        VStack(spacing: 24) {
            Spacer()

            // Status card
            VStack(spacing: 16) {
                Image(systemName: "dot.radiowaves.left.and.right")
                    .font(.system(size: 56)).foregroundColor(.purple)

                if lidar.isScanning {
                    VStack(spacing: 8) {
                        Text("סריקת LiDAR פעילה").font(.title3).bold().foregroundColor(.white)
                        Text("\(lidar.pointCount.formatted()) נקודות").foregroundColor(.purple).font(.headline)
                        Text("הכוון את המכשיר לעבר התקלה").foregroundColor(.gray).font(.caption)
                    }
                } else if let data = lidar.scannedData {
                    VStack(spacing: 8) {
                        Image(systemName: "checkmark.circle.fill").font(.system(size: 40)).foregroundColor(.green)
                        Text("\(data.points.count.formatted()) נקודות נסרקו").font(.title3).bold().foregroundColor(.white)
                    }
                } else {
                    VStack(spacing: 8) {
                        Text("סרוק את אזור התקלה").font(.title3).bold().foregroundColor(.white)
                        Text("השאר את המכשיר מכוון לאותו מקום כמו בתמונה")
                            .foregroundColor(.gray).font(.caption).multilineTextAlignment(.center)
                    }
                }
            }
            .padding(32)
            .background(Color.white.opacity(0.06))
            .cornerRadius(24)
            .padding(.horizontal)

            Spacer()

            VStack(spacing: 12) {
                if lidar.isScanning {
                    Button(action: stopLiDARAndValidate) {
                        Label("סיים סריקה", systemImage: "stop.circle.fill")
                            .frame(maxWidth: .infinity).padding()
                            .background(Color.purple)
                            .foregroundColor(.white)
                            .cornerRadius(14).font(.headline)
                    }
                } else if lidar.scannedData != nil {
                    Button(action: uploadDetection) {
                        Label("שלח לענן", systemImage: "arrow.up.circle.fill")
                            .frame(maxWidth: .infinity).padding()
                            .background(Color.blue)
                            .foregroundColor(.white)
                            .cornerRadius(14).font(.headline)
                    }
                    Button("סרוק שוב") {
                        lidar.scannedData = nil
                        lidar.startScan()
                    }
                    .foregroundColor(.purple)
                } else {
                    if !lidar.isSupported {
                        // LiDAR not available — skip directly to upload
                        Button(action: uploadDetection) {
                            Label("שלח ללא LiDAR", systemImage: "arrow.up.circle.fill")
                                .frame(maxWidth: .infinity).padding()
                                .background(Color.blue)
                                .foregroundColor(.white)
                                .cornerRadius(14).font(.headline)
                        }
                        Text("⚠️ מכשיר זה אינו תומך ב-LiDAR")
                            .font(.caption).foregroundColor(.orange)
                    } else {
                        Button(action: { lidar.startScan() }) {
                            Label("התחל סריקת LiDAR", systemImage: "dot.radiowaves.left.and.right")
                                .frame(maxWidth: .infinity).padding()
                                .background(Color.purple.opacity(0.3))
                                .foregroundColor(.purple)
                                .cornerRadius(14).font(.headline)
                        }
                    }
                }
            }
            .padding(.horizontal)
            .padding(.bottom, 32)
        }
    }

    @ViewBuilder
    private var validatingStep: some View {
        VStack(spacing: 20) {
            Spacer()
            if let img = capturedImage {
                Image(uiImage: img)
                    .resizable().scaledToFit()
                    .frame(maxHeight: 260)
                    .cornerRadius(16)
                    .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.purple.opacity(0.6), lineWidth: 2))
                    .padding(.horizontal)
            }
            ProgressView().scaleEffect(1.4).tint(.purple)
            Text("מאמת תמונה עם AI...").foregroundColor(.gray)
            Spacer()
        }
    }

    private func loadingStep(icon: String, text: String, color: Color) -> some View {
        VStack(spacing: 20) {
            Spacer()
            ProgressView().scaleEffect(1.5).tint(color)
            Text(text).foregroundColor(.gray)
            Spacer()
        }
    }

    private func successStep(ticketId: Int, isNew: Bool) -> some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "checkmark.circle.fill").font(.system(size: 72)).foregroundColor(.green)
            Text(isNew ? "טיקט #\(ticketId) נפתח!" : "נוסף לטיקט #\(ticketId)")
                .font(.title2).bold().foregroundColor(.white)
            Text("הדאשבורד עודכן בזמן אמת").foregroundColor(.gray).font(.subheadline)
            Spacer()
            Button("חזור לרשימה") { dismiss() }
                .padding(.horizontal, 40).padding(.vertical, 14)
                .background(Color.blue).foregroundColor(.white)
                .cornerRadius(16).font(.headline)
                .padding(.bottom, 40)
        }
    }

    private func failureStep(message: String) -> some View {
        VStack(spacing: 20) {
            Spacer()
            Image(systemName: "xmark.circle.fill").font(.system(size: 64)).foregroundColor(.red)
            Text("לא ניתן לעבד את הדיווח").font(.title3).bold().foregroundColor(.white)
            Text(message).foregroundColor(.red).multilineTextAlignment(.center)
                .font(.subheadline).padding(.horizontal)
            Spacer()
            HStack(spacing: 16) {
                Button("נסה שוב") {
                    capturedImage = nil
                    lidar.scannedData = nil
                    step = .camera
                }
                .padding(.horizontal, 24).padding(.vertical, 12)
                .background(Color.blue).foregroundColor(.white).cornerRadius(14)

                Button("חזור") { dismiss() }
                    .padding(.horizontal, 24).padding(.vertical, 12)
                    .background(Color.white.opacity(0.1)).foregroundColor(.white).cornerRadius(14)
            }
            .padding(.bottom, 40)
        }
    }

    // MARK: - Step indicator

    private var stepIndicator: some View {
        HStack(spacing: 6) {
            ForEach(0..<3) { i in
                let active = stepIndex >= i
                Capsule()
                    .fill(active ? Color.blue : Color.white.opacity(0.2))
                    .frame(width: active ? 24 : 8, height: 4)
            }
        }
    }

    private var stepIndex: Int {
        switch step {
        case .camera, .validating: return 0
        case .lidar: return 1
        case .uploading, .success, .failure: return 2
        }
    }

    // MARK: - Actions

    private func validateImage() {
        guard let image = capturedImage else { return }
        step = .validating
        Task {
            do {
                let result = try await APIService.shared.validateImage(image: image, useCaseId: useCase.id)
                await MainActor.run {
                    if result.valid {
                        validationCaption = result.reason
                        step = .lidar
                    } else {
                        capturedImage = nil
                        step = .failure("התמונה אינה תואמת לקטגוריה: \(useCase.name_he)\n\n\(result.reason)")
                    }
                }
            } catch {
                await MainActor.run {
                    step = .failure(error.localizedDescription)
                }
            }
        }
    }

    private func stopLiDARAndValidate() {
        lidar.stopScan()

        // Validate alignment between camera capture and LiDAR scan
        if let cameraTransform = cameraTransformAtCapture,
           let data = lidar.scannedData,
           !data.points.isEmpty {
            if !isLiDARAligned(cameraTransform: cameraTransform, points: data.points) {
                step = .failure("ענן הנקודות אינו תואם לתמונה.\nאנא צלם וסרוק מאותו מיקום וכיוון.")
                return
            }
        }
        // Alignment OK (or no camera transform recorded) — ready to upload
    }

    private func uploadDetection() {
        guard let image = capturedImage, let loc = location.location else { return }
        step = .uploading
        Task {
            do {
                let ply = lidar.scannedData?.toPLY()
                let result = try await APIService.shared.uploadDetection(
                    lat: loc.coordinate.latitude,
                    lng: loc.coordinate.longitude,
                    image: image,
                    pointCloudData: ply,
                    useCaseId: useCase.id,
                    imageCaption: validationCaption
                )
                await MainActor.run {
                    step = .success(result.ticket_id, result.is_new_ticket)
                }
            } catch {
                await MainActor.run {
                    step = .failure(error.localizedDescription)
                }
            }
        }
    }

    // MARK: - LiDAR Alignment Check

    private func isLiDARAligned(cameraTransform: simd_float4x4, points: [SIMD3<Float>]) -> Bool {
        // Camera forward direction in world space (ARKit: -Z axis)
        let camForward = simd_normalize(SIMD3<Float>(
            -cameraTransform.columns.2.x,
            -cameraTransform.columns.2.y,
            -cameraTransform.columns.2.z
        ))
        let camPos = SIMD3<Float>(
            cameraTransform.columns.3.x,
            cameraTransform.columns.3.y,
            cameraTransform.columns.3.z
        )

        // Centroid of point cloud
        var centroid = SIMD3<Float>(0, 0, 0)
        for p in points { centroid += p }
        centroid /= Float(points.count)

        // Direction from camera to centroid
        let toCentroid = simd_normalize(centroid - camPos)

        // Dot product: >0.4 means within ~66 degrees — acceptable
        let alignment = simd_dot(camForward, toCentroid)
        return alignment > 0.4
    }
}
