import logging
from datetime import datetime, timedelta
from os import environ
from typing import Union, List
from .x_caller import X_Caller
import pandas as pd
import praw
import emoji
import nltk
from sqlalchemy import exc, insert
import re
from topic_model.util import normalise_tweet, parse_html

from .models import (
    db,
    Niche, ModeledTopic, GeneratedPost,
    Tweet,TwitterTerm,
    tweet_modeled_topic_assoc
)


reddit = praw.Reddit(
    client_id=environ["REDDIT_CLIENT_ID"],
    client_secret=environ["REDDIT_CLIENT_SECRET"],
    user_agent=environ["REDDIT_USER_AGENT"]
)


def _to_dict(post: praw.models.Submission) -> dict:
    '''
    Extract fields from reddit submission into dictionary.
    '''
    return {
        "reddit_id": post.id,
        "author": post.__dict__.get("author_fullname"),  # may be undefined
        "title": post.title,
        "body": post.selftext,
        "score": post.score,
        "num_comments": post.num_comments,
        "created_at": datetime.utcfromtimestamp(int(post.created)),
        "url": post.url,
        "permalink": post.permalink,
    }

def clean_tweet(tweet: str) -> str:
    words = set(nltk.corpus.words.words())
    tweet = re.sub("@[A-Za-z0-9]+","",tweet) #Remove @ sign
    tweet = re.sub(r"(?:\@|http?\://|https?\://|www)\S+", "", tweet) #Remove http links
    tweet = " ".join(tweet.split())
    tweet = emoji.replace_emoji(tweet, replace='')
    tweet = tweet.replace("#", "").replace("_", " ") #Remove hashtag sign but keep the text
    tweet = " ".join(w for w in nltk.wordpunct_tokenize(tweet) \
         if w.lower() in words or not w.isalpha())
    return tweet


def get_posts_from_term(search_term: str, num_posts) -> List[dict]:
    x_caller = X_Caller()
    tweet_dicts = x_caller.search_tweets(search_term, max_results=num_posts)
    return tweet_dicts

def update_x_posts(posts: List[Tweet]):
    for p in posts:
        db.session.merge(p)
    db.session.commit()

def write_twitter_posts(posts: List[dict]) -> int:
    num_written = 0
    for post in posts:
        record = (
            db.session.query(Tweet)
            .filter(Tweet.id == post["id"])
            .first()
        )
        if record is None:
            record = Tweet(**post)
            try:
                db.session.add(record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Error writing twitter post: {e}")
            else:
                db.session.commit()
                num_written += 1
    return num_written


def write_generated_posts(generated_posts: List[dict]) -> None:
    """
    """
    for post in generated_posts:
        record = GeneratedPost(**post)
        try:
            db.session.add(record)
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error occurred: {e}")
        else:
            db.session.commit()


def write_modeled_topic_with_twitter_posts(
        topic: dict,
        post_ids: List[int]
) -> None:
    '''
    Save a modeled topic to the database and associate twitter IDs
    with the topic.
    '''
    modeled_topic = ModeledTopic(**topic)
    try:
        db.session.add(modeled_topic)
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error occured: {e}")
    else:
        db.session.commit()

    try:
        db.session.execute(
            insert(reddit_modeled_topic_assoc),
            [
                {"twitter_id": pid, "modeled_topic_id": modeled_topic.id}
                for pid in post_ids
            ],
        )
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error occured: {e}")
    else:
        db.session.commit()


def write_twitter_modeled_overview(topic_overviews: List[dict]) -> None:
    """
    """
    for topic in topic_overviews:
        try:
            db.session.add(ModeledTopic(**topic))
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error occurred: {e}")
        else:
            db.session.commit()
    logging.info(f"wrote overview for {len(topic_overviews)} modeled topics.")


def retrieve_reddit_niche() -> Union[pd.DataFrame, str]:
    """
    Get the ids for the niche title from the niche table, then join with the
    rsubreddit names and make a new table
    """
    # first of all, get the Niche data, ensure we have an entry
    query = db.session.query(Niche)
    df = query.all()
    df = pd.DataFrame(
        [row.__dict__ for row in df]
    )
    # return just the niche id and its associated title
    return df[["id", "title"]]


def retrieve_model_id() -> Union[pd.DataFrame, str]:
    """ """
    # first of all, get the Niche data, ensure we have an entry
    query = db.session.query(ModeledTopic)
    df = query.all()
    df = pd.DataFrame(
        [row.__dict__ for row in df]
    )  # get the pandas table for the Niche
    # return just the niche id and its associated title
    return df[["id", "niche_id"]]


def retrieve_niche_subreddit() -> Union[pd.DataFrame, str]:
    """
    Database call for the niche and linked subreddit to a
    pandas table
    """
    niche_df = retrieve_reddit_niche()  # id, niche
    niche_df = niche_df.rename(columns={"id": "niche_id"})
    subreddit_df = retrieve_subreddit()  # id, niche_id, title
    subreddit_df = subreddit_df.rename(columns={"title": "subreddit_title"})
    niche_subreddit = niche_df.merge(subreddit_df, how="outer").rename(
        columns={"title": "niche", "subreddit_title": "subreddit"}
    )
    niche_subreddit = niche_subreddit[["niche", "subreddit", "id", "niche_id"]]
    return niche_subreddit


def retrieve_subreddit() -> Union[pd.DataFrame, str]:
    """
    Get the ids for the niche title from the niche table, then join with the
    rsubreddit names and make a new table
    """
    query = db.session.query(Subreddit)
    df = query.all()
    df = pd.DataFrame(
        [row.__dict__ for row in df]
    )  # get the pandas table for the Niche
    # return just the niche id and its associated title
    return df[["id", "niche_id", "title"]]
