"""materialtype add glass value

Revision ID: c9d8e7f6a5b4
Revises: b3f7c9d21a44
Create Date: 2026-09-15 04:00:00.000000

SCOPE domain correction: several SCOPE.pdf commercial rows (Progressive
"White Glass"/"Photo Glass" rows, Single Vision glass row, Diving "White
Glass") are genuinely mineral GLASS, not any existing MaterialType value.
CR39/POLYCARBONATE/TRIVEX/HIGH_INDEX_* are all false for these rows and were
never an acceptable placeholder - this migration adds the missing truthful
value rather than continuing to misrepresent glass rows as CR39.

Purely additive: one new enum member (GLASS = "glass"). No existing row's
material changes as a result of this migration alone - the follow-up data
correction (re-pointing the affected SCOPE rows from CR39 to GLASS) is a
separate, ordinary CRUD update, not part of this schema change.

On SQLite (this project's default DATABASE_URL) the `lens_variants.material`
column is a plain VARCHAR with no CHECK constraint (confirmed against the
live schema) - the new value needs no DDL there at all, only the ORM-side
Python enum gains the member. On PostgreSQL, `Enum(MaterialType)` creates a
native TYPE ("materialtype") that must be altered explicitly, hence this
migration. `ADD VALUE` cannot run inside an ordinary transaction on
PostgreSQL < 12, so it is issued inside Alembic's autocommit block.

PostgreSQL provides no `DROP VALUE` for enum types, so downgrade() cannot
truly remove "glass" once added; it is a documented no-op there.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, Sequence[str], None] = "b3f7c9d21a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE materialtype ADD VALUE IF NOT EXISTS 'glass'")
    # SQLite and other non-native-enum dialects: no DDL needed - the column
    # is an unconstrained VARCHAR; only the Python-side enum changes.


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE - an added enum value
    # cannot be safely removed without recreating the type and rewriting
    # every dependent column. Left as a documented no-op; do not attempt to
    # reverse this on a database that already has GLASS-valued rows.
    pass
