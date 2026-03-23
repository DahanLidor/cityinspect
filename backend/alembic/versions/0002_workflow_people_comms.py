"""workflow, people, comms tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Add city_id + new fields to existing tables ───────────────────────────
    with op.batch_alter_table("tickets") as batch:
        batch.add_column(sa.Column("city_id", sa.String(64), nullable=False, server_default="default"))
        batch.add_column(sa.Column("score", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("current_step_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("protocol_id", sa.String(64), nullable=True))
        batch.add_column(sa.Column("sla_deadline", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("sla_breached", sa.Boolean(), nullable=False, server_default="0"))

    with op.batch_alter_table("detections") as batch:
        batch.add_column(sa.Column("city_id", sa.String(64), nullable=False, server_default="default"))

    # ── People ────────────────────────────────────────────────────────────────
    op.create_table(
        "people",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("city_id", sa.String(64), nullable=False, index=True),
        sa.Column("external_id", sa.String(64), nullable=False, index=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("role", sa.String(64), nullable=False),
        sa.Column("manager_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True),
        sa.Column("phone", sa.String(32), nullable=False, server_default=""),
        sa.Column("whatsapp_id", sa.String(32), nullable=False, server_default="", index=True),
        sa.Column("email", sa.String(128), nullable=False, server_default=""),
        sa.Column("specialties_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("availability_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("current_workload", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # ── WorkflowStep ──────────────────────────────────────────────────────────
    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("city_id", sa.String(64), nullable=False, index=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False, index=True),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("step_name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("owner_person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True),
        sa.Column("owner_role", sa.String(64), nullable=False, server_default=""),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_by_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True),
        sa.Column("action_taken", sa.String(64), nullable=True),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("skip_approved_by_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True),
    )

    # ── Rebuild work_orders (replaces old simple version) ─────────────────────
    # Note: old work_orders table had different schema; we alter it here
    with op.batch_alter_table("work_orders") as batch:
        batch.add_column(sa.Column("city_id", sa.String(64), nullable=False, server_default="default"))
        batch.add_column(sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=True))
        batch.add_column(sa.Column("assigned_person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True))
        batch.add_column(sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=True))
        batch.add_column(sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("protocol_id", sa.String(64), nullable=False, server_default=""))
        batch.add_column(sa.Column("team_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("materials_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("protocol_steps_json", sa.Text(), nullable=False, server_default="[]"))
        batch.add_column(sa.Column("estimated_hours", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("actual_hours", sa.Float(), nullable=True))

    # ── Conversations ─────────────────────────────────────────────────────────
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("city_id", sa.String(64), nullable=False, index=True),
        sa.Column("person_id", sa.Integer(), sa.ForeignKey("people.id"), nullable=False, index=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=False, index=True),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("state", sa.String(64), nullable=False, server_default="waiting_action"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_text", sa.Text(), nullable=True),
        sa.Column("pending_gates_json", sa.Text(), nullable=False, server_default="[]"),
    )

    # ── AuditLog ──────────────────────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("city_id", sa.String(64), nullable=False, index=True),
        sa.Column("ticket_id", sa.Integer(), sa.ForeignKey("tickets.id"), nullable=True, index=True),
        sa.Column("step_id", sa.String(64), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(128), nullable=False, server_default="system"),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("data_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True, index=True),
    )


def downgrade() -> None:
    op.drop_table("audit_log")
    op.drop_table("conversations")
    op.drop_table("workflow_steps")
    op.drop_table("people")
    with op.batch_alter_table("work_orders") as batch:
        for col in ["city_id", "ticket_id", "assigned_person_id", "approved_by_id",
                    "scheduled_start", "scheduled_end", "protocol_id", "team_json",
                    "materials_json", "protocol_steps_json", "estimated_hours",
                    "estimated_cost", "actual_hours"]:
            batch.drop_column(col)
    with op.batch_alter_table("detections") as batch:
        batch.drop_column("city_id")
    with op.batch_alter_table("tickets") as batch:
        for col in ["city_id", "score", "current_step_id", "protocol_id", "sla_deadline", "sla_breached"]:
            batch.drop_column(col)
