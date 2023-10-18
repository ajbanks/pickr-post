from typing import List

from sqlalchemy.orm import Query
from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import UUID

from .models import (
    RedditPost,
    ModeledTopic,
    GeneratedPost,
    PostEdit,
    Schedule,
    ScheduledPost,
    OAuthSession,
    reddit_modeled_topic_assoc,
)

###############################################################################
# Query util functions


def latest_post_edit(generated_post_id, user_id) -> PostEdit:
    '''Look up the user's most recent edit for a generated post, if any.'''
    return (
        PostEdit.query.join(GeneratedPost)
        .filter(
            and_(
                PostEdit.generated_post_id == GeneratedPost.id,
                GeneratedPost.id == generated_post_id,
                PostEdit.user_id == user_id,
            )
        )
        .order_by(PostEdit.id.desc())
        .limit(1)
        .first()
    )


def latest_user_schedule(user_id):
    '''Look up most recent schedule for user'''
    return (
        Schedule.query
        .filter(Schedule.user_id == user_id)
        .order_by(Schedule.schedule_creation_date.desc())
        .first()
    )


def get_scheduled_post(generated_post_id, user_id):
    '''Look up scheduled post by user and generated post'''
    return (
        ScheduledPost.query
        .filter(
            and_(
                ScheduledPost.user_id == user_id,
                ScheduledPost.generated_post_id == generated_post_id
            )
        )
        .order_by(ScheduledPost.id.desc())
        .first()
    )


def oauth_session_by_token(oauth_token) -> OAuthSession:
    return (
        OAuthSession.query
        .filter(OAuthSession.oauth_token == oauth_token)
        .order_by(OAuthSession.id.desc())
        .first()
    )


def oauth_session_by_user(user_id) -> OAuthSession:
    return (
        OAuthSession.query
        .filter(OAuthSession.user_id == user_id)
        .order_by(OAuthSession.id.desc())
        .first()
    )


def reddit_posts_for_topic_query(topic_id) -> Query:
    '''
    Return a query object that looks up reddit posts
    associated to a topic
    '''
    return (
        RedditPost.query
        .join(reddit_modeled_topic_assoc)
        .join(ModeledTopic)
        .filter(
            and_(
                RedditPost.id == reddit_modeled_topic_assoc.c.reddit_id,
                ModeledTopic.id == topic_id
            )
        )
    )


def top_modeled_topic_query(niche_ids: List[UUID]) -> Query:
    '''
    Return a query object that returns top recent modeled topics
    for a list of niches.
    '''
    return (
        ModeledTopic.query
        .filter(
            and_(
                ModeledTopic.niche_id.in_(niche_ids),
                ModeledTopic.generated_posts.any(),
            )
        )
        .order_by(
            ModeledTopic.date.desc(),
            ModeledTopic.size.desc()
        )
    )
