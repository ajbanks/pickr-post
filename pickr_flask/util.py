import numpy as np
import pandas as pd

# from .models import db, Topic, ModeledTopic, Tweet, PickrUser, GeneratedPost, Niche
from .models import (
    db,
    ModeledTopic,
    Tweet,
    PickrUser,
    GeneratedPost,
    Niche,
    RedditPost,
    Subreddit,
)

# testing how to save modeled topic
def save_model_result(model_result):
    user = (
        db.session.query(PickrUser).filter(PickrUser.username == "testuser555").first()
    )
    user_top = user.topics[0]

    fields = ["model_title", "title", "description", "size", "trend_type"]
    modeled_top = ModeledTopic(**{k: model_result[k] for k in fields})
    user_top.modeled_topics.append(modeled_top)

    modeled_top.tweets.extend(
        [Tweet(**d) for d in model_result["tweets"]],
    )

    db.session.commit()

def load_initial_data(data):
    n = Niche.query.first()
    if n:
        return False

    

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
    reddit_post_df["modeled_topic_id"] = reddit_post_df["modeled_topic_id"].fillna('68e45622-0c4c-41b5-ab58-b4390757d32d')
    reddit_post_rows = reddit_post_df.to_dict(orient="records")
    reddit_posts = [RedditPost(**d) for d in reddit_post_rows]
    for p in reddit_posts:
        db.session.merge(p)
    db.session.commit()

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

    return True
