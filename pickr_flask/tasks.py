from typing import List
import logging
import uuid
from datetime import datetime, timedelta
from celery import shared_task

import pandas as pd

from sqlalchemy import and_
from topic_model import topic
from .models import (
    RedditPost, Niche,
    _to_dict,
)

from .reddit import (
    process_post,
    fetch_subreddit_posts,
    write_reddit_niche,
    write_reddit_modeled_overview,
    write_reddit_posts,
    retrieve_niche_subreddit,
    write_generated_posts,
)


@shared_task
def daily_update():
    '''
    This is the main daily scheduled task. For each active niche,
    it fetches recent posts then builds a topic model.
    '''
    niches = Niche.query.filter(
        and_(
            Niche.is_active,
            Niche.subreddits.any()
        )
    ).all()

    # TODO: this can be parallel with celery "group"
    for niche in niches:
        update_niche_subreddits.apply_async(
            args=(niche.id,),
            link=run_niche_topic_model.s()
        )


@shared_task
def update_niche_subreddits(niche_id, posts_per_subreddit=100):
    '''
    Fetch new posts for each subreddit related to this niche.
    Save the results to DB.
    '''
    niche = Niche.query.filter(Niche.id == niche_id).one()
    all_posts = []
    for subreddit in niche.subreddits:
        # do we want top/hot from previous day here instead?
        posts = fetch_subreddit_posts(
            subreddit.title,
            num_posts=posts_per_subreddit,
        )
        for p in posts:
            p["subreddit_id"] = subreddit.id
            p["clean_text"] = process_post(p)
        logging.info(
            f"Fetched {len(posts)} posts for subredddit {subreddit.title}"
        )
        write_reddit_posts(posts)
        all_posts.extend(posts)

    return niche_id


@shared_task
def run_niche_topic_model(niche_id):
    '''
    Read recent posts for the niche and run the topic model.
    '''
    niche = Niche.query.filter(Niche.id == niche_id).one()
    sub_ids = [sub.id for sub in niche.subreddits]

    # what data do we want to use here?
    posts = RedditPost.query.filter(
        and_(
            RedditPost.created_at > datetime.now() - timedelta(days=21),
            RedditPost.subreddit_id.in_(sub_ids),
        )
    ).all()

    if len(posts) == 0:
        logging.error(f"No posts found for niche: {niche.title}")
        return

    posts_df = pd.DataFrame([_to_dict(p) for p in posts])
    posts_df["text"] = posts_df["title"] + posts_df["body"]

    logging.info(f"Building topic model for niche: {niche.title}")
    (
        topic_overviews,
        generated_tweets
    ) = topic.build_subtopic_model(
        posts_df,
        "reddit",
        trend_prev_days=14,
        max_relevant_topics=20,
        num_gen_tweets=2,
        num_topics_from_topic_label=5,
    )
    if len(topic_overviews) == 0:
        logging.info(f"No topics generated for niche: {niche.title}")
        return

    write_reddit_modeled_overview(topic_overviews)
    write_generated_posts(generated_tweets)


@shared_task
def update_niches_generate_posts():
    '''
    For each niche that doesn't have subreddits yet,
    generate generic posts with GPT and save to database.
    '''
    niches = Niche.query.filter(~Niche.subreddits.any()).all()

    for niche in niches:
        logging.info(f"niches without subreddits: {niche}")
        gpt_generated_tweets_df = topic.generate_tweets_for_topic(
            num_tweets=2, topic_label=niche, num_topics_from_topic_label=5
        )
        gpt_gen_topic_uuid_lookup = {
            k: uuid.uuid4() for k in
            gpt_generated_tweets_df["gpt_topic_label"].unique()
        }
        gpt_generated_tweets_df["modeled_topic_id"] = gpt_generated_tweets_df[
            "gpt_topic_label"
        ].apply(lambda x: gpt_gen_topic_uuid_lookup[x])
        gpt_topic_labels = gpt_generated_tweets_df["gpt_topic_label"].unique()
        # create topic_overview_df for generated tweets
        # that do not make use of trending topics
        current_date = datetime.today().strftime("%Y-%m-%d")
        n_labels = len(gpt_topic_labels)
        gpt_topic_overview_data = {
            "id": [gpt_gen_topic_uuid_lookup[i] for i in (gpt_topic_labels)],
            "name": gpt_topic_labels,
            "description": ["" for i in range(n_labels)],
            "trend_type": ["" for i in range(n_labels)],
            "niche_id": [niche.id for i in range(n_labels)],
            "date": [current_date for i in range(n_labels)],
            "size": [0 for i in range(n_labels)],
        }
        gpt_topic_overview_df = pd.DataFrame(data=gpt_topic_overview_data)
        write_reddit_modeled_overview(gpt_topic_overview_df)
        write_generated_posts(gpt_generated_tweets_df, "gpt")


@shared_task
def new_user_get_data(niches: List[str]):
    """
    For niches that are not in the database already, generated the
    tweets using chatgpt then store the remaining niches in the database
    """
    niche_df = retrieve_niche_subreddit()

    # split niches into those that are and aren't in the the DB
    remaining_niches = list(set(niches) - set(niche_df["niche"].tolist()))
    if len(remaining_niches) == 0:
        return
    write_reddit_niche(remaining_niches)
    # get generated tweets for those niches that don't have a subreddit
    for niche in remaining_niches:
        gpt_generated_tweets_df = topic.generate_tweets_for_topic(
            num_tweets=2, topic_label=niche, num_topics_from_topic_label=5
        )
        niche_uuid = niche_df.loc[niche_df["niche"] == niche, "niche_id"]
        # create topic_overview_df for generated tweets that do not make use of trending topics
        gpt_gen_topic_uuid_lookup = {
            k: uuid.uuid4() for k in gpt_generated_tweets_df["gpt_topic_label"].unique()
        }
        gpt_generated_tweets_df["modeled_topic_id"] = gpt_generated_tweets_df[
            "gpt_topic_label"
        ].apply(lambda x: gpt_gen_topic_uuid_lookup[x])
        gpt_topic_labels = gpt_generated_tweets_df["gpt_topic_label"].unique()
        # create topic_overview_df for generated tweets that do not make use of trending topics
        current_date = datetime.today().strftime("%Y-%m-%d")
        gpt_topic_overview_data = {
            "id": [gpt_gen_topic_uuid_lookup[i] for i in (gpt_topic_labels)],
            "name": gpt_topic_labels,
            "description": ["" for i in range(len(gpt_topic_labels))],
            "trend_type": ["" for i in range(len(gpt_topic_labels))],
            "niche_id": [niche_uuid for i in range(len(gpt_topic_labels))],
            "date": [current_date for i in range(len(gpt_topic_labels))],
            "size": [0 for i in range(len(gpt_topic_labels))],
        }
        gpt_topic_overview_df = pd.DataFrame(data=gpt_topic_overview_data)
        write_reddit_modeled_overview(gpt_topic_overview_df)
        write_generated_posts(
            gpt_generated_tweets_df, "gpt"
        )  # writing generated tweets here
