"""add oauth session table

Revision ID: cab042341f2f
Revises: 035e1d42485e
Create Date: 2023-10-17 15:22:44.123255

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'cab042341f2f'
down_revision = '035e1d42485e'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('oauth_session',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('oauth_token', sa.String(length=64), nullable=False),
    sa.Column('oauth_token_secret', sa.String(length=64), nullable=False),
    sa.Column('access_token', sa.String(length=64), nullable=True),
    sa.Column('access_token_secret', sa.String(length=64), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['pickr.user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='pickr'
    )
    with op.batch_alter_table('oauth_session', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_pickr_oauth_session_oauth_token'), ['oauth_token'], unique=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('oauth_session', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_pickr_oauth_session_oauth_token'))

    op.drop_table('oauth_session', schema='pickr')
    # ### end Alembic commands ###