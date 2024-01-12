import logging
import random
import uuid
import math
import tweepy
import itertools
from datetime import datetime, timedelta
from typing import List

from celery import chain, shared_task
from flask import current_app as app
from sqlalchemy import exc, insert, and_
from topic_model import topic
from .twitter import X_Caller
from .models import (GeneratedPost, ModeledTopic, Niche, PickrUser, PostEdit, Tweet, TwitterTerm, RedditPost,
                     ScheduledPost, _to_dict, db, user_niche_assoc)
from .newsapi import (get_trends, write_modeled_topic_with_news_article,
                      write_news_articles)
from .post_schedule import (write_schedule, write_schedule_posts,
                            get_simple_schedule_text)
from .queries import latest_post_edit, oauth_session_by_user
from .reddit import (fetch_subreddit_posts, process_post,
                     write_generated_posts,
                     write_modeled_topic_with_reddit_posts,write_reddit_posts)
from .twitter import (get_twitter_posts_from_term, clean_tweet,
                      write_modeled_topic_with_twitter_posts,
                      write_twitter_modeled_overview, write_twitter_posts)

TOPIC_MODEL_MIN_DOCS = 20
MAX_MONTHLY_TWITTER_POSTS = 9500
MAX_DAILY_TWITTER_POSTS = MAX_MONTHLY_TWITTER_POSTS / 30
TWITTER_NICHES = ["Entrepreneurship", "Marketing", "Personal Development"]

log = logging.getLogger(__name__)


@shared_task
def run_marketing_functions():
    x_caller = X_Caller()

    # send marketing dms
    x_caller.send_marketing_dms(50)


@shared_task
def all_users_run_schedule():
    '''
    Scheduled weeky task to create post schedule for every user
    '''
    users = PickrUser.query.all()

    for user in users:
        log.info(
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
    log.info(f"Creating schedule for user: {user_id}")
    print(f"Creating schedule for user: {user_id}")
    user = PickrUser.query.get(user_id)
    niches = user.niches
    
    total_num_posts = 7 * 3  # 3 posts for each day of the week
    log.info(f"User {user.id} has {len(niches)} niches.")
    print(f"User {user.id} has {len(niches)} niches.")
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

        twitter_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                ModeledTopic.trend_class == 'twitter'
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).all()

        evergreen_topics = ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id == niche.id,
                ModeledTopic.date >= datetime.now() - timedelta(days=7),
                #ModeledTopic.trend_class == None
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).all()
        topics = list(itertools.chain.from_iterable(zip(news_topics, twitter_topics)))
        topics += evergreen_topics
        
        topic_dict[niche] = topics
        all_topics += topics

    log.info(f"Got {len(all_topics)} topics")
    print(f"Got {len(all_topics)} topics")
    generated_posts = []
    num_posts_per_topic = 3
    if len(all_topics) == 0:
        log.info("User has no topics")
        print("User has no topics")
        return

    if len(all_topics) * num_posts_per_topic < total_num_posts:
        # if there arent enough topics to get 3 generated posts from each topic then
        # get more geenrated posts from each topic
        num_posts_per_topic = math.ceil(total_num_posts / len(all_topics))
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
    if user_tweet_examples is not None and len(user_tweet_examples) >= 1000:
        # convert posts into a users tone if this hasn't already been done
        for gp in generated_posts:
            post_edit = latest_post_edit(gp.id, user_id)
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
    print(f"Writing {len(scheduled_posts)} posts")
    write_schedule_posts(scheduled_posts)
    return schedule.id


@shared_task
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
    
    for niche in niches:

        if niche.title in TWITTER_NICHES:
            log.info(f"Updating twitter posts for niche: {niche.title}")
            update_niche_twitter.apply_async(args=(niche.id, num_twitter_posts_per_niche,))
        
        log.info(f"Updating subreddits for niche: {niche.title}")
        update_niche_subreddits.apply_async(args=(niche.id,))


@shared_task
def update_niche_twitter(niche_id, total_posts):
    """
    Fetch new posts for each twitter term related to this niche.
    Save the results to DB.
    """

    twitter_terms = db.session.query(TwitterTerm).filter(TwitterTerm.niche_id == niche_id).all()
    print('retrieved twitter terms', len(twitter_terms))
    posts_per_term = int(total_posts / len(twitter_terms))
    for twitter_term in twitter_terms:
        print('term', twitter_term)
        posts = get_twitter_posts_from_term(
            twitter_term.term,
            num_posts=posts_per_term,
        )

        for p in posts:
            p["clean_text"] = clean_tweet(p['text'])
            p["niche_id"] = niche_id

        log.info(f"Fetched {len(posts)} posts: term={twitter_term}")
        n_written = write_twitter_posts(posts)
        log.info(f"Wrote {n_written} twitter posts: term={twitter_term}")

    return niche_id


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
        log.info(f"Fetched {len(posts)} posts: subredddit={subreddit.title}")

        n_written = write_reddit_posts(posts)
        log.info(f"Wrote {n_written} reddit posts: subreddit={subreddit.title}")

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
        log.info(f"Running topic model for niche: {niche.title}")
        print(f"Running topic model for niche: {niche.title}")
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
def run_niche_trends(niche_id) -> List[uuid.UUID]:
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
        if topic_labels is None:
            continue
        for i, title_desc in enumerate(topic_labels):

            # create modeled topic
            modeled_topic = {
                "id": uuid.uuid4(),
                "niche_id": niche_id,
                "name": title_desc[0],
                "description": title_desc[1],
                "date": datetime.now(),
                "size": 0,
                "trend_class": "trending",
            }

            # create news articles
            news_articles = []
            for n in topic_articles[i]:
                news_article = {"id": uuid.uuid4(), "title": n["title"], "url": n["url"],
                                "published_date": n["published_date"]}
                news_articles.append(news_article)

            # write to db
            write_news_articles(news_articles)
            write_modeled_topic_with_news_article(
                modeled_topic, [n["id"] for n in news_articles]
            )
            all_topics.append(modeled_topic)

    return [t["id"] for t in all_topics]


def build_topic_dicts(posts, source, niche):

    if len(posts) < TOPIC_MODEL_MIN_DOCS:
        log.error(f"Not enough posts for topic model: niche={niche.title}")
        raise ValueError("Not enough posts to run topic model", niche.title)

    post_dicts = [_to_dict(p) for p in posts]
    texts = [p["clean_text"] for p in post_dicts]

    log.info(f"Building topic model: niche={niche.title}")
    if source == "reddit":
        topic_model = topic.build_subtopic_model(texts)
    else:
        topic_model = topic.build_subtopic_model(texts, min_samples=5, min_cluster_size=5)
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
        source,
        trend_prev_days=14,
    )

    return topic_dicts


@shared_task
def run_niche_topic_model(niche_id, date_from=None, date_to=None) -> List[dict]:
    """
    First step of topic pipeline:
    read recent posts for the niche and run the BERTopic model.
    """
    print('building topics')
    niche = Niche.query.get(niche_id)
    sub_ids = [sub.id for sub in niche.subreddits]
    topic_dicts = []
    # what data do we want to use here?

    if niche.title in ["Entrepreneurship", "Marketing", "Personal Development"]:
        if date_from is not None and date_to is not None:
            twitter_posts = Tweet.query.filter(
                and_(
                    Tweet.niche_id == niche.id,
                    Tweet.published_at >= date_from,
                    Tweet.published_at <= date_to
                )
            ).all()
        else:
            twitter_posts = Tweet.query.filter(
                and_(
                    Tweet.niche_id == niche.id,
                    Tweet.published_at > datetime.now() - timedelta(days=7)
                )
            ).all()

        topic_dicts = build_topic_dicts(twitter_posts, "twitter", niche)
        print(' in twitter, type of topic dict', type(topic_dicts))

    if date_from is not None and date_to is not None:
        reddit_posts = RedditPost.query.filter(
            and_(
                RedditPost.created_at >= date_from,
                RedditPost.created_at <= date_to,
                RedditPost.subreddit_id.in_(sub_ids),
            )
        ).all()
    else:
        reddit_posts = RedditPost.query.filter(
            and_(
                RedditPost.created_at > datetime.now() - timedelta(days=7),
                RedditPost.subreddit_id.in_(sub_ids),
            )
        ).all()

    topic_dicts = topic_dicts + build_topic_dicts(reddit_posts, "reddit", niche)
    return topic_dicts


@shared_task
def generate_niche_topic_overviews(
        topic_dicts: List[dict],
        niche_id: uuid.UUID,
        max_modeled_topics=13,
        topic_date=None
) -> List[uuid.UUID]:
    """
    Second step of topic pipeline:
    given the output of run_niche_topic_model, generate modeled topics
    and store them to the database.

    Returns list of modeled topic IDs that were created.
    """
    print('generating topic overview')
    print('type of topic_dicts', type(topic_dicts))

    niche = Niche.query.get(niche_id)
    modeled_topic_ids = []
    count = 0
    for topic_dict in topic_dicts:
        if count >= max_modeled_topics:
            break
        # query the text of the representative posts for this topic
        post_ids = topic_dict["post_ids"]

        if topic_dict["source"] == "twitter":
            posts_query = db.session.query(Tweet.clean_text).filter(
                Tweet.id.in_(post_ids[:4])
            )
        else:
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
        
        if topic_date is None:
            topic_date = datetime.now()
        modeled_topic = {
            "id": uuid.uuid4(),
            "niche_id": niche_id,
            "name": topic_label,
            "description": topic_desc,
            "date": topic_date,
            "size": topic_dict["rank"],
        }
        if topic_dict["source"] == "twitter":
            modeled_topic["trend_class"] = "twitter"
            write_modeled_topic_with_twitter_posts(modeled_topic, post_ids)
        else:
            write_modeled_topic_with_reddit_posts(modeled_topic, post_ids)
        modeled_topic_ids.append(modeled_topic["id"])
        count += 1

    log.info(f"{count} modeled topics created: niche={niche_id}")
    return modeled_topic_ids


@shared_task
def generate_modeled_topic_tweets(modeled_topic_ids):
    """
    Third step of topic pipeline:
    generate tweets for each modeled topic
    """
    print('type of modeled_topic_ids', type(modeled_topic_ids))
    for mt_id in modeled_topic_ids:
        modeled_topic = ModeledTopic.query.get(mt_id)
        generated_tweets = topic.generate_tweets_for_topic(
            10, modeled_topic.name, modeled_topic.description, 3
        )

        for tweet in generated_tweets:
            tweet["modeled_topic_id"] = mt_id

        num_tweets = len(generated_tweets)
        log.info(
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

    log.info(f"Generating GPT topics and posts: niche={niche.title}")
    print(f"Generating GPT topics and posts: niche={niche.title}")
    generated_tweets = topic.generate_tweets_for_topic(
        21, niche.title, niche.title, num_topics_from_topic_label=5
    )
    print("Got tweets")
    log.info("Got tweets")
    modeled_topics = []
    # these are "psuedo" modeled topics since they
    # aren't derived from BERTopic
    modeled_topic = {
        "id": uuid.uuid4(),
        "name": niche.title,
        "niche_id": niche_id,
        "date": datetime.now().date(),
    }
    modeled_topics.append(modeled_topic)

    for post in generated_tweets:
        post["modeled_topic_id"] = modeled_topic["id"]

    log.info(f"Created topic and post dicts")
    write_modeled_overview(modeled_topics)
    write_generated_posts(generated_tweets)
    log.info(f"Written topic and post dicts to db")

def write_modeled_overview(topic_overviews: List[dict]) -> None:
    """
    """
    for topic in topic_overviews:
        try:
            db.session.add(ModeledTopic(**topic))
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            log.error(f"Database error occurred: {e}")
        else:
            db.session.commit()
    log.info(f"wrote overview for {len(topic_overviews)} modeled topics.")


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
        log.info("no tweets to schedule")
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
                log.error(
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
