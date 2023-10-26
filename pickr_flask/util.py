from datetime import datetime
from uuid import UUID

import pandas as pd
import shortuuid
from flask import render_template

from .constants import DATETIME_FRIENDLY_FMT
# from .models import db, Topic, ModeledTopic, Tweet, PickrUser, GeneratedPost, Niche
from .models import (ActivityLog, GeneratedPost, ModeledTopic, Niche,
                     PickrUser, RedditPost, Subreddit, db)
from .queries import get_scheduled_post, latest_post_edit

SHORTCODE_ALPHABET = "abcdefghijklmnopqrstuvwxyz1234567890"
URLSAFE_ALPHABET = SHORTCODE_ALPHABET + "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

shortcode_uuid = shortuuid.ShortUUID(alphabet=SHORTCODE_ALPHABET)
urlsafe_uuid = shortuuid.ShortUUID(alphabet=URLSAFE_ALPHABET)


def shortcode(uuid: UUID, prefix="post") -> str:
    short_uuid = shortcode_uuid.encode(uuid)[:8]
    return f"{prefix}_{short_uuid}"


def generated_post_info(generated_post_id: UUID, user_id: UUID):
    post_edit = latest_post_edit(generated_post_id, user_id)
    scheduled_post = get_scheduled_post(generated_post_id, user_id)

    if post_edit is None:
        text = (
            db.session.query(GeneratedPost.text)
            .filter_by(id=generated_post_id)
            .one()
        )[0]
    else:
        text = post_edit.text

    return text, scheduled_post


def render_post_html(
        generated_post_id: UUID,
        user_id: UUID,
        text: str,
        template_name="post.html",
        **kwargs,
):
    '''
    Render a generated post HTML fragment template including any edits,
    and showing if the post is scheduled or already tweeted.

    It can render these templates:
        post.html, post_edit.html, schedule_post.html
    '''
    scheduled_for = kwargs.pop("scheduled_for", None)
    posted_at = kwargs.pop("posted_at", None)
    tweet_id = kwargs.pop("tweet_id", None)

    scheduled_for_str = None
    posted_at_str = None
    tweet_url = None
    if scheduled_for is not None:
        scheduled_for_str = scheduled_for.strftime(DATETIME_FRIENDLY_FMT)
    if posted_at is not None:
        posted_at_str = posted_at.strftime(DATETIME_FRIENDLY_FMT)
    if tweet_id is not None:
        tweet_url = f"https://twitter.com/i/status/{tweet_id}"

    short_id = shortcode(generated_post_id)
    urlsafe_id = urlsafe_uuid.encode(generated_post_id)

    return render_template(
        template_name,
        post_text=text,
        post_id=urlsafe_id,
        posted_at=posted_at_str,
        scheduled_for=scheduled_for_str,
        tweet_url=tweet_url,
        short_id=short_id,
        **kwargs
    )


def render_post_html_from_id(
        generated_post_id: UUID,
        user_id: UUID,
        template_name="post.html",
        **kwargs
):
    '''
    Convenience function to call render_post_html
    '''
    text, scheduled_post = generated_post_info(generated_post_id, user_id)
    scheduled_for, posted_at, tweet_id = None, None, None
    if scheduled_post is not None:
        scheduled_for = scheduled_post.scheduled_for
        posted_at = scheduled_post.posted_at
        tweet_id = scheduled_post.tweet_id

    return render_post_html(
        generated_post_id,
        user_id,
        text,
        template_name=template_name,
        scheduled_for=scheduled_for,
        posted_at=posted_at,
        tweet_id=tweet_id,
        **kwargs
    )


def log_user_activity(user: PickrUser, event: str):
    """ log a user activity event in the acitivty database"""
    event_time = datetime.now()

    # log the acitivity in the database
    activity_log = ActivityLog(
        username=user.username,
        email=user.email,
        time=event_time,
        event=event,
    )

    db.session.add(activity_log)
    db.session.commit()


def load_initial_data(data):
    n = Niche.query.first()
    if n:
        return False

    user = PickrUser.query.filter(
        PickrUser.username == data["user"]["username"]
    ).first()
    if user:
        pass
    else:
        user = PickrUser(**data["user"])

    user.niches = Niche.query.filter(Niche.title.in_(data["topics"])).all()
    db.session.merge(user)
    db.session.commit()

    niche_df = pd.read_csv("pickr_flask/static/data/Niche.csv")
    niche_df = niche_df.replace({'is_active': {'True': True, 'False': False}})
    niche_df["is_active"] = niche_df["is_active"].astype(bool)
    niche_df["is_custom"] = niche_df["is_custom"].astype(bool)
    niche_dict = niche_df.to_dict(orient="records")
    topics = [Niche(**d) for d in niche_dict]
    for t in topics:
        t.is_active = True
        db.session.merge(t)
    db.session.commit()

    subreddit_df = pd.read_csv("pickr_flask/static/data/Subreddit.csv")
    # subreddit_df = subreddit_df.drop(columns=["id"])
    subreddit_rows = subreddit_df.to_dict(orient="records")
    subreddits = [Subreddit(**d) for d in subreddit_rows]
    for s in subreddits:
        db.session.merge(s)
    db.session.commit()

    topic_df = pd.read_csv("pickr_flask/static/data/ModelledTopic.csv")
    topic_rows = topic_df.to_dict(orient="records")
    topics = [ModeledTopic(**d) for d in topic_rows]
    for t in topics:
        db.session.merge(t)
    db.session.commit()

    gen_post_df = pd.read_csv("pickr_flask/static/data/GeneratedPost.csv")
    gen_post_rows = gen_post_df.to_dict(orient="records")
    gen_posts = [GeneratedPost(**d) for d in gen_post_rows]
    for g in gen_posts:
        db.session.merge(g)
    db.session.commit()

    reddit_post_df = pd.read_csv("pickr_flask/static/data/RedditPost.csv")
    reddit_post_rows = reddit_post_df.to_dict(orient="records")
    reddit_posts = [RedditPost(**d) for d in reddit_post_rows]
    for p in reddit_posts:
        db.session.merge(p)
    db.session.commit()
    return True
