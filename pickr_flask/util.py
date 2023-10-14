import pandas as pd
from datetime import datetime
# from .models import db, Topic, ModeledTopic, Tweet, PickrUser, GeneratedPost, Niche
from .models import (
    db,
    ModeledTopic,
    Tweet,
    PickrUser,
    ActivityLog,
    GeneratedPost,
    Niche,
    RedditPost,
    Subreddit,
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
