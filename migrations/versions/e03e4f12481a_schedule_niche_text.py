"""schedule niche text

Revision ID: e03e4f12481a
Revises: 5fb94ed2a466
Create Date: 2024-01-17 23:20:28.997083

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'e03e4f12481a'
down_revision = '5fb94ed2a466'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('schedule_topic_assoc',
    sa.Column('schedule_id', sa.Integer(), nullable=False),
    sa.Column('modeled_topic_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['modeled_topic_id'], ['pickr.modeled_topic.id'], ),
    sa.ForeignKeyConstraint(['schedule_id'], ['pickr.schedule.id'], ),
    sa.PrimaryKeyConstraint('schedule_id', 'modeled_topic_id'),
    schema='pickr'
    )

    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.add_column(sa.Column('schedule_niche_text', sa.String(length=10000), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    
    with op.batch_alter_table('schedule', schema=None) as batch_op:
        batch_op.drop_column('schedule_niche_text')

    op.drop_table('schedule_topic_assoc', schema='pickr')
    # ### end Alembic commands ###
