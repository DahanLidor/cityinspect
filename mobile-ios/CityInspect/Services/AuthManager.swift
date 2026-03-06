import Foundation
import SwiftUI

@MainActor
class AuthManager: ObservableObject {
    @Published var isAuthenticated = false
    @Published var token: String?
    @Published var userId: String?
    @Published var userRole: String?
    @Published var isLoading = false
    @Published var errorMessage: String?

    private let apiService = APIService.shared
    private let tokenKey = "cityinspect_token"

    init() {
        if let saved = UserDefaults.standard.string(forKey: tokenKey) {
            self.token = saved
            self.isAuthenticated = true
        }
    }

    func login(username: String, password: String) async {
        isLoading = true
        errorMessage = nil

        do {
            let response = try await apiService.login(username: username, password: password)
            self.token = response.accessToken
            self.userId = response.userId
            self.userRole = response.role
            self.isAuthenticated = true
            UserDefaults.standard.set(response.accessToken, forKey: tokenKey)
            apiService.setToken(response.accessToken)
        } catch APIError.unauthorized {
            errorMessage = "Invalid username or password."
        } catch APIError.networkError(let msg) {
            errorMessage = "Network error: \(msg)"
        } catch {
            errorMessage = "Login failed: \(error.localizedDescription)"
        }

        isLoading = false
    }

    func logout() {
        token = nil
        userId = nil
        userRole = nil
        isAuthenticated = false
        UserDefaults.standard.removeObject(forKey: tokenKey)
        apiService.setToken(nil)
    }
}
