import logging
import math
import random
import uuid
from datetime import datetime, timedelta
from typing import List

import tweepy
from celery import chain, shared_task
from flask import current_app as app
from sqlalchemy import and_
from topic_model import topic

from .newsapi import (
    get_trends,
    write_news_articles,
    write_modeled_topic_with_news_article,
)
from .models import (GeneratedPost, ModeledTopic, Niche, PickrUser, RedditPost,
                     ScheduledPost, _to_dict, db, user_niche_assoc)
from .newsapi import (get_trends, write_modeled_topic_with_news_article,
                      write_news_articles)
from .post_schedule import write_schedule, write_schedule_posts
from .queries import latest_post_edit, oauth_session_by_user
from .reddit import (fetch_subreddit_posts, process_post,
                     write_generated_posts,
                     write_modeled_topic_with_reddit_posts,
                     write_reddit_modeled_overview, write_reddit_posts)

TOPIC_MODEL_MIN_DOCS = 20


@shared_task
def run_schedule():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    users = PickrUser.query.all()

    for user in users:
        logging.info(
            f"Creating schedule for user: {user.username}"
        )
        create_schedule(user.id).apply_async(
            args=(user.id,)
        )

@shared_task
def create_schedule(user_id):
    '''
    Generate weekly schedule of 3 posts per day.
    '''
    user = PickrUser.query.get(user_id)
    niches = user.niches

    num_posts_per_topic = 3

    generated_posts = []
    for niche in niches:
        logging.info(
            f"Creating niche {niche.title} schedule for user: {user_id}"
        )
        topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).limit(3).all()

        for t in topics:
            random.shuffle(t.generated_posts)
            generated_posts += t.generated_posts[:num_posts_per_topic]
    # endfor

    schedule = write_schedule({
        "user_id": user_id,
        "week_number": datetime.now().isocalendar().week
    })

    #  pick 3 random posts for each day
    random.shuffle(generated_posts)
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


@shared_task
def all_niches_reddit_update():
    """
    Scheduled daily task to fetch recent posts for all niches
    with subreddits and save to database.
    """
    niches = (
        Niche.query.filter(and_(Niche.is_active, Niche.subreddits.any()))
        .order_by(Niche.title)
        .all()
    )

    for niche in niches:
        logging.info(f"Updating subreddits for niche: {niche.title}")
        update_niche_subreddits.apply_async(args=(niche.id,))


@shared_task
def update_niche_subreddits(niche_id, posts_per_subreddit=200):
    """
    Fetch new posts for each subreddit related to this niche.
    Save the results to DB.
    """
    niche = Niche.query.get(niche_id)
    for subreddit in niche.subreddits:
        # TODO: do we want top/hot from previous day here instead?
        posts = fetch_subreddit_posts(
            subreddit.title,
            num_posts=posts_per_subreddit,
        )
        for p in posts:
            p["subreddit_id"] = subreddit.id
            p["clean_text"] = process_post(p)
        logging.info(f"Fetched {len(posts)} posts: subredddit={subreddit.title}")

        n_written = write_reddit_posts(posts)
        logging.info(f"Wrote {n_written} reddit posts: subreddit={subreddit.title}")

    return niche_id


@shared_task
def all_niches_run_pipeline():
    """
    Scheduled daily task to run topic pipeline for each niche
    """
    niches = (
        Niche.query.filter(and_(Niche.is_active, Niche.subreddits.any()))
        .order_by(Niche.title)
        .all()
    )

    for niche in niches:
        logging.info(f"Running topic model for niche: {niche.title}")
        run_topic_pipeline(niche.id)


def run_topic_pipeline(niche_id):
    """
    Topic pipeline is done by chaining celery tasks, so different workers
    can process different steps of the pipeline.
    """

    # get trending topics from news api
    pipeline_news = chain(
        run_niche_trends.s(),
        generate_modeled_topic_tweets.s()
    )
    pipeline_news.apply_async(args=(niche_id,))
    
    # get evergreen topics from reddit
    pipeline = chain(
        run_niche_topic_model.s(),
        generate_niche_topic_overviews.s(niche_id),
        generate_modeled_topic_tweets.s(),
    )
    pipeline.apply_async(args=(niche_id,))


@shared_task
def run_niche_trends(niche_id) -> List[dict]:
    """
    First step of topic pipeline:
    read recent posts for the niche and run the BERTopic model.
    """
    niche = Niche.query.get(niche_id)
    terms = [t.term for t in niche.news_terms]

    # get trends
    all_topics = []
    for term in terms:
        topic_labels, topic_articles = get_trends(term, niche.title)

        for i, title_desc in enumerate(topic_labels):
            # create modeled topic
            modeled_topic = {
                "id": uuid.uuid4(),
                "niche_id": niche_id,
                "name": title_desc[0],
                "description": title_desc[1],
                "date": datetime.now(),
                "size": 0,
                "trend_type": "news",
            }

            # create news articles
            news_articles = []
            for n in topic_articles[i]:
                news_article = {"id": uuid.uuid4(), "title": n["title"], "url": n["url"], "published_date": n["published_date"]}
                news_articles.append(news_article)
            
            # write to db
            write_news_articles(news_articles)
            write_modeled_topic_with_news_article(
                modeled_topic, [n["id"] for n in news_articles]
            )
            all_topics.append(modeled_topic)

    return [t["id"] for t in all_topics]


@shared_task
def run_niche_topic_model(niche_id) -> List[dict]:
    """
    First step of topic pipeline:
    read recent posts for the niche and run the BERTopic model.
    """
    niche = Niche.query.get(niche_id)
    sub_ids = [sub.id for sub in niche.subreddits]

    # what data do we want to use here?
    posts = RedditPost.query.filter(
        and_(
            RedditPost.created_at > datetime.now() - timedelta(days=18),
            RedditPost.subreddit_id.in_(sub_ids),
        )
    ).all()

    if len(posts) < TOPIC_MODEL_MIN_DOCS:
        logging.error(f"Not enough posts for topic model: niche={niche.title}")
        raise ValueError("Not enough posts to run topic model", niche.title)

    post_dicts = [_to_dict(p) for p in posts]
    texts = [p["clean_text"] for p in post_dicts]

    logging.info(f"Building topic model: niche={niche.title}")
    topic_model = topic.build_subtopic_model(texts)
    topics, probs = topic_model.topics_, topic_model.probabilities_
    topic_keywords = topic_model.get_topic_info()["Representation"].tolist()

    # TODO topic_rep_docs shouldn't be sent to the celery broker,
    # it makes payload too large
    topic_rep_docs = topic_model.get_topic_info()["Representative_Docs"].tolist()
    topic_dicts = topic.analyze_topics(
        topics,
        probs,
        topic_keywords,
        topic_rep_docs,
        post_dicts,
        "reddit",
        trend_prev_days=14,
    )
    return topic_dicts


@shared_task
def generate_niche_topic_overviews(
    topic_dicts: List[dict],
    niche_id: uuid.UUID,
    max_modeled_topics=5,
) -> List[uuid.UUID]:
    """
    Second step of topic pipeline:
    given the output of run_niche_topic_model, generate modeled topics
    and store them to the database.

    Returns list of modeled topic IDs that were created.
    """
    niche = Niche.query.get(niche_id)
    modeled_topic_ids = []
    count = 0
    for topic_dict in topic_dicts:
        if count >= max_modeled_topics:
            break
        # query the text of the representative posts for this topic
        post_ids = topic_dict["post_ids"]
        posts_query = db.session.query(RedditPost.clean_text).filter(
            RedditPost.id.in_(post_ids[:4])
        )
        texts = [t for (t,) in posts_query.all()]

        topic_label, topic_desc = topic.generate_topic_overview(
            texts,
            topic_dict["topic_keywords"],
            topic_dict["topic_rep_docs"],
            niche.title,
        )
        if topic_label == "" or topic_desc == "":
            continue  # discard this topic

        modeled_topic = {
            "id": uuid.uuid4(),
            "niche_id": niche_id,
            "name": topic_label,
            "description": topic_desc,
            "date": datetime.now(),
            "size": topic_dict["rank"],
        }
        write_modeled_topic_with_reddit_posts(modeled_topic, post_ids)
        modeled_topic_ids.append(modeled_topic["id"])
        count += 1

    logging.info(f"{count} modeled topics created: niche={niche_id}")
    return modeled_topic_ids


@shared_task
def generate_modeled_topic_tweets(modeled_topic_ids):
    """
    Third step of topic pipeline:
    generate tweets for each modeled topic
    """
    for mt_id in modeled_topic_ids:
        modeled_topic = ModeledTopic.query.get(mt_id)
        _, generated_tweets = topic.generate_tweets_for_topic(
            5, modeled_topic.name, modeled_topic.description, 3
        )

        for tweet in generated_tweets:
            tweet["modeled_topic_id"] = mt_id

        num_tweets = len(generated_tweets)
        logging.info(
            f"generated {num_tweets} tweets for modeled topic: {modeled_topic.name}"
        )
        write_generated_posts(generated_tweets)


@shared_task
def generate_niche_gpt_topics(niche_id):
    """
    Generate modeled topics and posts for a niche with GPT.
    This does not use BERTopic or reddit/twitter data.
    """
    niche = Niche.query.get(niche_id)

    logging.info(f"Generating GPT topics and posts: niche={niche.title}")
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
            "date": datetime.now().date(),
        }
        for post in generated_tweets:
            if post["topic_label"] == related_topic:
                post["modeled_topic_id"] = modeled_topic["id"]
        modeled_topics.append(modeled_topic)

    write_reddit_modeled_overview(modeled_topics)
    write_generated_posts(generated_tweets)


@shared_task
def post_scheduled_tweets():
    '''
    Retrieve any scheduled tweets that need to be posted from the DB
    and post them to twitter.
    '''
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
        logging.info("no tweets to schedule")
        return

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
            logging.error(
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

        logging.info(
            f"posted {num_posted} tweets for user_id={user_id}"
        )
    # endfor
