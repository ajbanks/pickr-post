from datetime import datetime, timedelta
from os import environ
from typing import Union, List
import logging

import pandas as pd
import praw
import uuid
from sqlalchemy import exc

from topic_model.util import normalise_tweet, parse_html

from .models import (
    db,
    Niche, ModeledTopic, GeneratedPost,
    Subreddit, RedditPost
)


reddit = praw.Reddit(
    client_id=environ["REDDIT_CLIENT_ID"],
    client_secret=environ["REDDIT_CLIENT_SECRET"],
    user_agent=environ["REDDIT_USER_AGENT"]
)


def _to_dict(post):
    return {
        "reddit_id": post.id,
        "author": post.__dict__.get("author_fullname"),  # may be undefined
        "title": post.title,
        "body": post.selftext,
        "score": post.score,
        "created_at": datetime.utcfromtimestamp(int(post.created)),
        "url": post.url,
    }


def process_post(p) -> str:
    return normalise_tweet(
        parse_html(p["title"] + "\n" + p["body"])
    )


def search_subreddit_for_term(
        subreddit_string,
        search_term,
        time_filter="week"
):
    output_rows = []
    sub_generator = reddit.subreddit(subreddit_string).search(
        search_term, time_filter=time_filter
    )
    for submission in sub_generator:
        output_rows.append(_to_dict(submission))

    reddit_df = pd.DataFrame(output_rows)
    reddit_df["title"] = reddit_df["title"].apply(parse_html)
    reddit_df["body"] = reddit_df["body"].apply(parse_html)
    reddit_df["text"] = reddit_df["title"] + reddit_df["body"]
    reddit_df["clean_text"] = reddit_df["text"].apply(normalise_tweet)

    return reddit_df


def get_hot_submissions_from_subreddit_list(subreddit_list):
    post_rows = []
    for subreddit_string in subreddit_list:
        post_rows += get_hot_submissions(reddit.subreddit(subreddit_string))

    reddit_df = pd.DataFrame(post_rows)
    reddit_df["title"] = reddit_df["title"].apply(parse_html)
    reddit_df["body"] = reddit_df["body"].apply(parse_html)
    reddit_df["text"] = reddit_df["title"] + reddit_df["body"]
    reddit_df["clean_text"] = reddit_df["text"].apply(normalise_tweet)
    # reddit_df["lang"] = reddit_df["clean_text"].apply(lang)
    # reddit_df = reddit_df[reddit_df["lang"] == "en"]
    return reddit_df


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


def fetch_niche_subreddit_posts(
        subreddits,
        num_posts_per_subreddit=100,
        time_filter="all",
):
    """"""
    output_rows = []
    try:
        for subred in subreddits:
            sub_generator = reddit.subreddit(subred.title).new(
                limit=num_posts_per_subreddit,
                time_filter=time_filter
            )
            for submission in sub_generator:
                output_rows.append(_to_dict(submission))

    except Exception as e:
        raise Exception(f"Failed to get any posts: {e}")

    df = pd.DataFrame(output_rows)
    df["title"] = df["title"].astype(str)
    df["body"] = df["body"].astype(str)
    df["text"] = df["title"] + " " + df["body"]
    df["clean_text"] = df["text"].apply(normalise_tweet)
    return df


#############################################################################
#


def write_generated_posts(generated_posts) -> None:
    """ """
    for post in generated_posts:
        record = GeneratedPost(**post)
        try:
            db.session.add(record)
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error(f"Database error occurred: {e}")
        else:
            db.session.commit()


def write_reddit_modeled_overview(topic_overviews) -> None:
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


def write_reddit_niche(niche_list: List[str]):
    """
    Adding reddit posts
    """
    topic_id_dict = {}

    for topic in niche_list:
        # store the niche uuids
        niche_id_uuid = uuid.uuid4()
        topic_id_dict[topic] = niche_id_uuid
        # store subreddit ids with the niche ids
        # update Niche input - if we have a duplicated niche
        topic_dict = {}
        topic_dict[
            "id"
        ] = niche_id_uuid  # topic_id_dict[row["topic"]]  # we have a unique id for each niche
        topic_dict["title"] = topic
        topic_dict["category"] = None
        topic_dict["is_active"] = True
        topic_dict["is_custom"] = False
        # find whether we have an entry for the record
        record = (
            db.session.query(Niche)
            .filter(Niche.title == topic)
            .first()
        )

        if record is None:  # if we cannot detect a record, we update
            niche_record = Niche(**topic_dict)
            try:
                db.session.add(niche_record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Database error occurred: {e}")
            else:
                db.session.commit()

    logging.info(f"wrote {len(niche_list)} niches")


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


def write_subreddit(
    file_path: str,
) -> None:
    """
    Reshape the subreddit data and store the subreddit
    in relational database with the niche id
    """
    # empty entries in subreddit
    # try:
    #    db.session.query(Subreddit).delete()
    #    db.session.commit()
    #    logging.info(f"Resetting the subreddit table")
    # except Exception as e:
    #    logging.error(f"error in deleting the subreddit table")
    #    db.session.rollback()
    # finally:
    #    db.session.close()
    niches = retrieve_reddit_niche()
    niches = niches.rename(columns={"title": "niche"})
    # Read subreddit data
    subreddit_data = pd.read_csv(file_path)
    # Remove rows with NaNs
    subreddit_data = subreddit_data.dropna()
    # Ensure that the format of the niche we read with the subreddit file
    # is consistent with the niche identified with the reddits posts niche
    subreddit_data["niche"] = (
        subreddit_data["niche"].str.replace("_", " ").str.lower()
    )
    # isolate only the niche and subreddits associated with that niche
    subreddit_data = subreddit_data.merge(niches, how="outer")
    subreddit_data = subreddit_data.rename(columns={"id": "niche_id"})

    for index, row in subreddit_data.iterrows():
        subreddit_dict = {}
        subreddit_id_uuid = uuid.uuid4()  # generate key uuid for topic
        subreddit_dict["id"] = subreddit_id_uuid
        subreddit_dict["title"] = row["subreddits"]
        subreddit_dict["niche_id"] = row["niche_id"]
        # ensure that we are not adding a repeated topic here
        record = (
            db.session.query(Subreddit)
            .filter(
                Subreddit.title == row["subreddits"],
            )
            .first()
        )
        if record is None:
            record = Subreddit(**subreddit_dict)
            try:
                db.session.add(record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                logging.error(e)
            else:
                db.session.commit()


def write_reddit_posts(posts) -> int:
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
