import enum

from flask_login import UserMixin
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import uuid4
from . import db

DEFAULT_SCHEMA = "pickr"


def _to_dict(obj):
    return dict((col, getattr(obj, col))
                for col in obj.__table__.columns.keys())


user_niche_assoc = db.Table(
    "user_niche_assoc",
    db.Column(
        "user_id",
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.user.id"),
        primary_key=True,
    ),
    db.Column(
        "niche_id",
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.niche.id"),
        primary_key=True,
    ),
    schema=DEFAULT_SCHEMA,
)


tweet_modeled_topic_assoc = db.Table(
    "tweet_modeled_topic_assoc",
    db.Column(
        "tweet_id",
        BigInteger,
        ForeignKey(f"{DEFAULT_SCHEMA}.tweet.id"),
        primary_key=True,
    ),
    db.Column(
        "modeled_topic_id",
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.modeled_topic.id"),
        primary_key=True,
    ),
    schema=DEFAULT_SCHEMA,
)


reddit_modeled_topic_assoc = db.Table(
    "reddit_modeled_topic_assoc",
    db.Column(
        "reddit_id",
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.reddit.id"),
        primary_key=True,
    ),
    db.Column(
        "modeled_topic_id",
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.modeled_topic.id"),
        primary_key=True,
    ),
    schema=DEFAULT_SCHEMA,
)


class ActivityLog(UserMixin, db.Model):
    """ActivityLog represents one of our activity tracking events."""

    __tablename__ = "activity_log"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), nullable=False, unique=False)
    email = Column(String(40), unique=False, nullable=False)
    time = Column(DateTime, nullable=True)
    event = Column(String(150), nullable=False)

    def __repr__(self):
        return f"<ActivityLog event={self.event} username={self.username} time={self.time}>"


class PickrUser(UserMixin, db.Model):
    """PickrUser represents one of our users."""
    __tablename__ = "user"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    username = Column(String(100), nullable=False, unique=False)
    email = Column(String(40), unique=True, nullable=False)
    password = Column(String(200), nullable=False)
    created_at = Column(DateTime, nullable=True)
    last_login = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, nullable=True, default=func.now())
    # niches the user chose
    niches = relationship("Niche", secondary=user_niche_assoc)
    stripe_subscriptions = relationship("StripeSubscription")

    def __repr__(self):
        return f"<PickrUser id={self.id} username={self.username}>"


class Schedule(db.Model):
    """Schedule represents a users schedule."""
    __tablename__ = "schedule"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    schedule_text = Column(String(10000), nullable=False)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.user.id")
    )
    schedule_creation_date = Column(DateTime, nullable=False, default=func.now())


class SchedulePost(db.Model):
    """ScheSchedulePostdule represents a post for a Schedule."""
    __tablename__ = "schedulepost"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    schedule_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.schedule.id"),
        index=True
    )
    post_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.generated_post.id"),
        index=True
    )
    celery_id = Column(UUID(as_uuid=True), nullable=True)


class StripeSubscriptionStatus(enum.Enum):
    """Status for StripeAPI subscription"""
    active = 'active'
    incomplete = 'incomplete'
    incomplete_expired = 'incomplete_expired'
    past_due = 'past_due'
    canceled = 'canceled'
    unpaid = 'unpaid'
    paused = 'paused'
    trialing = 'trialing'


class StripeSubscription(db.Model):
    """
    StripeSubscription records Stripe subscription information for users.
    """
    __tablename__ = "stripe_subscription"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(ENUM(StripeSubscriptionStatus), nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.user.id")
    )
    stripe_customer_id = Column(String(255), nullable=False)
    stripe_subscription_id = Column(String(255), nullable=False)
    stripe_invoice_id = Column(String(255), nullable=False)

    def __repr__(self):
        return f"<StripeSubscription id={self.stripe_subscription_id}>"


class ModeledTopic(db.Model):
    """
    ModeledTopic represents a topic computed from a topic model.
    The relation to Tweets is many-to-many.
    The relation to GeneratedPosts in one-to-many.
    """
    __tablename__ = "modeled_topic"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(1000), nullable=True)
    description = Column(String, nullable=True)
    size = Column(Integer, nullable=False, default=0)
    trend_type = Column(String(32), nullable=True)
    niche_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.niche.id")
    )
    date = Column(DateTime, nullable=True)
    # posts generated for this topic generated by GPT etc.
    generated_posts = relationship("GeneratedPost")
    reddit_posts = relationship(
        "RedditPost", secondary=reddit_modeled_topic_assoc
    )

    # tweets that the model clustered into this topic.
    # tweets = relationship("Tweet", secondary=tweet_modeled_topic_assoc)

    def __repr__(self):
        return f"<ModeledTopic id={self.id}>"


class GeneratedPost(db.Model):
    __tablename__ = "generated_post"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    text = Column(String, nullable=False)
    information_type = Column(String(64), nullable=True)
    # The topic label generated by GPT.
    # This is different from ModeledTopic.name
    topic_label = Column(String, nullable=True)
    modeled_topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.modeled_topic.id"),
        index=True
    )


class Subreddit(db.Model):
    """
    Table associating ids with the subreddit names
    """
    __tablename__: str = "subreddit"
    __table_args__: str = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    reddit_id = Column(String(64), nullable=True)
    niche_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.niche.id"),
        nullable=True
    )
    title = Column(String(255), nullable=True)

    def __repr__(self):
        return f"<Subreddit title={self.title}>"


class RedditPost(db.Model):
    """
    Table to store the reddit posts that has been scraped from the API
    """
    __tablename__: str = "reddit"
    __table_args__: str = {"schema": DEFAULT_SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    reddit_id = Column(
        String(64),
        index=True,
        unique=True,
    )
    author = Column(String(128))
    title = Column(String)
    body = Column(String)
    score = Column(Integer)
    created_at = Column(DateTime, nullable=True)
    url = Column(String)
    clean_text = Column(String)  # processed title + body
    subreddit_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.subreddit.id"),
        nullable=True,
        default=None,
    )

    def __repr__(self):
        return f"<RedditPost id={self.id} url={self.url}>"


class Niche(db.Model):
    """
    Niche represents a topic or area of interest that a user chooses.
    The relation to "ModeledTopic" and "Subreddit" is one-to-many.
    """
    __tablename__ = "niche"
    __table_args__ = {"schema": DEFAULT_SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(255), nullable=False)
    category = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=True, default=func.now())
    is_active = Column(Boolean, default=False, nullable=False)
    is_custom = Column(Boolean, default=False, nullable=False)
    # ModeledTopics that were derived from this "Niche"
    modeled_topics = relationship("ModeledTopic")
    # Subreddits relevant to this niche
    subreddits = relationship("Subreddit")

    def __repr__(self):
        return f"<Niche id={self.id} title={self.title}>"


class Tweet(db.Model):
    """Tweet represents a tweet scraped from Twitter."""
    __tablename__: str = "tweet"
    __table_args__: str = {"schema": DEFAULT_SCHEMA}

    # same as twitter's ID
    id = Column(BigInteger, primary_key=True)
    url = Column(String(255), nullable=True)
    username = Column(String(255), nullable=False)
    text = Column(String, nullable=True)
    created_at = Column(String, nullable=True)
    author_id = Column(Integer, nullable=True)
    retweets = Column(Integer, nullable=True)
    likes = Column(Integer, nullable=True)
    retweet_id = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=True, server_default=func.now())

    def __repr__(self):
        return f"<Tweet id={self.id}>"
