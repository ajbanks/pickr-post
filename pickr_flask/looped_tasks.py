import logging
import random
from datetime import datetime, timedelta, time
from typing import List
import itertools
import time as time_m

import tweepy
import math
from tqdm import tqdm
from flask import current_app as app
from sqlalchemy import and_
from topic_model import topic
from .models import (GeneratedPost, ModeledTopic, Niche, PickrUser, PostEdit, RedditPost,
                     ScheduledPost, _to_dict, db, user_niche_assoc)
from .post_schedule import (write_schedule, write_schedule_posts,
                            get_simple_schedule_text)
from .queries import latest_post_edit, oauth_session_by_user
from .tasks import (create_schedule, update_niche_twitter, update_niche_subreddits, run_niche_trends, build_topic_dicts, 
                    run_niche_topic_model, generate_niche_topic_overviews, generate_modeled_topic_tweets,
                    MAX_DAILY_TWITTER_POSTS, TWITTER_NICHES
)
from .reddit import (fetch_subreddit_posts, process_post,
                     write_generated_posts,
                     write_modeled_topic_with_reddit_posts,write_reddit_posts)
from .twitter import (get_twitter_posts_from_term, clean_tweet,
                      write_modeled_topic_with_twitter_posts,
                      write_twitter_modeled_overview, write_twitter_posts)
TOPIC_MODEL_MIN_DOCS = 20

log = logging.getLogger(__name__)


def is_time_between(begin_time, end_time, check_time=None):
    # If check time is not given, default to current UTC time
    check_time = check_time or datetime.utcnow().time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else: # crosses midnight
        return check_time >= begin_time or check_time <= end_time


def all_niches_update_schedule():
    """
    Scheduled daily task to fetch recent posts for all niches
    with subreddits or twitter terms and save to database.
    """
    while True:
        # datetime object containing current date and time
        now = datetime.now()
        if is_time_between(time(0, 59), time(1, 00), check_time=now.time()):
            all_niches_update()
            
            
def all_niches_update():
    """
    Scheduled daily task to fetch recent posts for all niches
    with subreddits or twitter terms and save to database.
    """
    niches = (
        Niche.query.filter(and_(Niche.is_active, Niche.subreddits.any()))
            .order_by(Niche.title)
            .all()
    )

    num_twitter_posts_per_niche = MAX_DAILY_TWITTER_POSTS / len(TWITTER_NICHES)

    for niche in tqdm(niches):

        if niche.title in ["Entrepreneurship", "Marketing", "Personal Development"]:
            log.info(f"Updating twitter posts for niche: {niche.title}")
            update_niche_twitter(niche.id, num_twitter_posts_per_niche)

        log.info(f"Updating subreddits for niche: {niche.title}")
        update_niche_subreddits(niche.id)


def all_niches_run_pipeline_schedule():
    """
    Scheduled daily task to run topic pipeline for each niche
    """
    now = datetime.now()
    if is_time_between(time(1,59), time(2, 00), check_time=now.time()):
        all_niches_run_pipeline()        


def all_niches_run_pipeline():
    """
    Scheduled daily task to run topic pipeline for each niche
    """
    niches = (
        Niche.query.filter(and_(Niche.is_active, Niche.subreddits.any()))
            .order_by(Niche.title)
            .all()
    )

    for niche in tqdm(niches):
        log.info(f"Running topic model for niche: {niche.title}")
        run_topic_pipeline(niche.id)


def run_topic_pipeline(niche_id):
    """
    Topic pipeline is done by chaining celery tasks, so different workers
    can process different steps of the pipeline.
    """

    # get trending topics from news api
    modeled_topic_ids = run_niche_trends(niche_id)
    generate_modeled_topic_tweets(modeled_topic_ids)

    # get evergreen topics from reddit
    topic_dicts = run_niche_topic_model(niche_id)
    modeled_topic_ids = generate_niche_topic_overviews(topic_dicts, niche_id)
    generate_modeled_topic_tweets(modeled_topic_ids)


def all_users_run_schedule_schdule():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    while True:
        # datetime object containing current date and time
        now = datetime.now()
        if now.isoweekday() == 1 and is_time_between(time(4, 59), time(5, 00), check_time=now.time()):
            all_users_run_schedule()


def all_users_run_schedule():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    users = PickrUser.query.all()
    for user in tqdm(users):
        logging.info(
            f"Creating schedule for user: {user.username}"
        )
        create_schedule(user.id)


def post_scheduled_tweets():
    '''
    Retrieve any scheduled tweets that need to be posted from the DB
    and post them to twitter.
    '''
    while True:
        time_m.sleep(300)
        scheduled_posts = (
            ScheduledPost.query.filter(
                and_(
                    ScheduledPost.posted_at.is_(None),
                    ScheduledPost.scheduled_for < datetime.now()
                )
            )
            .order_by(
                ScheduledPost.user_id, ScheduledPost.scheduled_for
            )
            .all()
        )
        if not scheduled_posts:
            log.info("no tweets to schedule")
            continue

        log.info(f"found {len(scheduled_posts)} tweets to schedule")
        # post the tweets grouped by user
        uid_to_posts = {}
        for p in scheduled_posts:
            uid = p.user_id
            if uid not in uid_to_posts.keys():
                uid_to_posts[uid] = []
            uid_to_posts[uid].append(p)

        for user_id, posts in uid_to_posts.items():
            oauth_sess = oauth_session_by_user(user_id)
            if oauth_sess is None or oauth_sess.access_token is None \
            or oauth_sess.access_token_secret is None:
                log.error(
                    f"no twitter credentials found for user: user_id={user_id}"
                )
                continue

            client = tweepy.Client(
                consumer_key=app.config["TWITTER_API_KEY"],
                consumer_secret=app.config["TWITTER_API_KEY_SECRET"],
                access_token=oauth_sess.access_token,
                access_token_secret=oauth_sess.access_token_secret,
                wait_on_rate_limit=True,
            )

            num_posted = 0
            for p in posts:
                post_edit = latest_post_edit(p.generated_post_id, user_id)
                if post_edit is None:
                    gp = GeneratedPost.query.get(p.generated_post_id)
                    post_text = gp.text
                else:
                    post_text = post_edit.text

                try:
                    resp = client.create_tweet(text=post_text)
                except (tweepy.errors.BadRequest, tweepy.errors.Unauthorized) as e:
                    logging.error(
                        f"error posting tweet for user_id={user_id}: {e}"
                    )
                    break

                p.tweet_id = resp.data["id"]
                p.posted_at = datetime.now()
                db.session.add(p)
                db.session.commit()
                num_posted += 1
            # endfor

            log.info(
                f"posted {num_posted} tweets for user_id={user_id}"
            )
        
        # endfor
