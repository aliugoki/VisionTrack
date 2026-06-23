"""make person_embeddings.person_id nullable

Revision ID: 0014_embedding_person_nullable
Revises: 0013_persons
Create Date: 2026-06-08

Background
----------
In P2.1 we created `person_embeddings.person_id` as NOT NULL with a
FK to `persons`. The original intent was that every embedding belongs
to a known person.

In P2.3 we add the DeepStream embedding pipeline that publishes ReID
features from every detected track. At that point, we don't yet know
which Person the embedding belongs to — the cross-camera matcher
(P2.5) is what reads accumulated embeddings and decides "these N
embeddings belong to the same person, create / merge a Person row."

So we need person_id to be nullable until the matcher claims it.

The PersonEmbedding model docstring already hinted at this design:
'sparse storage by design ... matcher reads accumulated embeddings'.
The NOT NULL constraint was an oversight.

Rollback path
-------------
downgrade() restores NOT NULL. Before running downgrade in prod you
MUST clean up any orphan embeddings:
    DELETE FROM person_embeddings WHERE person_id IS NULL;
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0014_embedding_person_nullable"
down_revision = "0013_persons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "person_embeddings",
        "person_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=True,
    )


def downgrade() -> None:
    # WARNING: will fail if there are NULL person_id rows in the table.
    # Production downgrades must clean those up first.
    op.alter_column(
        "person_embeddings",
        "person_id",
        existing_type=sa.dialects.postgresql.UUID(),
        nullable=False,
    )
