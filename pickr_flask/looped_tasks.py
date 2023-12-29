import logging
import random
from datetime import datetime, timedelta, time
from typing import List
from itertools import chain

import tweepy
import math
from flask import current_app as app
from sqlalchemy import and_
from topic_model import topic
from .models import (GeneratedPost, ModeledTopic, Niche, PickrUser, PostEdit, RedditPost,
                     ScheduledPost, _to_dict, db, user_niche_assoc)
from .post_schedule import (write_schedule, write_schedule_posts,
                            get_simple_schedule_text)
from .queries import latest_post_edit, oauth_session_by_user
TOPIC_MODEL_MIN_DOCS = 20

log = logging.getLogger(__name__)


def is_time_between(begin_time, end_time, check_time=None):
    # If check time is not given, default to current UTC time
    check_time = check_time or datetime.utcnow().time()
    if begin_time < end_time:
        return check_time >= begin_time and check_time <= end_time
    else: # crosses midnight
        return check_time >= begin_time or check_time <= end_time


def all_users_run_schedule_debug():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    # datetime object containing current date and time
    now = datetime.now()
    users = PickrUser.query.all()
    for user in users:
        logging.info(
            f"Creating schedule for user: {user.username}"
        )
        create_schedule(user.id)

def all_users_run_schedule():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    while True:
        # datetime object containing current date and time
        now = datetime.now()
        if now.isoweekday() == 1 and is_time_between(time(4, 59), time(5, 00), check_time=now.time()):
            users = PickrUser.query.all()
            for user in users:
                logging.info(
                    f"Creating schedule for user: {user.username}"
                )
                create_schedule(user.id)


def create_schedule(user_id):
    '''
    Generate weekly schedule of 3 posts per day.
    '''
    f"Creating schedule for user: {user_id}"
    user = PickrUser.query.get(user_id)
    niches = user.niches

    
    total_num_posts = 7 * 3  # 3 posts for each day of the week
    log.info(f"User {user.id} has {len(niches)} niches.")
    topic_dict = {}
    all_topics = []
    for niche in niches:
        #log.info(
        #    f"Getting posts in schedule in niche {niche.title} schedule with niche id {niche.id}"
        #)
        # get both top trending and evergreen topics and choose a random selection of them

        news_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                ModeledTopic.trend_class == 'trending'
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).all()

        evergreen_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                ModeledTopic.trend_class == None
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).all()
        topics = list(chain.from_iterable(zip(news_topics, evergreen_topics)))
        
        topic_dict[niche] = topics
        all_topics += topics

    log.info(f"Got {len(all_topics)} topics")
    generated_posts = []
    num_posts_per_topic = 3
    if len(all_topics) == 0:
        log.info("User has no topics")
        return
    
    if len(all_topics) * num_posts_per_topic < total_num_posts:
        # if there arent enough topics to get 3 generated posts from each topic then
        # get more geenrated posts from each topic
        num_posts_per_topic = total_num_posts / len(all_topics)
        for t in all_topics:
            random.shuffle(t.generated_posts)
            posts = t.generated_posts[:num_posts_per_topic]
            generated_posts += posts

    else:
        got_all_posts = False
        
        while got_all_posts is False:
            for n, t in topic_dict.items():
                if len(t) == 0:
                    continue
                t_ = t.pop()
                random.shuffle(t_.generated_posts)
                posts = t_.generated_posts[:num_posts_per_topic]
                
                generated_posts += posts
                if len(generated_posts) >= total_num_posts:
                    got_all_posts = True
                    break

    # do tone matching for generated posts. sonly make a post edit if the user has tweet examples
    user_tweet_examples = user.tweet_examples
    if user_tweet_examples is not None and len(user_tweet_examples) >= 200:
        # convert posts into a users tone if this hasn't already been done
        for gp in generated_posts:
            post_edit = latest_post_edit(gp.generated_post_id, user_id)
            if post_edit is None:
                # a post edit hasn't been made. Which means this post needs to be tone matched
                tone_matched_tweet = topic.rewrite_tweet_in_users_tone(gp.text, user_tweet_examples)

                new_edit = PostEdit(
                    text=tone_matched_tweet,
                    created_at=datetime.now(),
                    user_id=user_id,
                    generated_post_id=gp.id
                )
                db.session.add(new_edit)
                db.session.commit()

    # endfor
    
    schedule = write_schedule({
        "user_id": user_id,
        "week_number": datetime.now().isocalendar().week,
        "schedule_text": get_simple_schedule_text()
    })

    #  pick 3 random posts for each day
    scheduled_posts = []
    schedule_hours = [9, 12, 17]
    for day in range(7):
        for hour in schedule_hours:
            if len(generated_posts) == 0:
                break
            gp = generated_posts.pop()
            scheduled_posts.append({
                "schedule_id": schedule.id,
                "scheduled_day": day,
                "scheduled_hour": hour,
                "user_id": user.id,
                "generated_post_id": gp.id,
            })
    log.info(f"Writing {len(scheduled_posts)} posts")
    write_schedule_posts(scheduled_posts)
    return schedule.id


def post_scheduled_tweets():
    '''
    Retrieve any scheduled tweets that need to be posted from the DB
    and post them to twitter.
    '''
    while True:
        time.sleep(300)
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
