# CityInspect — Municipal Infrastructure Hazard Detection System

A production-grade MVP for municipal inspectors to scan, report, and track infrastructure hazards such as potholes, broken sidewalks, cracks, and road damage using AI detection and LiDAR depth sensing.

---

## System Architecture

```
┌──────────────┐
│  iOS App     │  SwiftUI · ARKit · AVFoundation · CoreLocation
│  (Inspector) │
└──────┬───────┘
       │  HTTPS (multipart upload)
       ▼
┌──────────────┐     ┌───────────────┐
│  FastAPI     │────▶│  AI Service   │  YOLOv8 hazard classification
│  Backend     │     └───────────────┘
│              │     ┌───────────────┐
│              │────▶│  LiDAR Proc.  │  Depth map → geometry measurements
│              │     └───────────────┘
│              │     ┌───────────────┐
│              │────▶│  PostgreSQL   │  PostGIS spatial queries
│              │     │  + PostGIS    │
└──────────────┘     └───────────────┘
```

## Tech Stack

| Component         | Technology                              |
|-------------------|-----------------------------------------|
| Mobile App        | Swift 5.9, SwiftUI, ARKit, AVFoundation |
| Backend API       | Python 3.12, FastAPI, SQLAlchemy 2.0    |
| AI Detection      | YOLOv8 (Ultralytics), PyTorch           |
| LiDAR Processing  | NumPy, SciPy, custom depth pipeline     |
| Database          | PostgreSQL 16 + PostGIS 3.4             |
| Cache             | Redis 7                                 |
| Container Runtime | Docker + Docker Compose                 |

---

## Project Structure

```
cityinspect/
├── mobile-ios/                    # iOS application (Xcode project)
│   ├── CityInspect.xcodeproj/
│   └── CityInspect/
│       ├── CityInspectApp.swift   # App entry point
│       ├── Info.plist             # Permissions (Camera, GPS, LiDAR)
│       ├── Models/
│       │   └── Models.swift       # Data models & Codable structs
│       ├── Services/
│       │   ├── APIService.swift   # HTTP client for backend
│       │   ├── AuthManager.swift  # JWT authentication state
│       │   └── CaptureService.swift # Camera + LiDAR + GPS
│       └── Views/
│           ├── LoginView.swift
│           ├── MainTabView.swift
│           ├── IncidentCaptureView.swift
│           └── IncidentMapView.swift
│
├── backend/                       # FastAPI backend service
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── main.py               # FastAPI app + middleware
│   │   ├── config.py             # Environment-based settings
│   │   ├── database.py           # Async SQLAlchemy engine
│   │   ├── models/
│   │   │   ├── models.py         # ORM models (User, Incident, etc.)
│   │   │   └── schemas.py        # Pydantic request/response schemas
│   │   ├── routers/
│   │   │   ├── auth.py           # POST /login
│   │   │   └── incidents.py      # POST /incident/upload, GET /incident/{id}, GET /incidents/map
│   │   ├── services/
│   │   │   ├── ai_client.py      # HTTP client for AI microservice
│   │   │   ├── duplicate_detection.py  # GPS + image hash + LiDAR dedup
│   │   │   └── incident_service.py     # Core business logic orchestrator
│   │   └── utils/
│   │       ├── auth.py           # JWT + bcrypt helpers
│   │       └── storage.py        # Local / S3 file storage abstraction
│   └── tests/
│       └── test_api.py
│
├── ai-service/                    # AI detection microservice
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                   # FastAPI detection endpoint
│   └── hazard_detection.py       # YOLOv8 model wrapper + fallback
│
├── lidar-processing/              # LiDAR depth analysis library
│   ├── depth_processing.py       # Depth map → measurements pipeline
│   └── geometry_calculations.py  # RANSAC plane fit, surface area, volume
│
├── database/
│   ├── schema.sql                # Full PostgreSQL + PostGIS schema
│   └── migrations/
│       └── V001__initial_schema.sql
│
├── docker/
│   └── docker-compose.yml        # Full stack orchestration
│
└── docs/
    └── README.md                 # This file
```

---

## Quick Start

### Prerequisites

- **Docker** ≥ 24.0 and **Docker Compose** ≥ 2.20
- **Xcode** ≥ 15.0 (for iOS app)
- iPhone/iPad with LiDAR sensor (iPhone 12 Pro+, iPad Pro 2020+) for full functionality

### 1. Start the Backend Stack

```bash
cd cityinspect/docker

# Build and start all services
docker-compose up --build -d

# Verify services are running
docker-compose ps

# Check health endpoints
curl http://localhost:8000/health
curl http://localhost:8001/health
```

This starts:

| Service       | Port  | Description                     |
|---------------|-------|---------------------------------|
| Backend API   | 8000  | FastAPI with Swagger docs       |
| AI Service    | 8001  | YOLOv8 detection endpoint       |
| PostgreSQL    | 5432  | PostGIS-enabled database        |
| Redis         | 6379  | Cache and rate limiting         |

### 2. Open the iOS Project

```bash
cd cityinspect/mobile-ios
open CityInspect.xcodeproj
```

In Xcode:
1. Select your development team in **Signing & Capabilities**.
2. If testing on Simulator, the app connects to `localhost:8000`.
3. For a physical device, edit `APIService.swift` and replace `YOUR_SERVER_IP` with your backend host.
4. Build and run on an iPhone with LiDAR (iPhone 12 Pro or later).

### 3. Test the API Manually

Interactive API documentation is available at:
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

**Login:**
```bash
curl -X POST http://localhost:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "changeme123"}'
```

**Upload an Incident:**
```bash
curl -X POST http://localhost:8000/api/v1/incident/upload \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -F "image=@pothole.jpg" \
  -F "latitude=40.7128" \
  -F "longitude=-74.0060" \
  -F "captured_at=2025-01-15T10:30:00Z" \
  -F 'lidar_measurements={"depth_m":0.08,"width_m":0.45,"length_m":0.60,"surface_area_m2":0.27}'
```

**Get Map Incidents:**
```bash
curl -X GET "http://localhost:8000/api/v1/incidents/map?min_lat=40.70&max_lat=40.80&min_lon=-74.02&max_lon=-73.95" \
  -H "Authorization: Bearer <YOUR_TOKEN>"
```

---

## API Endpoints

| Method | Path                    | Auth     | Description                          |
|--------|-------------------------|----------|--------------------------------------|
| POST   | `/api/v1/login`         | Public   | Authenticate and receive JWT token   |
| POST   | `/api/v1/incident/upload` | Bearer | Upload image + LiDAR + GPS report   |
| GET    | `/api/v1/incident/{id}` | Bearer   | Retrieve a single incident           |
| GET    | `/api/v1/incidents/map` | Bearer   | List incidents in bounding box       |
| GET    | `/health`               | Public   | Backend health check                 |

---

## Database Schema

### Tables

- **users** — Inspector accounts with roles (inspector / supervisor / admin)
- **incidents** — Canonical hazard records with AI detection + LiDAR measurements
- **incident_reports** — Individual user submissions linked to incidents
- **incident_clusters** — Merged duplicate groups with similarity scores
- **audit_log** — Change tracking for compliance

### Spatial Indexing

All location columns use PostGIS `GEOGRAPHY(Point, 4326)` with GIST indexes for efficient proximity queries and duplicate detection.

---

## Duplicate Detection

When a new report is submitted, the system checks for existing incidents within a configurable radius (default: 25m) using three similarity signals:

| Signal           | Weight | Method                                  |
|------------------|--------|-----------------------------------------|
| GPS Proximity    | 40%    | PostGIS `ST_DWithin` spatial query      |
| Image Similarity | 40%    | Perceptual hash (pHash) comparison      |
| LiDAR Similarity | 20%    | Geometric ratio matching (depth/width)  |

Reports with combined score ≥ 0.65 are merged into the existing incident's cluster.

---

## Custom AI Model Training

The system ships with a YOLOv8 fallback. To train a custom model:

1. Collect labeled images of potholes, cracks, broken sidewalks, and road damage.
2. Format as YOLOv8 dataset with 4 classes (indices 0–3).
3. Train:
   ```bash
   yolo detect train data=hazards.yaml model=yolov8n.pt epochs=100 imgsz=640
   ```
4. Place the exported `best.pt` at `/models/yolov8_hazard.pt` (mounted via Docker volume).

---

## Environment Variables

See `backend/.env.example` for all configuration options. Key variables:

| Variable                    | Default                          | Description                     |
|-----------------------------|----------------------------------|---------------------------------|
| `SECRET_KEY`                | (change in production)           | JWT signing key                 |
| `DATABASE_URL`              | `postgresql+asyncpg://...`       | Async database connection       |
| `AI_SERVICE_URL`            | `http://ai-service:8001`         | AI microservice endpoint        |
| `STORAGE_BACKEND`           | `local`                          | `local` or `s3`                 |
| `DUPLICATE_GPS_RADIUS_M`    | `25.0`                           | Duplicate search radius         |

---

## Stopping the Stack

```bash
cd cityinspect/docker
docker-compose down          # Stop containers
docker-compose down -v       # Stop and remove volumes (resets DB)
```

---

## License

This project is provided as an MVP scaffold. Adapt licensing to your organization's requirements.
