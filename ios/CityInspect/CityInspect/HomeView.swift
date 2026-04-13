import SwiftUI

struct HomeView: View {
    @AppStorage("auth_token") private var token: String = ""
    @State private var useCases: [UseCase] = []
    @State private var loading = true
    @State private var error = ""
    @State private var selectedUseCase: UseCase? = nil

    var body: some View {
        ZStack {
            Color(red: 0.039, green: 0.059, blue: 0.09).ignoresSafeArea()

            VStack(spacing: 0) {
                // Header
                HStack {
                    VStack(alignment: .trailing, spacing: 2) {
                        Text("CityInspect").font(.headline).bold().foregroundColor(.white)
                        Text("בחר סוג תקלה לדיווח").font(.caption).foregroundColor(.gray)
                    }
                    Spacer()
                    Button("יציאה") { token = "" }
                        .font(.caption).foregroundColor(.gray)
                }
                .padding()
                .background(Color.white.opacity(0.05))

                if loading {
                    Spacer()
                    ProgressView().tint(.white)
                    Text("טוען...").foregroundColor(.gray).padding(.top, 8)
                    Spacer()
                } else if !error.isEmpty {
                    Spacer()
                    VStack(spacing: 12) {
                        Image(systemName: "wifi.slash").font(.system(size: 40)).foregroundColor(.red)
                        Text(error).foregroundColor(.red).multilineTextAlignment(.center).font(.caption)
                        Button("נסה שוב") { Task { await loadUseCases() } }
                            .foregroundColor(.blue)
                    }.padding()
                    Spacer()
                } else {
                    ScrollView {
                        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible())], spacing: 16) {
                            ForEach(useCases) { uc in
                                UseCaseCard(useCase: uc)
                                    .onTapGesture { selectedUseCase = uc }
                            }
                        }
                        .padding()
                    }
                }
            }
        }
        .environment(\.layoutDirection, .rightToLeft)
        .task { await loadUseCases() }
        .fullScreenCover(item: $selectedUseCase) { uc in
            ScanFlowView(useCase: uc)
        }
    }

    private func loadUseCases() async {
        loading = true
        error = ""
        do {
            useCases = try await APIService.shared.fetchUseCases()
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }
}

struct UseCaseCard: View {
    let useCase: UseCase

    var body: some View {
        VStack(spacing: 12) {
            Text(useCase.icon).font(.system(size: 44))
            Text(useCase.name_he)
                .font(.subheadline).bold()
                .foregroundColor(.white)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
        .background(Color.white.opacity(0.07))
        .cornerRadius(20)
        .overlay(RoundedRectangle(cornerRadius: 20).stroke(Color.white.opacity(0.1), lineWidth: 1))
    }

}
