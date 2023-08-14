import enum

import numpy as np
from flask_login import UserMixin
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID  # , ARRAY
from flask_login import UserMixin
from uuid import uuid4
from . import db

DEFAULT_SCHEMA = "pickr"

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
    niches = relationship("Niche", secondary=user_niche_assoc)  # many to many
    stripe_subscriptions = relationship("StripeSubscription")

    def __repr__(self):
        return f"<PickrUser id={self.id} username={self.username}>"


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
    status = Column(Enum(StripeSubscriptionStatus), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey(f"{DEFAULT_SCHEMA}.user.id"))
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
    description = Column(String(1000), nullable=True)
    size = Column(Integer, nullable=False, default=0)
    trend_type = Column(String(32), nullable=True)
    niche_id = Column(UUID(as_uuid=True), ForeignKey(f"{DEFAULT_SCHEMA}.niche.id"))
    date = Column(DateTime, nullable=True)
    # posts generated for this topic generated by GPT etc.
    generated_posts = relationship("GeneratedPost")
    reddit_posts = relationship("RedditPost")
    # tweets that the model clustered into this topic.
    tweets = relationship("Tweet", secondary=tweet_modeled_topic_assoc)

    def __repr__(self):
        return f"<ModeledTopic id={self.id} title={self.name}>"


class GeneratedPost(db.Model):
    __tablename__ = "generated_post"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    topic_label = Column(String, nullable=True)
    text = Column(String, nullable=False)
    information_type = Column(String, nullable=True)
    modeled_topic_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{DEFAULT_SCHEMA}.modeled_topic.id")
    )


class Subreddit(db.Model):
    """
    Table associating ids with the subreddit names
    """

    __tablename__: str = "subreddit"
    __table_args__: str = {"schema": DEFAULT_SCHEMA}
    # same as twitter's ID
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    niche_id = Column(
        UUID(as_uuid=True), ForeignKey(f"{DEFAULT_SCHEMA}.niche.id"), nullable=True
    )
    title = Column(String(255), nullable=True)
    # reddit_post = relationship("RedditPost", back_populates="subreddit")
    def __repr__(self):
        return f"<Subreddit id={self.id}>"


class RedditPost(db.Model):
    """
    Table to store the reddit posts that has been scraped from the API
    """

    __tablename__: str = "reddit"
    __table_args__: str = {"schema": DEFAULT_SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String)
    body = Column(String)
    score = Column(Integer)
    date = Column(DateTime, nullable=True)
    link = Column(String)
    modeled_topic_id = Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.modeled_topic.id"),
        nullable=True,
        default=uuid4,
    )
    """Column(
        UUID(as_uuid=True),
        ForeignKey(f"{DEFAULT_SCHEMA}.subreddit.id"),
        nullable=True,
        default=None,
    )"""
    # modeled_topic = relationship("ModeledTopic", back_populates="modeled_topic")
    # subreddit = relationship("Subreddit", back_populates="reddit_post")

    def __repr__(self):
        return f"<YourTableName id={self.id} title={self.title}>"


class Niche(db.Model):
    """
    Topic represents a topic or area of interest that a user chooses.
    The relation to "ModeledTopic" is one-to-many.
    """

    __tablename__ = "niche"
    __table_args__ = {"schema": DEFAULT_SCHEMA}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(255), nullable=False)  # this is more like niche
    category = Column(String(255), nullable=True)
    updated_at = Column(DateTime, nullable=True, default=func.now())
    is_active = Column(Boolean, default=False, nullable=False)
    is_custom = Column(Boolean, default=False, nullable=False)
    # ModeledTopics that were derived from this "Niche"
    modeled_topics = relationship("ModeledTopic")

    def __repr__(self):
        return f"<Topic id={self.id} title={self.title}>"


"""
Twitter classes
"""


class TwitterUser(db.Model):
    """
    TwitterUser represents a user account scraped from Twitter.
    """

    __tablename__ = "twitter_user"
    __table_args__ = {"schema": DEFAULT_SCHEMA}
    # same as twitter's ID
    id = Column(BigInteger, primary_key=True)
    username = Column(String, nullable=True)
    name = Column(String, nullable=True)
    followers_count = Column(Integer, nullable=True)
    tweet_count = Column(Integer, nullable=True)
    updated_at = Column(DateTime, nullable=True, server_default=func.now())

    def __repr__(self) -> str:
        return f"<TwitterUser username={self.username} id={self.id}"


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