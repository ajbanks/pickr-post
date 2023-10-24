import logging
import re
from datetime import date, timedelta
from os import environ
from typing import List

import nltk
from flask import current_app as app
from newsapi import NewsApiClient
from sqlalchemy import exc, insert

from .models import db, NewsArticle, ModeledTopic, news_modeled_topic_assoc
from topic_model.topic import get_label_and_description_no_keywords
from topic_model.util import remove_stop_words

newsapi = NewsApiClient(api_key=app.config["NEWS_API_KEY"])


def get_trends(term, page_size=100, num_pages=1, min_words=4, min_matches=2):
    """
    Get news articles and get topics from them
    """
    # get articles
    docs = []
    docs_dict = []
    today = date.today()
    start_date = today - timedelta(days=14)
    start_date_str = start_date.strftime("%Y-%m-%d")
    for i in range(num_pages):
        try:
            all_articles = newsapi.get_everything(
                q=term,
                from_param=start_date_str,
                to=start_date,
                language="en",
                sort_by="relevancy",
                page_size=page_size,
                page=i + 1,
            )
            docs += [a["title"] for a in all_articles["articles"]]
            docs_dict += [{"title": a["title"], "url": a["url"], "published_date": a["publishedAt"]}  for a in all_articles["articles"]]
        except Exception as e:
            return

    # remove duplicate articles
    docs = list(set(docs))
    docs_dict_ = []
    for l in list(set(docs)):
        for j in docs_dict:
            if j['title'] == l:
                docs_dict_.append(j)
                break

    # get articles without stop words
    docs_non_sw = remove_stop_words(docs)

    # get article topics that appear more than once
    added_posts = []
    topic_articles = []
    for i, d in enumerate(docs_non_sw):
        if docs[i] in added_posts:
            continue
        matches = [docs_dict_[i]]
        for x, d_ in enumerate(docs_non_sw):
            if i != x and len(d.intersection(d_)) >= min_words:
                if docs[x] not in added_posts:
                    matches.append(docs_dict_[x])
        if len(matches) >= min_matches:
            topic_articles.append(matches)
            for d__ in matches:
                added_posts.append(d__['title'])

    topic_labels = []
    for t in topic_articles:
        topic_documents = "\n\n".join(["Message:    " + d_[:1000] for d_ in t[:4]])
        topic_labels.append(get_label_and_description_no_keywords(topic_documents))
    return topic_labels, topic_articles


def write_news_articles(posts: List[dict]) -> int:
    """
    Save news articles
    """
    num_written = 0
    for post in posts:
        record = (
            db.session.query(NewsArticle).filter(NewsArticle.id == post["id"]).first()
        )
        if record is None:
            record = NewsArticle(**post)
            try:
                db.session.add(record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                logging.error(f"Error writing news article: {e}")
            else:
                db.session.commit()
                num_written += 1
    return num_written


def write_modeled_topic_with_news_article(topic: dict, post_ids: List[int]) -> None:
    """
    Save a modeled topic to the database and associated news article IDs with the topic.
    """
    modeled_topic = ModeledTopic(**topic)
    try:
        db.session.add(modeled_topic)
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error occured: {e}")
    else:
        db.session.commit()

    try:
        db.session.execute(
            insert(news_modeled_topic_assoc),
            [
                {"news_id": pid, "modeled_topic_id": modeled_topic.id}
                for pid in post_ids
            ],
        )
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        logging.error(f"Database error occured: {e}")
    else:
        db.session.commit()
