import logging
from datetime import datetime, timedelta
from os import environ
from typing import Union, List

import pandas as pd
import praw
from sqlalchemy import exc, insert

from topic_model.util import normalise_tweet, parse_html

from .models import (
    db,
    Niche, ModeledTopic, GeneratedPost,
    Subreddit, RedditPost,
    reddit_modeled_topic_assoc
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


def process_post(p: dict) -> str:
    return normalise_tweet(
        parse_html(p["title"] + "\n" + p["body"])
    )


def search_subreddit_for_term(
        subreddit_string,
        search_term,
        time_filter="week"
) -> List[dict]:
    output_rows = []
    sub_generator = reddit.subreddit(subreddit_string).search(
        search_term, time_filter=time_filter
    )
    for submission in sub_generator:
        output_rows.append(_to_dict(submission))
    return output_rows


def get_hot_submissions(subreddit):
    post_rows = []
    month_ago = datetime.utcnow() - timedelta(days=30)

    for submission in subreddit.hot(limit=1000):
        if submission.created >= month_ago:
            post_rows.append(_to_dict(submission))
    return post_rows


def find_subreddits(search_terms):
    found_subreddits = []
    subreddits = reddit.subreddits
    for term in search_terms:
        found_subreddits += subreddits.search_by_name(term, include_nsfw=False)
    return [s.display_name for s in found_subreddits]


def fetch_subreddit_posts(subreddit_name, num_posts=1000):
    '''
    Fetch new posts from a subreddit
    '''
    submissions = []
    submission_generator = reddit.subreddit(subreddit_name).new(
        limit=num_posts
    )
    # TODO: add rate-limit backoff
    try:
        for submission in submission_generator:
            submissions.append(_to_dict(submission))
    except Exception as e:
        logging.error(f"error fetching submissions for {subreddit_name}: {e}")
        return submissions
    return submissions


#############################################################################
#

def update_reddit_posts(posts: List[RedditPost]):
    for p in posts:
        db.session.merge(p)
    db.session.commit()


def write_reddit_posts(posts: List[dict]) -> int:
    num_written = 0
    for post in posts:
        record = (
            db.session.query(RedditPost)
            .filter(RedditPost.reddit_id == post["reddit_id"])
            .first()
        )
        if record is None:
            record = RedditPost(**post)
            try:
                db.session.add(record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Error writing reddit post: {e}")
            else:
                db.session.commit()
                num_written += 1
    return num_written


def write_generated_posts(generated_posts: List[dict]) -> None:
    """
    """
    records = []
    for post in generated_posts:
        record = GeneratedPost(**post)
        records.append(record)
        try:
            db.session.add(record)
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error occurred: {e}")
        else:
            db.session.commit()

    return records


def write_modeled_topic_with_reddit_posts(
        topic: dict,
        post_ids: List[int]
) -> None:
    '''
    Save a modeled topic to the database and associate reddit IDs
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
                {"reddit_id": pid, "modeled_topic_id": modeled_topic.id}
                for pid in post_ids
            ],
        )
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error occured: {e}")
    else:
        db.session.commit()



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
