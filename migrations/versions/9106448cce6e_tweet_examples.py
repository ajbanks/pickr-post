"""tweet examples

Revision ID: 9106448cce6e
Revises: 76563eee15af
Create Date: 2023-12-24 03:00:01.155534

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '9106448cce6e'
down_revision = '76563eee15af'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
   
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.add_column(sa.Column('tweet_examples', sa.String(length=5000), nullable=True))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
   
    with op.batch_alter_table('user', schema=None) as batch_op:
        batch_op.drop_column('tweet_examples')

   
    # ### end Alembic commands ###
