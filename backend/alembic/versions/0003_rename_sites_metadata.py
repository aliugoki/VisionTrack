"""Rename sites.metadata to sites.attributes.

The name `metadata` clashes with SQLAlchemy's reserved attribute on
Base classes, which broke Pydantic's from_attributes validation.

Revision ID: 0003_rename_sites_metadata
Revises: 0002_sites_and_cameras
Create Date: 2026-06-02
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0003_rename_sites_metadata"
down_revision: Union[str, None] = "0002_sites_and_cameras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("sites", "metadata", new_column_name="attributes")


def downgrade() -> None:
    op.alter_column("sites", "attributes", new_column_name="metadata")