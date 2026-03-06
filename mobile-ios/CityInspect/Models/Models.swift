import Foundation
import CoreLocation

// MARK: - API Models

struct LoginRequest: Codable {
    let username: String
    let password: String
}

struct TokenResponse: Codable {
    let accessToken: String
    let tokenType: String
    let userId: String
    let role: String

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case userId = "user_id"
        case role
    }
}

// MARK: - Incident Models

struct Incident: Codable, Identifiable {
    let id: String
    let hazardType: String
    let severity: String
    let status: String
    let latitude: Double
    let longitude: Double
    let address: String?
    let aiConfidence: Double?
    let depthM: Double?
    let widthM: Double?
    let lengthM: Double?
    let surfaceAreaM2: Double?
    let volumeM3: Double?
    let imageUrl: String?
    let thumbnailUrl: String?
    let reportCount: Int
    let firstReportedAt: String
    let lastReportedAt: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case hazardType = "hazard_type"
        case severity
        case status
        case latitude, longitude, address
        case aiConfidence = "ai_confidence"
        case depthM = "depth_m"
        case widthM = "width_m"
        case lengthM = "length_m"
        case surfaceAreaM2 = "surface_area_m2"
        case volumeM3 = "volume_m3"
        case imageUrl = "image_url"
        case thumbnailUrl = "thumbnail_url"
        case reportCount = "report_count"
        case firstReportedAt = "first_reported_at"
        case lastReportedAt = "last_reported_at"
        case createdAt = "created_at"
    }

    var coordinate: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: latitude, longitude: longitude)
    }

    var hazardDisplayName: String {
        switch hazardType {
        case "pothole": return "Pothole"
        case "broken_sidewalk": return "Broken Sidewalk"
        case "crack": return "Crack"
        case "road_damage": return "Road Damage"
        default: return hazardType.replacingOccurrences(of: "_", with: " ").capitalized
        }
    }

    var severityColor: String {
        switch severity {
        case "critical": return "red"
        case "high": return "orange"
        case "medium": return "yellow"
        default: return "green"
        }
    }
}

// MARK: - Capture Data

struct CaptureData {
    let imageData: Data
    let depthMapData: Data?
    let latitude: Double
    let longitude: Double
    let capturedAt: Date
    let deviceInfo: [String: String]

    struct LidarMeasurements: Codable {
        let depthM: Double?
        let widthM: Double?
        let lengthM: Double?
        let surfaceAreaM2: Double?
        let volumeM3: Double?

        enum CodingKeys: String, CodingKey {
            case depthM = "depth_m"
            case widthM = "width_m"
            case lengthM = "length_m"
            case surfaceAreaM2 = "surface_area_m2"
            case volumeM3 = "volume_m3"
        }
    }

    var lidarMeasurements: LidarMeasurements?
}
