import SwiftUI

@main
struct CityInspectApp: App {
    var body: some Scene {
        WindowGroup {
            RootView()
        }
    }
}

struct RootView: View {
    @AppStorage("auth_token") private var token: String = ""

    var body: some View {
        if token.isEmpty {
            LoginView()
        } else {
            HomeView()
        }
    }
}
