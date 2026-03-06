-- Migration V001: Initial schema
-- Run with: psql -U cityinspect -d cityinspect -f V001__initial_schema.sql

\echo 'Applying V001__initial_schema ...'

BEGIN;

\i ../schema.sql

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INT PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO schema_migrations (version, description)
VALUES (1, 'Initial schema with PostGIS, users, incidents, reports, clusters');

COMMIT;

\echo 'V001 applied successfully.'
