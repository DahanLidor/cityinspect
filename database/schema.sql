-- CityInspect Database Schema
-- PostgreSQL 15+ with PostGIS extension

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- ENUM TYPES
-- ============================================================

CREATE TYPE hazard_type AS ENUM (
    'pothole',
    'broken_sidewalk',
    'crack',
    'road_damage'
);

CREATE TYPE incident_severity AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);

CREATE TYPE incident_status AS ENUM (
    'reported',
    'confirmed',
    'in_progress',
    'resolved',
    'dismissed'
);

CREATE TYPE user_role AS ENUM (
    'inspector',
    'supervisor',
    'admin'
);

-- ============================================================
-- USERS TABLE
-- ============================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(64) UNIQUE NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    full_name       VARCHAR(128) NOT NULL,
    role            user_role NOT NULL DEFAULT 'inspector',
    department      VARCHAR(128),
    badge_number    VARCHAR(32),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_users_username ON users (username);
CREATE INDEX idx_users_email ON users (email);

-- ============================================================
-- INCIDENTS TABLE (canonical hazard records)
-- ============================================================

CREATE TABLE incidents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    hazard_type         hazard_type NOT NULL,
    severity            incident_severity NOT NULL DEFAULT 'medium',
    status              incident_status NOT NULL DEFAULT 'reported',
    location            GEOGRAPHY(Point, 4326) NOT NULL,
    address             VARCHAR(512),
    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,

    -- AI detection metadata
    ai_confidence       FLOAT CHECK (ai_confidence >= 0 AND ai_confidence <= 1),
    ai_model_version    VARCHAR(32),

    -- LiDAR measurements (metres)
    depth_m             FLOAT,
    width_m             FLOAT,
    length_m            FLOAT,
    surface_area_m2     FLOAT,
    volume_m3           FLOAT,

    -- media
    image_url           VARCHAR(1024),
    depth_map_url       VARCHAR(1024),
    thumbnail_url       VARCHAR(1024),

    report_count        INT NOT NULL DEFAULT 1,
    first_reported_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_reported_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at         TIMESTAMPTZ,

    created_by          UUID REFERENCES users(id),
    assigned_to         UUID REFERENCES users(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_incidents_location ON incidents USING GIST (location);
CREATE INDEX idx_incidents_status ON incidents (status);
CREATE INDEX idx_incidents_hazard_type ON incidents (hazard_type);
CREATE INDEX idx_incidents_created_at ON incidents (created_at DESC);

-- ============================================================
-- INCIDENT REPORTS (individual user submissions)
-- ============================================================

CREATE TABLE incident_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    incident_id         UUID REFERENCES incidents(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES users(id),

    latitude            DOUBLE PRECISION NOT NULL,
    longitude           DOUBLE PRECISION NOT NULL,
    location            GEOGRAPHY(Point, 4326) NOT NULL,

    image_url           VARCHAR(1024) NOT NULL,
    depth_map_url       VARCHAR(1024),
    image_hash          VARCHAR(128),

    -- raw AI results for this report
    ai_hazard_type      hazard_type,
    ai_confidence       FLOAT,
    ai_raw_output       JSONB,

    -- raw LiDAR results for this report
    lidar_depth_m       FLOAT,
    lidar_width_m       FLOAT,
    lidar_length_m      FLOAT,
    lidar_area_m2       FLOAT,
    lidar_raw_output    JSONB,

    device_info         JSONB,
    captured_at         TIMESTAMPTZ NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reports_incident ON incident_reports (incident_id);
CREATE INDEX idx_reports_user ON incident_reports (user_id);
CREATE INDEX idx_reports_location ON incident_reports USING GIST (location);

-- ============================================================
-- INCIDENT CLUSTERS (merged duplicate detection groups)
-- ============================================================

CREATE TABLE incident_clusters (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    canonical_incident  UUID NOT NULL REFERENCES incidents(id),
    centroid            GEOGRAPHY(Point, 4326),
    radius_m            FLOAT,
    report_count        INT NOT NULL DEFAULT 1,
    gps_similarity      FLOAT,
    image_similarity    FLOAT,
    lidar_similarity    FLOAT,
    merged_incident_ids UUID[] NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_clusters_centroid ON incident_clusters USING GIST (centroid);
CREATE INDEX idx_clusters_canonical ON incident_clusters (canonical_incident);

-- ============================================================
-- AUDIT LOG
-- ============================================================

CREATE TABLE audit_log (
    id              BIGSERIAL PRIMARY KEY,
    entity_type     VARCHAR(64) NOT NULL,
    entity_id       UUID NOT NULL,
    action          VARCHAR(32) NOT NULL,
    actor_id        UUID REFERENCES users(id),
    old_data        JSONB,
    new_data        JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON audit_log (entity_type, entity_id);

-- ============================================================
-- FUNCTIONS & TRIGGERS
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_users_updated
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_incidents_updated
    BEFORE UPDATE ON incidents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_clusters_updated
    BEFORE UPDATE ON incident_clusters
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- SEED DATA
-- ============================================================

INSERT INTO users (username, email, password_hash, full_name, role, department, badge_number)
VALUES (
    'admin',
    'admin@cityinspect.local',
    -- bcrypt hash of "changeme123"
    '$2b$12$LJ3m4ys3Lk0TSwHjfT4wCOBMnLq7bR.xG9dKFLgH6jR5VkXm1pJWe',
    'System Administrator',
    'admin',
    'IT',
    'ADMIN-001'
);
