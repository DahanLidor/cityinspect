import Foundation
import UIKit

let API_BASE = "https://cityinspect-production.up.railway.app"

// MARK: - Models

struct LoginResponse: Codable {
    let access_token: String
    let user: UserInfo
}

struct UserInfo: Codable {
    let id: Int
    let username: String
    let full_name: String
    let role: String
}

struct UseCase: Codable, Identifiable {
    let id: String
    let name_he: String
    let name_en: String
    let icon: String
    let severity_default: String
}

struct ValidationResult: Codable {
    let valid: Bool
    let reason: String
    let confidence: Double
}

struct UploadResponse: Codable {
    let detection_id: Int
    let ticket_id: Int
    let is_new_ticket: Bool
    let address: String
}

// MARK: - API Service

class APIService {
    static let shared = APIService()

    var token: String {
        get { UserDefaults.standard.string(forKey: "auth_token") ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: "auth_token") }
    }
    var username: String {
        get { UserDefaults.standard.string(forKey: "auth_username") ?? "" }
        set { UserDefaults.standard.set(newValue, forKey: "auth_username") }
    }
    var cityId: String { "tel-aviv" }

    private var authHeader: [String: String] {
        ["Authorization": "Bearer \(token)"]
    }

    // MARK: Login

    func login(username: String, password: String) async throws -> LoginResponse {
        var req = URLRequest(url: URL(string: "\(API_BASE)/api/v1/login")!)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["username": username, "password": password])
        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else { throw APIError.unauthorized }
        return try JSONDecoder().decode(LoginResponse.self, from: data)
    }

    // MARK: Use Cases

    func fetchUseCases() async throws -> [UseCase] {
        var req = URLRequest(url: URL(string: "\(API_BASE)/api/v1/use-cases?city_id=\(cityId)")!)
        authHeader.forEach { req.setValue($1, forHTTPHeaderField: $0) }
        let (data, _) = try await URLSession.shared.data(for: req)
        return try JSONDecoder().decode([UseCase].self, from: data)
    }

    // MARK: Validate Image

    func validateImage(image: UIImage, useCaseId: String) async throws -> ValidationResult {
        guard let jpeg = image.jpegData(compressionQuality: 0.85) else {
            throw APIError.serverError("Failed to encode image")
        }
        let boundary = UUID().uuidString
        var req = URLRequest(url: URL(string: "\(API_BASE)/api/v1/validate/image")!)
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authHeader.forEach { req.setValue($1, forHTTPHeaderField: $0) }
        req.timeoutInterval = 30

        var body = Data()
        func field(_ name: String, _ value: String) {
            body += "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!
        }
        field("use_case_id", useCaseId)
        field("city_id", cityId)
        body += "--\(boundary)\r\nContent-Disposition: form-data; name=\"image\"; filename=\"photo.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".data(using: .utf8)!
        body += jpeg
        body += "\r\n--\(boundary)--\r\n".data(using: .utf8)!
        req.httpBody = body

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            throw APIError.serverError(String(data: data, encoding: .utf8) ?? "Validation failed")
        }
        return try JSONDecoder().decode(ValidationResult.self, from: data)
    }

    // MARK: Upload Detection

    func uploadDetection(
        lat: Double, lng: Double,
        image: UIImage,
        pointCloudData: Data?,
        useCaseId: String,
        imageCaption: String = "",
        sensorData: [String: Any]? = nil
    ) async throws -> UploadResponse {
        guard let jpeg = image.jpegData(compressionQuality: 0.85) else {
            throw APIError.serverError("Failed to encode image")
        }
        let boundary = UUID().uuidString
        var req = URLRequest(url: URL(string: "\(API_BASE)/api/v1/incident/upload")!)
        req.httpMethod = "POST"
        req.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        authHeader.forEach { req.setValue($1, forHTTPHeaderField: $0) }
        req.timeoutInterval = 60

        var body = Data()
        func field(_ name: String, _ value: String) {
            body += "--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".data(using: .utf8)!
        }
        field("lat", String(lat))
        field("lng", String(lng))
        field("defect_type", useCaseId)
        field("severity", "unknown")
        field("vehicle_id", UIDevice.current.identifierForVendor?.uuidString ?? "UNKNOWN")
        field("vehicle_model", UIDevice.current.model)
        field("vehicle_sensor_version", "lidar-v1.0")
        field("reported_by", username)
        if !imageCaption.isEmpty { field("image_caption", imageCaption) }
        if let sd = sensorData, let jsonData = try? JSONSerialization.data(withJSONObject: sd) {
            field("sensor_data", String(data: jsonData, encoding: .utf8) ?? "{}")
        }

        body += "--\(boundary)\r\nContent-Disposition: form-data; name=\"image\"; filename=\"scan.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n".data(using: .utf8)!
        body += jpeg
        body += "\r\n".data(using: .utf8)!

        if let ply = pointCloudData {
            body += "--\(boundary)\r\nContent-Disposition: form-data; name=\"point_cloud\"; filename=\"scan.ply\"\r\nContent-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!
            body += ply
            body += "\r\n".data(using: .utf8)!
        }
        body += "--\(boundary)--\r\n".data(using: .utf8)!
        req.httpBody = body

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 201 else {
            throw APIError.serverError(String(data: data, encoding: .utf8) ?? "Upload failed")
        }
        return try JSONDecoder().decode(UploadResponse.self, from: data)
    }
}

enum APIError: LocalizedError {
    case unauthorized
    case serverError(String)
    var errorDescription: String? {
        switch self {
        case .unauthorized: return "שם משתמש או סיסמה שגויים"
        case .serverError(let m): return m
        }
    }
}
