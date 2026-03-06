import Foundation

// MARK: - API Errors

enum APIError: Error, LocalizedError {
    case invalidURL
    case unauthorized
    case serverError(Int)
    case networkError(String)
    case decodingError(String)

    var errorDescription: String? {
        switch self {
        case .invalidURL: return "Invalid server URL."
        case .unauthorized: return "Authentication required."
        case .serverError(let code): return "Server error (HTTP \(code))."
        case .networkError(let msg): return "Network error: \(msg)"
        case .decodingError(let msg): return "Data error: \(msg)"
        }
    }
}

// MARK: - API Service

class APIService {
    static let shared = APIService()

    // Change this to your backend URL
    private let baseURL: String

    private var token: String?

    private init() {
        // Default to localhost for simulator, adjust for device testing
        #if targetEnvironment(simulator)
        baseURL = "http://localhost:8000/api/v1"
        #else
        baseURL = "http://YOUR_SERVER_IP:8000/api/v1"
        #endif
    }

    func setToken(_ token: String?) {
        self.token = token
    }

    // MARK: - Auth

    func login(username: String, password: String) async throws -> TokenResponse {
        let body = LoginRequest(username: username, password: password)
        return try await post(path: "/login", body: body)
    }

    // MARK: - Incidents

    func uploadIncident(capture: CaptureData) async throws -> Incident {
        guard let url = URL(string: "\(baseURL)/incident/upload") else {
            throw APIError.invalidURL
        }

        let boundary = UUID().uuidString
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")

        if let token = token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        var body = Data()

        // Image file
        body.appendMultipart(boundary: boundary, name: "image", filename: "capture.jpg",
                             mimeType: "image/jpeg", data: capture.imageData)

        // Depth map (optional)
        if let depthData = capture.depthMapData {
            body.appendMultipart(boundary: boundary, name: "depth_map", filename: "depth.bin",
                                 mimeType: "application/octet-stream", data: depthData)
        }

        // Form fields
        body.appendMultipartField(boundary: boundary, name: "latitude", value: "\(capture.latitude)")
        body.appendMultipartField(boundary: boundary, name: "longitude", value: "\(capture.longitude)")

        let isoFormatter = ISO8601DateFormatter()
        body.appendMultipartField(boundary: boundary, name: "captured_at",
                                  value: isoFormatter.string(from: capture.capturedAt))

        if let deviceJSON = try? JSONEncoder().encode(capture.deviceInfo),
           let deviceStr = String(data: deviceJSON, encoding: .utf8) {
            body.appendMultipartField(boundary: boundary, name: "device_info", value: deviceStr)
        }

        if let lidar = capture.lidarMeasurements,
           let lidarJSON = try? JSONEncoder().encode(lidar),
           let lidarStr = String(data: lidarJSON, encoding: .utf8) {
            body.appendMultipartField(boundary: boundary, name: "lidar_measurements", value: lidarStr)
        }

        body.append("--\(boundary)--\r\n".data(using: .utf8)!)
        request.httpBody = body

        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResp = response as? HTTPURLResponse else {
            throw APIError.networkError("Invalid response")
        }

        guard (200...299).contains(httpResp.statusCode) else {
            if httpResp.statusCode == 401 { throw APIError.unauthorized }
            throw APIError.serverError(httpResp.statusCode)
        }

        let decoder = JSONDecoder()
        return try decoder.decode(Incident.self, from: data)
    }

    func getIncident(id: String) async throws -> Incident {
        return try await get(path: "/incident/\(id)")
    }

    func getIncidentsForMap(minLat: Double = -90, maxLat: Double = 90,
                            minLon: Double = -180, maxLon: Double = 180) async throws -> [Incident] {
        let query = "?min_lat=\(minLat)&max_lat=\(maxLat)&min_lon=\(minLon)&max_lon=\(maxLon)"
        return try await get(path: "/incidents/map\(query)")
    }

    // MARK: - Private Helpers

    private func get<T: Decodable>(path: String) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        if let token = token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        let (data, response) = try await URLSession.shared.data(for: request)
        return try handleResponse(data: data, response: response)
    }

    private func post<T: Decodable, B: Encodable>(path: String, body: B) async throws -> T {
        guard let url = URL(string: "\(baseURL)\(path)") else { throw APIError.invalidURL }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        if let token = token {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }

        request.httpBody = try JSONEncoder().encode(body)

        let (data, response) = try await URLSession.shared.data(for: request)
        return try handleResponse(data: data, response: response)
    }

    private func handleResponse<T: Decodable>(data: Data, response: URLResponse) throws -> T {
        guard let httpResp = response as? HTTPURLResponse else {
            throw APIError.networkError("Invalid response type")
        }

        guard (200...299).contains(httpResp.statusCode) else {
            if httpResp.statusCode == 401 { throw APIError.unauthorized }
            throw APIError.serverError(httpResp.statusCode)
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error.localizedDescription)
        }
    }
}

// MARK: - Data Multipart Helpers

extension Data {
    mutating func appendMultipart(boundary: String, name: String, filename: String,
                                   mimeType: String, data: Data) {
        append("--\(boundary)\r\n".data(using: .utf8)!)
        append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
        append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
        append(data)
        append("\r\n".data(using: .utf8)!)
    }

    mutating func appendMultipartField(boundary: String, name: String, value: String) {
        append("--\(boundary)\r\n".data(using: .utf8)!)
        append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
        append("\(value)\r\n".data(using: .utf8)!)
    }
}
