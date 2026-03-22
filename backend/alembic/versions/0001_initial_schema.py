"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-03-22

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("full_name", sa.String(128), nullable=False),
        sa.Column("hashed_pw", sa.String(256), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="field_team"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "work_orders",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("title", sa.String(256), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("team", sa.String(128), nullable=False, server_default=""),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ticket_ids_json", sa.Text(), nullable=False, server_default="[]"),
    )

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("defect_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("address", sa.String(256), nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("detection_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id"), nullable=True),
    )

    op.create_table(
        "detections",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("vehicle_id", sa.String(64), nullable=False, server_default="UNKNOWN"),
        sa.Column("vehicle_model", sa.String(128), nullable=False, server_default="Unknown"),
        sa.Column("vehicle_sensor_version", sa.String(32), nullable=False, server_default="v1.0"),
        sa.Column("vehicle_speed_kmh", sa.Float(), nullable=False, server_default="0"),
        sa.Column("vehicle_heading_deg", sa.Float(), nullable=False, server_default="0"),
        sa.Column("reported_by", sa.String(32), nullable=False, server_default="system"),
        sa.Column("reporter_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("defect_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lng", sa.Float(), nullable=False),
        sa.Column("defect_length_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("defect_width_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("defect_depth_cm", sa.Float(), nullable=False, server_default="0"),
        sa.Column("defect_volume_m3", sa.Float(), nullable=False, server_default="0"),
        sa.Column("repair_material_m3", sa.Float(), nullable=False, server_default="0"),
        sa.Column("surface_area_m2", sa.Float(), nullable=False, server_default="0"),
        sa.Column("ambient_temp_c", sa.Float(), nullable=False, server_default="25"),
        sa.Column("asphalt_temp_c", sa.Float(), nullable=False, server_default="28"),
        sa.Column("weather_condition", sa.String(32), nullable=False, server_default="Clear"),
        sa.Column("wind_speed_kmh", sa.Float(), nullable=False, server_default="10"),
        sa.Column("humidity_pct", sa.Float(), nullable=False, server_default="50"),
        sa.Column("visibility_m", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("image_url", sa.String(512), nullable=False, server_default=""),
        sa.Column("image_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("image_caption", sa.String(512), nullable=False, server_default=""),
        sa.Column("notes", sa.Text(), nullable=False, server_default=""),
        sa.Column("pipeline_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("detections")
    op.drop_table("tickets")
    op.drop_table("work_orders")
    op.drop_table("users")
