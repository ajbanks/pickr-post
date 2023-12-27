import logging
import random
import time
from datetime import datetime, timedelta
from typing import List
import tweepy
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

def create_schedule(user_id):
    '''
    Generate weekly schedule of 3 posts per day.
    '''
    user = PickrUser.query.get(user_id)
    niches = user.niches

    num_posts_per_topic = 3
    total_num_posts = 7 * 3  # 3 posts for each day of the week
    total_topics = total_num_posts / num_posts_per_topic
    num_topics_per_niche = total_topics / len(niches)  # even number of topics for each niche

    generated_posts = []
    for niche in niches:
        log.info(
            f"Creating niche {niche.title} schedule for user: {user_id}"
        )
        # get both top trending and evergreen topics and choose a random selection of them
        news_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                ModeledTopic.trend_type == 'trend'
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).limit(num_topics_per_niche).all()

        evergreen_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                ModeledTopic.trend_type != 'trend'
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).limit(num_topics_per_niche).all()
        topics = news_topics + evergreen_topics
        random.shuffle(topics)
        topics = topics[:num_topics_per_niche]
        for t in topics:
            random.shuffle(t.generated_posts)
            generated_posts += t.generated_posts[:num_posts_per_topic]



        # convert posts into a users tone if this hasn't already been done
        for gp in generated_posts:

            user_tweet_examples = user.tweet_examples

            # only make a post edit if the user has tweet examples
            if len(user_tweet_examples) < 200:
                continue


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

    write_schedule_posts(scheduled_posts)
    return schedule.id


def post_scheduled_tweets():
    '''
    Retrieve any scheduled tweets that need to be posted from the DB
    and post them to twitter.
    '''
    while True:
        time.sleep(10)
        print('getting scheduled posts')
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
        print('got scheduled posts')
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
