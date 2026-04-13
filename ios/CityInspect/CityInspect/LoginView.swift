import SwiftUI

struct LoginView: View {
    @AppStorage("auth_token") private var token: String = ""
    @AppStorage("auth_username") private var savedUsername: String = ""

    @State private var username = ""
    @State private var password = ""
    @State private var loading = false
    @State private var error = ""

    var body: some View {
        ZStack {
            Color(red: 0.059, green: 0.09, blue: 0.137).ignoresSafeArea()

            VStack(spacing: 32) {
                // Logo
                VStack(spacing: 8) {
                    Text("🏗️").font(.system(size: 56))
                    Text("CityInspect").font(.title).bold().foregroundColor(.white)
                    Text("סריקת תשתיות שטח").font(.subheadline).foregroundColor(.gray)
                }

                // Form
                VStack(spacing: 16) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("שם משתמש").font(.caption).foregroundColor(.gray).environment(\.layoutDirection, .rightToLeft)
                        TextField("admin", text: $username)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                            .padding()
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(12)
                            .foregroundColor(.white)
                            .multilineTextAlignment(.leading)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        Text("סיסמה").font(.caption).foregroundColor(.gray)
                        SecureField("••••••••", text: $password)
                            .padding()
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(12)
                            .foregroundColor(.white)
                    }

                    if !error.isEmpty {
                        Text(error).foregroundColor(.red).font(.caption).multilineTextAlignment(.center)
                    }

                    Button(action: doLogin) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 14)
                                .fill(Color.blue)
                                .frame(height: 52)
                            if loading {
                                ProgressView().tint(.white)
                            } else {
                                Text("כניסה").bold().foregroundColor(.white)
                            }
                        }
                    }
                    .disabled(loading || username.isEmpty || password.isEmpty)
                }
                .padding()
                .background(Color.white.opacity(0.05))
                .cornerRadius(20)

                Text("דמו: admin / admin123").font(.caption2).foregroundColor(.gray.opacity(0.6))
            }
            .padding(28)
            .environment(\.layoutDirection, .rightToLeft)
        }
    }

    private func doLogin() {
        loading = true
        error = ""
        Task {
            do {
                let res = try await APIService.shared.login(username: username, password: password)
                await MainActor.run {
                    savedUsername = res.user.username
                    token = res.access_token
                }
            } catch {
                await MainActor.run {
                    self.error = error.localizedDescription
                    loading = false
                }
            }
        }
    }
}
