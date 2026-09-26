"""add survey questionnaire processing history

Revision ID: f2a9c3d4e5b6
Revises: d1e7c9a4b621
Create Date: 2026-09-26
"""

from alembic import op
import sqlalchemy as sa


revision = "f2a9c3d4e5b6"
down_revision = "d1e7c9a4b621"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "survey_processing_questionnaires",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("processing_id", sa.Text(), nullable=False),
        sa.Column("client_id", sa.Text(), nullable=False),
        sa.Column("questionnaire_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["processing_id"],
            ["survey_processing_jobs.processing_id"],
            name="fk_survey_processing_questionnaires_processing_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "processing_id",
            "questionnaire_id",
            name="uq_survey_processing_questionnaires_processing_questionnaire",
        ),
    )
    op.create_index(
        "idx_survey_processing_questionnaires_lookup",
        "survey_processing_questionnaires",
        ["client_id", "questionnaire_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_survey_processing_questionnaires_processing_id",
        "survey_processing_questionnaires",
        ["processing_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_survey_processing_questionnaires_id"),
        "survey_processing_questionnaires",
        ["id"],
        unique=False,
    )

    # Backfill the client questionnaire jobs that already exist. The original
    # request payload is the authoritative source for questionnaire ids.
    op.execute(
        """
        INSERT INTO survey_processing_questionnaires (
            processing_id,
            client_id,
            questionnaire_id,
            created_at
        )
        SELECT
            job.processing_id,
            job.client_id,
            questionnaire.value ->> 'id',
            job.created_at
        FROM survey_processing_jobs AS job
        CROSS JOIN LATERAL jsonb_array_elements(
            COALESCE(job.request_payload_json -> 'questionnaires', '[]'::jsonb)
        ) AS questionnaire(value)
        WHERE job.client_id IS NOT NULL
          AND questionnaire.value ? 'id'
          AND NULLIF(BTRIM(questionnaire.value ->> 'id'), '') IS NOT NULL
        ON CONFLICT (processing_id, questionnaire_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_survey_processing_questionnaires_id"),
        table_name="survey_processing_questionnaires",
    )
    op.drop_index(
        "idx_survey_processing_questionnaires_processing_id",
        table_name="survey_processing_questionnaires",
    )
    op.drop_index(
        "idx_survey_processing_questionnaires_lookup",
        table_name="survey_processing_questionnaires",
    )
    op.drop_table("survey_processing_questionnaires")
