import logging
import uuid
from datetime import datetime, timedelta
from typing import List
from celery import shared_task

from sqlalchemy import and_
from topic_model import topic
from .models import (
    db,
    RedditPost, Niche, ModeledTopic,
    _to_dict,
)

from .reddit import (
    process_post,
    fetch_subreddit_posts,
    write_reddit_modeled_overview,
    write_modeled_topic_with_reddit_posts,
    write_reddit_posts,
    write_generated_posts,
)

TOPIC_MODEL_MIN_DOCS = 20

@shared_task
def all_niches_reddit_update():
    '''
    For each active niche, fetch recent posts and save to database.
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

    for niche in niches:
        logging.info(
            f"Running topic model for niche: {niche.title}"
        )
        # model runs are serial for now since we only have
        # one worker machine
        topic_dicts = run_niche_topic_model.apply_async(
            args=(niche.id,)).get()

        modeled_topic_ids = generate_niche_topic_overviews(
            niche.id, topic_dicts, max_modeled_topics_per_niche=20
        )

        for mt_id in modeled_topic_ids:
            generate_modeled_topic_tweets.apply_async(
                args=(mt_id,)
            )



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
def run_niche_topic_model(niche_id) -> List[dict]:
    '''
    Read recent posts for the niche and run the topic model.
    '''
    niche = Niche.query.filter(Niche.id == niche_id).one()
    sub_ids = [sub.id for sub in niche.subreddits]

    # what data do we want to use here?
    posts = RedditPost.query.filter(
        and_(
            RedditPost.created_at > datetime.now() - timedelta(days=18),
            RedditPost.subreddit_id.in_(sub_ids),
        )
    ).all()

    if len(posts) < TOPIC_MODEL_MIN_DOCS:
        logging.error(
            f"Not enough posts for topic model: niche={niche.title}")
        return

    post_dicts = [_to_dict(p) for p in posts]
    texts = [p["clean_text"] for p in post_dicts]

    logging.info(f"Building topic model: niche={niche.title}")
    topic_model = topic.build_subtopic_model(texts)
    topics, probs = topic_model.topics_, topic_model.probabilities_
    topic_dicts = topic.analyze_topics(
        topics,
        probs,
        post_dicts,
        "reddit",
        trend_prev_days=14,
    )
    return topic_dicts


@shared_task
def generate_niche_topic_overviews(
        niche_id: uuid.UUID,
        topic_dicts: List[dict],
        max_modeled_topics_per_niche=20,
) -> List[uuid.UUID]:
    '''
    Given the output of run_niche_topic_model,
    generate topic overviews and store the modeled topics to the database.
    '''
    count = 0
    for topic_dict in topic_dicts:
        if count > max_modeled_topics_per_niche:
            break
        # query the text of the representative posts for this topic
        post_ids = topic_dict["post_ids"]
        posts_query = db.session.query(
            RedditPost.clean_text
        ).filter(
            RedditPost.id.in_(post_ids[:4])
        )
        texts = [t for (t,) in posts_query.all()]

        topic_label, topic_desc = topic.generate_topic_overview(texts)
        if topic_label == "" or topic_desc == "":
            continue  # discard this topic

        modeled_topic = {
            "id": uuid.uuid4(),
            "niche_id": niche_id,
            "name": topic_label,
            "desciption": topic_desc,
            "date": datetime.now().date(),
            "size": topic_dict["rank"],
        }
        write_modeled_topic_with_reddit_posts(
            modeled_topic, post_ids
        )
        count += 1

    logging.info(f"{count} modeled topics created: niche={niche_id}")


def generate_modeled_topic_tweets(modeled_topic_id):
    '''
    Generate tweets for a modeled topic
    '''
    modeled_topic = ModeledTopic.query.get(modeled_topic_id)
    _, generated_tweets = topic.generate_tweets_for_topic(
        2, modeled_topic.title
    )

    for tweet in generated_tweets:
        tweet["modeled_topic_id"] = modeled_topic_id

    write_generated_posts(generated_tweets)


@shared_task
def generate_niche_gpt_topics(niche_id):
    '''
    Generate modeled topics and posts for a niche with GPT.
    This does not use BERTopic or reddit/twitter data.
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
            "date": datetime.now().date(),
        }
        for post in generated_tweets:
            if post["topic_label"] == related_topic:
                post["modeled_topic_id"] = modeled_topic["id"]
        modeled_topics.append(modeled_topic)

    write_reddit_modeled_overview(modeled_topics)
    write_generated_posts(generated_tweets)
