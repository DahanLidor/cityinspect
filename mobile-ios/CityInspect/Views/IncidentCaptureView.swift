import SwiftUI
import ARKit

// MARK: - Step-based Capture Flow

enum CaptureStep: Int, CaseIterable {
    case ready = 0
    case scanning = 1
    case uploading = 2
    case done = 3
}

struct IncidentCaptureView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    @StateObject private var lidarService = LiDARCaptureService()
    @StateObject private var locationService = LocationService()

    @State private var step: CaptureStep = .ready
    @State private var capturedImage: UIImage?
    @State private var captureData: CaptureData?
    @State private var isUploading = false
    @State private var uploadSuccess = false
    @State private var errorMessage: String?
    @State private var scanProgress: Double = 0
    @State private var scanTimer: Timer?

    var body: some View {
        NavigationStack {
            ZStack {
                Color.black.ignoresSafeArea()

                switch step {
                case .ready:
                    readyView
                case .scanning:
                    scanningView
                case .uploading:
                    uploadingView
                case .done:
                    doneView
                }
            }
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if step != .uploading {
                        Button {
                            dismiss()
                        } label: {
                            Image(systemName: "xmark")
                                .foregroundStyle(.white)
                        }
                    }
                }
            }
        }
        .onAppear {
            lidarService.startSession()
            locationService.startUpdating()
        }
        .onDisappear {
            lidarService.stopSession()
            locationService.stopUpdating()
            scanTimer?.invalidate()
        }
    }

    // MARK: - Step 1: Ready (Camera Preview + Big Button)

    private var readyView: some View {
        VStack(spacing: 0) {
            // AR Camera preview
            ZStack {
                ARViewContainer(session: lidarService.session)
                    .ignoresSafeArea()

                // Overlay gradient
                VStack {
                    Spacer()
                    LinearGradient(
                        colors: [.clear, .black.opacity(0.8)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                    .frame(height: 200)
                }

                // Status indicators at top
                VStack {
                    HStack(spacing: 16) {
                        sensorBadge(icon: "camera.fill", label: "מצלמה", active: true)
                        sensorBadge(icon: "sensor.tag.radiowaves.forward", label: "LiDAR", active: lidarService.isLiDARAvailable)
                        sensorBadge(icon: "location.fill", label: "GPS", active: locationService.currentLocation != nil)
                    }
                    .padding(.horizontal, 20)
                    .padding(.vertical, 10)
                    .background(.ultraThinMaterial)
                    .cornerRadius(16)
                    .padding(.top, 60)

                    Spacer()
                }
            }

            // Bottom section with capture button
            VStack(spacing: 16) {
                Text("כוון את המצלמה על המפגע")
                    .font(.headline)
                    .foregroundStyle(.white)

                Text("לחץ לסריקה — הכל אוטומטי")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))

                Button {
                    startScan()
                } label: {
                    ZStack {
                        Circle()
                            .stroke(Color.blue, lineWidth: 4)
                            .frame(width: 80, height: 80)
                        Circle()
                            .fill(Color.blue)
                            .frame(width: 64, height: 64)
                        Image(systemName: "camera.viewfinder")
                            .font(.system(size: 28, weight: .medium))
                            .foregroundStyle(.white)
                    }
                }
                .disabled(locationService.currentLocation == nil)
                .opacity(locationService.currentLocation == nil ? 0.4 : 1)

                if locationService.currentLocation == nil {
                    Text("ממתין ל-GPS...")
                        .font(.caption)
                        .foregroundStyle(.orange)
                }
            }
            .padding(.vertical, 30)
            .frame(maxWidth: .infinity)
            .background(Color.black)
        }
    }

    // MARK: - Step 2: Scanning (Auto progress)

    private var scanningView: some View {
        VStack(spacing: 0) {
            // Camera still visible
            ZStack {
                ARViewContainer(session: lidarService.session)
                    .ignoresSafeArea()

                // Scanning overlay
                VStack {
                    Spacer()

                    VStack(spacing: 20) {
                        // Animated scanning indicator
                        ZStack {
                            Circle()
                                .stroke(Color.blue.opacity(0.3), lineWidth: 6)
                                .frame(width: 100, height: 100)

                            Circle()
                                .trim(from: 0, to: scanProgress)
                                .stroke(Color.blue, style: StrokeStyle(lineWidth: 6, lineCap: .round))
                                .frame(width: 100, height: 100)
                                .rotationEffect(.degrees(-90))
                                .animation(.linear(duration: 0.1), value: scanProgress)

                            Image(systemName: "sensor.tag.radiowaves.forward")
                                .font(.system(size: 32))
                                .foregroundStyle(.blue)
                        }

                        Text("סורק...")
                            .font(.title3)
                            .fontWeight(.semibold)
                            .foregroundStyle(.white)

                        Text("LiDAR + מצלמה + GPS + IMU")
                            .font(.caption)
                            .foregroundStyle(.white.opacity(0.6))

                        // Progress bar
                        ProgressView(value: scanProgress)
                            .tint(.blue)
                            .padding(.horizontal, 60)
                    }
                    .padding(.bottom, 80)
                }
                .background(Color.black.opacity(0.5))
            }
        }
    }

    // MARK: - Step 3: Uploading

    private var uploadingView: some View {
        VStack(spacing: 30) {
            Spacer()

            if let image = capturedImage {
                Image(uiImage: image)
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxHeight: 200)
                    .cornerRadius(16)
                    .shadow(color: .blue.opacity(0.3), radius: 20)
                    .padding(.horizontal, 40)
            }

            VStack(spacing: 12) {
                ProgressView()
                    .scaleEffect(1.5)
                    .tint(.blue)

                Text("מעלה לענן...")
                    .font(.title3)
                    .fontWeight(.semibold)
                    .foregroundStyle(.white)

                Text("AI יסווג, ימדוד ויתעדף אוטומטית")
                    .font(.subheadline)
                    .foregroundStyle(.white.opacity(0.6))
            }

            if let error = errorMessage {
                VStack(spacing: 12) {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 40)

                    Button("נסה שוב") {
                        Task { await uploadCapture() }
                    }
                    .buttonStyle(.bordered)
                    .tint(.blue)
                }
            }

            Spacer()
        }
        .background(Color.black)
    }

    // MARK: - Step 4: Done

    private var doneView: some View {
        VStack(spacing: 24) {
            Spacer()

            // Success animation
            ZStack {
                Circle()
                    .fill(Color.green.opacity(0.15))
                    .frame(width: 120, height: 120)

                Circle()
                    .fill(Color.green.opacity(0.3))
                    .frame(width: 90, height: 90)

                Image(systemName: "checkmark.circle.fill")
                    .font(.system(size: 60))
                    .foregroundStyle(.green)
            }

            Text("נשלח בהצלחה!")
                .font(.title)
                .fontWeight(.bold)
                .foregroundStyle(.white)

            Text("הנתונים הועברו לענן.\nAI מנתח את המפגע כעת.")
                .font(.subheadline)
                .foregroundStyle(.white.opacity(0.6))
                .multilineTextAlignment(.center)

            // What happens next
            VStack(alignment: .leading, spacing: 10) {
                stepItem(icon: "brain", text: "VLM מזהה ומסווג את המפגע", done: true)
                stepItem(icon: "ruler", text: "מדידה אוטומטית מ-Point Cloud", done: true)
                stepItem(icon: "chart.bar", text: "חישוב ציון חומרה", done: false)
                stepItem(icon: "person.2", text: "הקצאת צוות טיפול", done: false)
            }
            .padding(20)
            .background(Color.white.opacity(0.05))
            .cornerRadius(16)
            .padding(.horizontal, 30)

            Spacer()

            Button {
                dismiss()
            } label: {
                Text("סיום")
                    .font(.headline)
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 16)
                    .background(Color.blue)
                    .cornerRadius(14)
            }
            .padding(.horizontal, 30)
            .padding(.bottom, 40)
        }
        .background(Color.black)
    }

    // MARK: - Helpers

    private func sensorBadge(icon: String, label: String, active: Bool) -> some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(label)
                .font(.caption2)
        }
        .foregroundStyle(active ? .green : .red)
    }

    private func stepItem(icon: String, text: String, done: Bool) -> some View {
        HStack(spacing: 12) {
            Image(systemName: done ? "checkmark.circle.fill" : "circle.dotted")
                .foregroundStyle(done ? .green : .white.opacity(0.4))
                .font(.body)
            Text(text)
                .font(.subheadline)
                .foregroundStyle(done ? .white : .white.opacity(0.5))
        }
    }

    // MARK: - Actions

    private func startScan() {
        step = .scanning
        scanProgress = 0

        // 3-second scan with progress
        scanTimer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { timer in
            scanProgress += 0.05 / 3.0
            if scanProgress >= 1.0 {
                timer.invalidate()
                captureAndUpload()
            }
        }
    }

    private func captureAndUpload() {
        let (image, depthData, lidarMeasurements) = lidarService.captureCurrentData()

        guard let uiImage = image,
              let jpegData = uiImage.jpegData(compressionQuality: 0.85),
              let location = locationService.currentLocation else {
            errorMessage = "שגיאה בצילום. וודא שהמצלמה וה-GPS פעילים."
            step = .ready
            return
        }

        capturedImage = uiImage

        var lidarMeas: CaptureData.LidarMeasurements?
        if let m = lidarMeasurements {
            lidarMeas = CaptureData.LidarMeasurements(
                depthM: m["depth_m"],
                widthM: m["width_m"],
                lengthM: m["length_m"],
                surfaceAreaM2: m["surface_area_m2"],
                volumeM3: m["volume_m3"]
            )
        }

        var data = CaptureData(
            imageData: jpegData,
            depthMapData: depthData,
            latitude: location.coordinate.latitude,
            longitude: location.coordinate.longitude,
            capturedAt: Date(),
            deviceInfo: [
                "model": UIDevice.current.model,
                "systemVersion": UIDevice.current.systemVersion,
                "lidarAvailable": "\(lidarService.isLiDARAvailable)"
            ]
        )
        data.lidarMeasurements = lidarMeas
        captureData = data

        step = .uploading
        Task { await uploadCapture() }
    }

    private func uploadCapture() async {
        guard let data = captureData else { return }

        isUploading = true
        errorMessage = nil

        do {
            let _ = try await APIService.shared.uploadIncident(capture: data)
            uploadSuccess = true
            try? await Task.sleep(nanoseconds: 500_000_000)
            await MainActor.run {
                step = .done
            }
        } catch {
            await MainActor.run {
                errorMessage = "העלאה נכשלה: \(error.localizedDescription)"
            }
        }

        isUploading = false
    }
}

// MARK: - AR View UIKit Bridge

struct ARViewContainer: UIViewRepresentable {
    let session: ARSession

    func makeUIView(context: Context) -> ARSCNView {
        let view = ARSCNView()
        view.session = session
        view.automaticallyUpdatesLighting = true
        return view
    }

    func updateUIView(_ uiView: ARSCNView, context: Context) {}
}

#Preview {
    IncidentCaptureView()
        .environmentObject(AuthManager())
}
