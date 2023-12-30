"""tweet terms

Revision ID: 29f53a2e7e94
Revises: 9106448cce6e
Create Date: 2023-12-30 14:11:40.582814

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '29f53a2e7e94'
down_revision = '9106448cce6e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('twitter_term',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('niche_id', sa.UUID(), nullable=True),
    sa.Column('term', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['niche_id'], ['pickr.niche.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='pickr'
    )

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('twitter_term', schema='pickr')
    # ### end Alembic commands ###