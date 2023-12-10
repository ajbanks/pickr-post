"""news api

Revision ID: df4c3ab833fd
Revises: 69c51049ad4f
Create Date: 2023-11-17 19:50:02.928634

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'df4c3ab833fd'
down_revision = '69c51049ad4f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('news_article',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(), nullable=True),
    sa.Column('url', sa.String(), nullable=True),
    sa.Column('published_date', sa.DateTime(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    schema='pickr'
    )
    op.create_table('news_api_term',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('niche_id', sa.UUID(), nullable=True),
    sa.Column('term', sa.String(length=255), nullable=True),
    sa.ForeignKeyConstraint(['niche_id'], ['pickr.niche.id'], ),
    sa.PrimaryKeyConstraint('id'),
    schema='pickr'
    )
    op.create_table('news_modeled_topic_assoc',
    sa.Column('news_id', sa.UUID(), nullable=False),
    sa.Column('modeled_topic_id', sa.UUID(), nullable=False),
    sa.ForeignKeyConstraint(['modeled_topic_id'], ['pickr.modeled_topic.id'], ),
    sa.ForeignKeyConstraint(['news_id'], ['pickr.news_article.id'], ),
    sa.PrimaryKeyConstraint('news_id', 'modeled_topic_id'),
    schema='pickr'
    )
    with op.batch_alter_table('modeled_topic', schema=None) as batch_op:
        batch_op.add_column(sa.Column('trend_class', sa.String(length=32), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table('modeled_topic', schema=None) as batch_op:
        batch_op.drop_column('trend_class')

    op.drop_table('news_modeled_topic_assoc', schema='pickr')
    op.drop_table('news_api_term', schema='pickr')
    op.drop_table('news_article', schema='pickr')
    # ### end Alembic commands ###