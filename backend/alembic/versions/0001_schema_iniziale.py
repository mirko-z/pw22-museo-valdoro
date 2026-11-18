"""Schema iniziale: utenti, eventi, prenotazioni, feedback.

Scritta a mano (non autogenerata) per rendere espliciti vincoli e indici
del modello dei dati. Il test tests/test_schema.py verifica che
il risultato coincida con i modelli ORM.

Revision ID: 0001
Revises:
Create Date: 2026-10-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# Nota: op.f("nome") indica ad Alembic che il nome è già definitivo. Senza,
# applicherebbe di nuovo la naming convention dei modelli (app/models/base.py)
# e il CHECK "ck_events_capacity_positive" diventerebbe "ck_events_ck_events_...".

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- users -------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(60), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("role", sa.String(10), server_default="visitor", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.CheckConstraint("role IN ('visitor', 'staff', 'admin')", name=op.f("ck_users_userrole")),
    )
    # Indice univoco su espressione: email senza distinzione tra maiuscole e minuscole
    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)

    # --- events ------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(8, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(10), server_default="scheduled", nullable=False),
        sa.Column("max_seats_per_booking", sa.Integer(), nullable=False),
        sa.Column("cancellation_deadline_hours", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_events")),
        sa.CheckConstraint("type IN ('guided_tour', 'workshop', 'conference')", name=op.f("ck_events_eventtype")),
        sa.CheckConstraint("status IN ('scheduled', 'cancelled')", name=op.f("ck_events_eventstatus")),
        sa.CheckConstraint("end_at > start_at", name=op.f("ck_events_end_after_start")),
        sa.CheckConstraint("capacity > 0", name=op.f("ck_events_capacity_positive")),
        sa.CheckConstraint("price >= 0", name=op.f("ck_events_price_non_negative")),
        sa.CheckConstraint(
            "max_seats_per_booking > 0 AND max_seats_per_booking <= capacity",
            name=op.f("ck_events_max_seats_valid"),
        ),
        sa.CheckConstraint("cancellation_deadline_hours >= 0", name=op.f("ck_events_deadline_non_negative")),
    )
    op.create_index("ix_events_start_at", "events", ["start_at"])

    # --- bookings ----------------------------------------------------------
    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(10), server_default="confirmed", nullable=False),
        sa.Column("code", sa.String(12), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_bookings")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_bookings_user_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_bookings_event_id_events"), ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("code", name=op.f("uq_bookings_code")),
        sa.CheckConstraint("status IN ('confirmed', 'cancelled')", name=op.f("ck_bookings_bookingstatus")),
        sa.CheckConstraint("seats > 0", name=op.f("ck_bookings_seats_positive")),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_bookings_cancelled_at_consistent"),
        ),
    )
    # Indice univoco PARZIALE: una sola prenotazione confermata per utente ed evento
    op.create_index(
        "uq_bookings_active",
        "bookings",
        ["user_id", "event_id"],
        unique=True,
        postgresql_where=sa.text("status = 'confirmed'"),
    )
    op.create_index("ix_bookings_event_id", "bookings", ["event_id"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])

    # --- feedback ----------------------------------------------------------
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_feedback")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_feedback_user_id_users"), ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["events.id"], name=op.f("fk_feedback_event_id_events"), ondelete="RESTRICT"
        ),
        sa.UniqueConstraint("user_id", "event_id", name=op.f("uq_feedback_user_id_event_id")),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name=op.f("ck_feedback_rating_range")),
        sa.CheckConstraint("char_length(comment) <= 1000", name=op.f("ck_feedback_comment_length")),
    )
    op.create_index("ix_feedback_event_id", "feedback", ["event_id"])


def downgrade() -> None:
    # Ordine inverso: prima le tabelle che hanno chiavi esterne verso le altre
    op.drop_table("feedback")
    op.drop_table("bookings")
    op.drop_table("events")
    op.drop_table("users")
