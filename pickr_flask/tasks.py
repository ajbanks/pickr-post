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
    update_reddit_posts,
    write_reddit_modeled_overview,
    write_reddit_posts,
    write_generated_posts,
)


@shared_task
def all_niches_reddit_update():
    '''
    For each active niche, fetch recent posts.
    '''
    niches = Niche.query.filter(
        and_(Niche.is_active, Niche.subreddits.any())
    ).order_by(
        Niche.title
    ).all()

    for niche in niches:
        logging.info(
            f"Updating subreddits for niche: {niche.title}"
        )
        update_niche_subreddits.apply_async(
            args=(niche.id,)
        )


@shared_task
def all_niches_run_model():
    niches = Niche.query.filter(
        and_(Niche.is_active, Niche.subreddits.any())
    ).order_by(
        Niche.title
    ).all()

    # model runs are serial for now since we only have
    # one worker machine
    for niche in niches:
        logging.info(
            f"Running topic model for niche: {niche.title}"
        )
        run_niche_topic_model(niche.id)


@shared_task
def update_niche_subreddits(niche_id, posts_per_subreddit=200):
    '''
    Fetch new posts for each subreddit related to this niche.
    Save the results to DB.
    '''
    niche = Niche.query.filter(Niche.id == niche_id).one()
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
            f"Fetched {len(posts)} posts: subredddit={subreddit.title}"
        )

        n_written = write_reddit_posts(posts)
        logging.info(
            f"Wrote {n_written} reddit posts: subreddit={subreddit.title}"
        )

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

    if len(posts) < 2:
        logging.error(
            f"Not enough posts for topic model: niche={niche.title}")
        return

    posts_df = pd.DataFrame([_to_dict(p) for p in posts])
    posts_df["text"] = posts_df["title"] + posts_df["body"]

    logging.info(f"Building topic model: niche={niche.title}")
    (
        topic_overviews,
        generated_tweets,
        reddit_post_modeled_topic_ids
    ) = topic.build_subtopic_model(
        posts_df,
        "reddit",
        niche.title,
        trend_prev_days=14,
        max_relevant_topics=20,
        num_gen_tweets=2,
        num_topics_from_topic_label=5,
    )
    if len(topic_overviews) == 0:
        logging.info(f"No topics generated: niche={niche.title}")
        return
    
    # update ids in both topic overviews and reddit posts
    for t in topic_overviews:
        t["niche_id"] = niche_id
    for p, mt_id in zip(posts, reddit_post_modeled_topic_ids):
        if isinstance(mt_id, uuid.UUID):
            p.modeled_topic_id = mt_id
    
    write_reddit_modeled_overview(topic_overviews)
    write_generated_posts(generated_tweets)
    #update_reddit_posts(posts)


@shared_task
def generate_niche_topics(niche_id):
    '''
    Generate modeled topics and posts for a niche.
    '''
    niche = Niche.query.get(niche_id)

    logging.info(
        f"Generating GPT topics and posts: niche={niche.title}"
    )
    related_topics, generated_tweets = topic.generate_tweets_for_topic(
        num_tweets=2, topic_label=niche.title, num_topics_from_topic_label=5
    )
    modeled_topics = []
    for related_topic in related_topics:
        # these are "psuedo" modeled topics since they
        # aren't derived from BERTopic
        modeled_topic = {
            "id": uuid.uuid4(),
            "name": related_topic,
            "niche_id": niche_id,
            "date": datetime.now(),
        }
        for post in generated_tweets:
            if post["topic_label"] == related_topic:
                post["modeled_topic_id"] = modeled_topic["id"]
        modeled_topics.append(modeled_topic)

    write_reddit_modeled_overview(modeled_topics)
    write_generated_posts(generated_tweets)
