import SwiftUI
import ARKit

struct IncidentCaptureView: View {
    @EnvironmentObject var authManager: AuthManager
    @Environment(\.dismiss) private var dismiss

    @StateObject private var lidarService = LiDARCaptureService()
    @StateObject private var locationService = LocationService()

    @State private var capturedImage: UIImage?
    @State private var captureData: CaptureData?
    @State private var isUploading = false
    @State private var uploadSuccess = false
    @State private var uploadedIncident: Incident?
    @State private var errorMessage: String?
    @State private var showConfirmation = false

    var body: some View {
        NavigationStack {
            ZStack {
                if let _ = capturedImage, showConfirmation {
                    confirmationView
                } else {
                    scanningView
                }
            }
            .navigationTitle("Scan Hazard")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    Button("Cancel") { dismiss() }
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
        }
    }

    // MARK: - Scanning View (AR Camera)

    private var scanningView: some View {
        VStack(spacing: 0) {
            // AR Camera preview area
            ZStack {
                ARViewContainer(session: lidarService.session)
                    .ignoresSafeArea()

                VStack {
                    Spacer()

                    // Status indicators
                    HStack(spacing: 20) {
                        StatusBadge(
                            icon: "camera.fill",
                            label: "Camera",
                            isActive: true
                        )
                        StatusBadge(
                            icon: "sensor.tag.radiowaves.forward",
                            label: "LiDAR",
                            isActive: lidarService.isLiDARAvailable
                        )
                        StatusBadge(
                            icon: "location.fill",
                            label: "GPS",
                            isActive: locationService.currentLocation != nil
                        )
                    }
                    .padding()
                    .background(.ultraThinMaterial)
                    .cornerRadius(16)
                    .padding(.bottom, 20)
                }
            }

            // Capture button
            VStack(spacing: 12) {
                Button {
                    captureScene()
                } label: {
                    ZStack {
                        Circle()
                            .stroke(Color.white, lineWidth: 4)
                            .frame(width: 72, height: 72)
                        Circle()
                            .fill(Color.white)
                            .frame(width: 60, height: 60)
                    }
                }
                .disabled(locationService.currentLocation == nil)

                Text("Tap to capture")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .padding(.vertical, 24)
            .frame(maxWidth: .infinity)
            .background(Color(.systemBackground))
        }
    }

    // MARK: - Confirmation View

    private var confirmationView: some View {
        ScrollView {
            VStack(spacing: 20) {
                if let image = capturedImage {
                    Image(uiImage: image)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .cornerRadius(12)
                        .padding(.horizontal)
                }

                if let loc = locationService.currentLocation {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("GPS Coordinates", systemImage: "location.fill")
                            .font(.headline)
                        Text("Lat: \(loc.coordinate.latitude, specifier: "%.6f"), Lon: \(loc.coordinate.longitude, specifier: "%.6f")")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                }

                if lidarService.isLiDARAvailable {
                    VStack(alignment: .leading, spacing: 8) {
                        Label("LiDAR Data", systemImage: "sensor.tag.radiowaves.forward")
                            .font(.headline)
                        Text("Depth map captured. Measurements will be computed server-side.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal)
                }

                if let error = errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(.horizontal)
                }

                if uploadSuccess, let incident = uploadedIncident {
                    VStack(spacing: 12) {
                        Image(systemName: "checkmark.circle.fill")
                            .font(.system(size: 48))
                            .foregroundStyle(.green)
                        Text("Incident Reported!")
                            .font(.title3)
                            .fontWeight(.semibold)
                        Text("\(incident.hazardDisplayName) — \(incident.severity.capitalized) severity")
                            .foregroundStyle(.secondary)
                        Button("Done") { dismiss() }
                            .buttonStyle(.borderedProminent)
                    }
                    .padding()
                } else {
                    HStack(spacing: 16) {
                        Button("Retake") {
                            capturedImage = nil
                            showConfirmation = false
                            errorMessage = nil
                        }
                        .buttonStyle(.bordered)

                        Button {
                            Task { await uploadCapture() }
                        } label: {
                            HStack {
                                if isUploading { ProgressView().tint(.white) }
                                Text("Submit Report")
                            }
                        }
                        .buttonStyle(.borderedProminent)
                        .disabled(isUploading)
                    }
                    .padding()
                }
            }
            .padding(.vertical)
        }
    }

    // MARK: - Actions

    private func captureScene() {
        let (image, depthData, lidarMeasurements) = lidarService.captureCurrentData()

        guard let uiImage = image,
              let jpegData = uiImage.jpegData(compressionQuality: 0.85),
              let location = locationService.currentLocation else {
            errorMessage = "Failed to capture scene. Ensure camera and GPS are active."
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
        showConfirmation = true
    }

    private func uploadCapture() async {
        guard let data = captureData else { return }

        isUploading = true
        errorMessage = nil

        do {
            let incident = try await APIService.shared.uploadIncident(capture: data)
            uploadedIncident = incident
            uploadSuccess = true
        } catch {
            errorMessage = "Upload failed: \(error.localizedDescription)"
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

// MARK: - Status Badge

struct StatusBadge: View {
    let icon: String
    let label: String
    let isActive: Bool

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption2)
            Text(label)
                .font(.caption2)
        }
        .foregroundStyle(isActive ? .green : .red)
    }
}
