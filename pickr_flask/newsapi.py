import logging
import re
from datetime import date, timedelta
from os import environ
from typing import List

from newsapi import NewsApiClient
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sqlalchemy import exc, insert


from .models import db, NewsArticle, ModeledTopic, news_modeled_topic_assoc
from topic_model.topic import get_label

newsapi = NewsApiClient(api_key=environ["NEWS_API_KEY"])


def get_trends(term, page_size=10, num_pages=10):
    # get articles
    num_pages = 10
    docs = []
    today = date.today()
    start_date = today - timedelta(days=7)
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
        except Exception as e:
            continue
    docs = list(set(docs))

    # get articles without stop words
    lemmatizer = WordNetLemmatizer()
    docs_non_sw = []
    for d in docs:
        non_stop_title = " ".join(
            [
                lemmatizer.lemmatize(word).lower()
                for word in word_tokenize(d)
                if word not in stop_words and word.strip != "" and len(word) > 1
            ]
        )
        non_stop_title = re.sub("[^a-zA-Z0-9 \n\.]", "", non_stop_title)
        non_stop_title = set(word_tokenize(non_stop_title))
        docs_non_sw.append(non_stop_title)

    # get article topics that appear more than once
    added_posts = []
    topics = []
    for i, d in enumerate(docs_non_sw):
        if docs[i] in added_posts:
            continue
        matches = [docs[i]]
        for x, d_ in enumerate(docs_non_sw):
            if i != x and len(d.intersection(d_)) > 3:
                if docs[x] not in added_posts:
                    matches.append(docs[x])
        if len(matches) > 1:
            topics.append(matches)
            for d__ in matches:
                added_posts.append(d__)

    labels = []
    for t in topics:
        topic_documents = "\n\n".join(["Message:    " + d_[:1000] for d_ in t[:4]])
        labels.append(get_label(topic_documents))
    return labels, topics


def get_articles(term, page_size=10):
    today = date.today()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    try:
        all_articles = newsapi.get_everything(
            q=term,
            from_param=yesterday_str,
            to=yesterday_str,
            language="en",
            sort_by="relevancy",
            page_size=page_size,
            page=1,
        )
    except Exception:
        return None
    return [
        {"title": v["title"], "date": v["publishedAt"], "url": v["url"]}
        for v in all_articles["articles"]
    ]


def write_news_articles(posts: List[dict]) -> int:
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
    Save a modeled topic to the database and associate reddit IDs
    with the topic.
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
