import os
import sys
import time
import logging
import uuid

from os import environ, path
from dotenv import load_dotenv
from typing import List
from tqdm import tqdm
from datetime import datetime

sys.path.append("../")

import pandas as pd

from . import task_queue
from pickr.topic import topic
from pickr.twitter import twitter

from pickr.backend.topic_write_flask_reddit import (
    write_subreddit,
    write_reddit_niche,
    write_reddit_modeled_overview,
    write_reddit_posts,
    retrieve_niche_subreddit,
    retrieve_model_id,
    write_generated_posts,
)

logging.basicConfig(level=logging.INFO)


@task_queue.task
def write_niche_subreddit(niche_subreddit_path: str = "static/data/nichesubreddit.csv"):
    """
    This function stores niche, and adds a UUID id to it.

    Follwing this, the subreddits and its titles are also attached a UUID
    as well as the corresponding niche UUID
    """
    write_reddit_niche(file_path=niche_subreddit_path)
    write_subreddit(niche_subreddit_path)


@task_queue.task
def daily_update_reddit(num_posts_per_subreddit: int = 1000, max_tries: int = 10) -> None:
    """
    This retrieves the niches from the database and then
    writes the posts retrieved from the subreddits to the database
    """
    # get unique niches and there related subreddits for each user
    niche_df = retrieve_niche_subreddit()

    # split niches into those with and without a subreddit
    niche_no_subreddit = niche_df[niche_df["subreddit"].isna()]["niche"].unique()
    niche_w_subreddit = list(set(niche_df["niche"].unique()) - set(niche_no_subreddit))
    logging.info("we have loaded the niche with subreddits and ones without")

    # for niches with subreddits get the trending topics and generated tweets
    for i, niche in enumerate(niche_w_subreddit):
        niche_uuid = niche_df.loc[niche_df["niche"] == niche, "niche_id"].iloc[0]

        logging.info(f"niches with subreddits - working with niche - {niche}")
        if i != 0 and i % 2 == 0:
            time.sleep(120)
        subreddits = niche_df[niche_df["niche"]==niche]["subreddits"].unique()
        success = False
        num_posts = num_posts_per_subreddit
        tries = 0
        while success is False and tries < max_tries:
            try:
                subreddits = niche_df[niche_df["niche"] == niche]["subreddit"].tolist()
                posts_df = twitter.fetch_niche_subreddit_posts(subreddits)
            except:
                num_posts = num_posts - num_posts*0.2
                tries += 1
        if success is False:
            logging.error(
                f"Couldn't get posts for niche - {niche}"
            )
            continue
        
        logging.info(
            f"generating overview, posts, and generated posts for niche - {niche}"
        )
        (
            topic_overview_df,
            topic_posts_df,
            generated_tweets_df,
        ) = topic.build_subtopic_model(
            posts_df,
            "reddit",
            trend_prev_days=14,
            max_relevant_topics=20,
            num_gen_tweets=2,
            num_topics_from_topic_label=5,
        )
        topic_overview_df["niche_id"] = niche_uuid
        topic_posts_df["modeled_topic_id"] = topic_posts_df["modeled_topic_id"].fillna('68e45622-0c4c-41b5-ab58-b4390757d32d')
        logging.info(
            f"write to database the overview, posts, and generated posts for niche - {niche}"
        )
        write_reddit_modeled_overview(
            topic_overview_df,
        )  # write overview
        write_reddit_posts(topic_posts_df)  # writing topic posts here
        write_generated_posts(
            generated_tweets_df, "subreddit"
        )  # writing generated tweets here

    # for niches without subreddits get generated tweets
    for niche in tqdm(niche_no_subreddit):
        niche_uuid = niche_df.loc[niche_df["niche"] == niche, "niche_id"].iloc[0]

        logging.info(f"niches without subreddits - working with niche - {niche}")
        gpt_generated_tweets_df = topic.generate_tweets_for_topic(
            num_tweets=2, topic_label=niche, num_topics_from_topic_label=5
        )
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


@task_queue.task
def new_user_get_data(niches: List[str]):
    """
    For niches that are not in the database already, generated the
    tweets using chatgpt then store the remaining niches in the database
    """
    niche_df = retrieve_niche_subreddit()
    modeled_df = retrieve_model_id()

    # split niches into those that are and aren't in the the DB
    remaining_niches = list(set(niches) - set(niche_df["niche"].tolist()))
    if len(remaining_niches) == 0: 
        return
    write_reddit_niche(remaining_niches)
    # get generated tweets for those niches that don't have a subreddit
    for niche in tqdm(remaining_niches):
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


if __name__ == "__name__":
    write_niche_subreddit()
