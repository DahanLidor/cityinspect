import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authManager: AuthManager
    @State private var username = ""
    @State private var password = ""

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Spacer()

                // Logo / Branding
                VStack(spacing: 12) {
                    Image(systemName: "building.2.crop.circle")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 80, height: 80)
                        .foregroundStyle(.blue)

                    Text("CityInspect")
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    Text("Municipal Infrastructure Hazard Detection")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.bottom, 48)

                // Login Form
                VStack(spacing: 16) {
                    TextField("Username", text: $username)
                        .textContentType(.username)
                        .autocapitalization(.none)
                        .disableAutocorrection(true)
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(12)

                    SecureField("Password", text: $password)
                        .textContentType(.password)
                        .padding()
                        .background(Color(.systemGray6))
                        .cornerRadius(12)

                    if let error = authManager.errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                            .padding(.top, 4)
                    }

                    Button {
                        Task {
                            await authManager.login(username: username, password: password)
                        }
                    } label: {
                        HStack {
                            if authManager.isLoading {
                                ProgressView()
                                    .tint(.white)
                            }
                            Text("Sign In")
                                .fontWeight(.semibold)
                        }
                        .frame(maxWidth: .infinity)
                        .padding()
                        .background(isFormValid ? Color.blue : Color.gray)
                        .foregroundColor(.white)
                        .cornerRadius(12)
                    }
                    .disabled(!isFormValid || authManager.isLoading)
                }
                .padding(.horizontal, 24)

                Spacer()
                Spacer()
            }
            .navigationBarHidden(true)
        }
    }

    private var isFormValid: Bool {
        !username.isEmpty && password.count >= 6
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthManager())
}
