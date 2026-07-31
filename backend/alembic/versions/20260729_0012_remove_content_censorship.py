"""移除系统级题材内容审查规则。

Revision ID: 0012
Revises: 0011
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM craft_rules "
            "WHERE rule_text LIKE :political OR rule_text LIKE :adult"
        ).bindparams(political="%涉政涉黄%", adult="%色情内容%")
    )


def downgrade() -> None:
    # 内容审查属于产品策略，不在回滚结构迁移时自动恢复。
    pass
