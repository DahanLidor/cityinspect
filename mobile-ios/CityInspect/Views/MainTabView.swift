import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var showCapture = false
    @State private var selectedTab = 0

    var body: some View {
        TabView(selection: $selectedTab) {
            HomeView(showCapture: $showCapture)
                .tabItem {
                    Label("Home", systemImage: "house.fill")
                }
                .tag(0)

            IncidentMapView()
                .tabItem {
                    Label("Map", systemImage: "map.fill")
                }
                .tag(1)

            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape.fill")
                }
                .tag(2)
        }
        .fullScreenCover(isPresented: $showCapture) {
            IncidentCaptureView()
                .environmentObject(authManager)
        }
    }
}

// MARK: - Home View

struct HomeView: View {
    @EnvironmentObject var authManager: AuthManager
    @Binding var showCapture: Bool
    @State private var recentIncidents: [Incident] = []

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 24) {
                    // Hero capture button
                    Button {
                        showCapture = true
                    } label: {
                        VStack(spacing: 16) {
                            Image(systemName: "camera.viewfinder")
                                .font(.system(size: 48))
                            Text("Create Incident")
                                .font(.title2)
                                .fontWeight(.semibold)
                            Text("Scan infrastructure damage using Camera & LiDAR")
                                .font(.caption)
                                .foregroundStyle(.white.opacity(0.8))
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 40)
                        .background(
                            LinearGradient(
                                colors: [.blue, .blue.opacity(0.8)],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                        .foregroundColor(.white)
                        .cornerRadius(20)
                    }
                    .padding(.horizontal)

                    // Stats summary
                    HStack(spacing: 12) {
                        StatCard(title: "Reported", value: "\(recentIncidents.count)", icon: "exclamationmark.triangle", color: .orange)
                        StatCard(title: "Active", value: "\(recentIncidents.filter { $0.status != "resolved" }.count)", icon: "wrench", color: .blue)
                        StatCard(title: "Resolved", value: "\(recentIncidents.filter { $0.status == "resolved" }.count)", icon: "checkmark.circle", color: .green)
                    }
                    .padding(.horizontal)

                    // Recent incidents
                    if !recentIncidents.isEmpty {
                        VStack(alignment: .leading, spacing: 12) {
                            Text("Recent Incidents")
                                .font(.headline)
                                .padding(.horizontal)

                            ForEach(recentIncidents.prefix(5)) { incident in
                                IncidentRow(incident: incident)
                            }
                        }
                    }
                }
                .padding(.vertical)
            }
            .navigationTitle("CityInspect")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button {
                        authManager.logout()
                    } label: {
                        Image(systemName: "rectangle.portrait.and.arrow.right")
                    }
                }
            }
            .task {
                await loadIncidents()
            }
        }
    }

    private func loadIncidents() async {
        do {
            recentIncidents = try await APIService.shared.getIncidentsForMap()
        } catch {
            // Silently handle — empty state shown
        }
    }
}

// MARK: - Subviews

struct StatCard: View {
    let title: String
    let value: String
    let icon: String
    let color: Color

    var body: some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .font(.title3)
                .foregroundStyle(color)
            Text(value)
                .font(.title2)
                .fontWeight(.bold)
            Text(title)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

struct IncidentRow: View {
    let incident: Incident

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(severityColor)
                .frame(width: 12, height: 12)

            VStack(alignment: .leading, spacing: 2) {
                Text(incident.hazardDisplayName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                Text(incident.address ?? "Lat: \(incident.latitude, specifier: "%.4f"), Lon: \(incident.longitude, specifier: "%.4f")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            VStack(alignment: .trailing, spacing: 2) {
                Text(incident.severity.capitalized)
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(severityColor)
                if incident.reportCount > 1 {
                    Text("\(incident.reportCount) reports")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
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

// MARK: - Settings

struct SettingsView: View {
    @EnvironmentObject var authManager: AuthManager

    var body: some View {
        NavigationStack {
            List {
                Section("Account") {
                    if let userId = authManager.userId {
                        LabeledContent("User ID", value: String(userId.prefix(8)) + "...")
                    }
                    if let role = authManager.userRole {
                        LabeledContent("Role", value: role.capitalized)
                    }
                }

                Section("Device") {
                    LabeledContent("LiDAR", value: ARWorldTrackingConfiguration.supportsFrameSemantics(.sceneDepth) ? "Available" : "Not available")
                }

                Section {
                    Button("Sign Out", role: .destructive) {
                        authManager.logout()
                    }
                }
            }
            .navigationTitle("Settings")
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(AuthManager())
}
