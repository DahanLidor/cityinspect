import SwiftUI
import MapKit

struct IncidentMapView: View {
    @State private var incidents: [Incident] = []
    @State private var selectedIncident: Incident?
    @State private var cameraPosition: MapCameraPosition = .automatic
    @State private var isLoading = true

    var body: some View {
        NavigationStack {
            ZStack {
                Map(position: $cameraPosition, selection: $selectedIncident) {
                    ForEach(incidents) { incident in
                        Annotation(incident.hazardDisplayName, coordinate: incident.coordinate) {
                            IncidentMapPin(incident: incident)
                        }
                        .tag(incident)
                    }
                }
                .mapStyle(.standard(elevation: .realistic))

                if isLoading {
                    ProgressView("Loading incidents...")
                        .padding()
                        .background(.ultraThinMaterial)
                        .cornerRadius(12)
                }
            }
            .navigationTitle("Incident Map")
            .navigationBarTitleDisplayMode(.inline)
            .sheet(item: $selectedIncident) { incident in
                IncidentDetailSheet(incident: incident)
                    .presentationDetents([.medium])
            }
            .task {
                await loadIncidents()
            }
        }
    }

    private func loadIncidents() async {
        do {
            incidents = try await APIService.shared.getIncidentsForMap()
        } catch {
            // Handle silently — empty map shown
        }
        isLoading = false
    }
}

// MARK: - Map Pin

struct IncidentMapPin: View {
    let incident: Incident

    var body: some View {
        VStack(spacing: 0) {
            Image(systemName: iconName)
                .font(.caption)
                .foregroundStyle(.white)
                .padding(6)
                .background(pinColor)
                .clipShape(Circle())

            Image(systemName: "triangle.fill")
                .font(.system(size: 8))
                .foregroundStyle(pinColor)
                .rotationEffect(.degrees(180))
                .offset(y: -2)
        }
    }

    private var iconName: String {
        switch incident.hazardType {
        case "pothole": return "circle.circle"
        case "broken_sidewalk": return "square.split.diagonal"
        case "crack": return "bolt"
        case "road_damage": return "exclamationmark.triangle"
        default: return "mappin"
        }
    }

    private var pinColor: Color {
        switch incident.severity {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .green
        }
    }
}

// MARK: - Detail Sheet

struct IncidentDetailSheet: View {
    let incident: Incident

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(incident.hazardDisplayName)
                        .font(.title2)
                        .fontWeight(.bold)
                    Text(incident.status.capitalized)
                        .font(.caption)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.blue.opacity(0.1))
                        .cornerRadius(4)
                }
                Spacer()
                Text(incident.severity.capitalized)
                    .font(.headline)
                    .foregroundStyle(severityColor)
            }

            Divider()

            if let confidence = incident.aiConfidence {
                LabeledContent("AI Confidence", value: "\(Int(confidence * 100))%")
            }
            if let depth = incident.depthM {
                LabeledContent("Depth", value: String(format: "%.1f cm", depth * 100))
            }
            if let area = incident.surfaceAreaM2 {
                LabeledContent("Surface Area", value: String(format: "%.2f m²", area))
            }
            LabeledContent("Reports", value: "\(incident.reportCount)")

            if let address = incident.address {
                LabeledContent("Address", value: address)
            }
        }
        .padding()
    }

    private var severityColor: Color {
        switch incident.severity {
        case "critical": return .red
        case "high": return .orange
        case "medium": return .yellow
        default: return .green
        }
    }
}

extension Incident: Hashable {
    static func == (lhs: Incident, rhs: Incident) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}
