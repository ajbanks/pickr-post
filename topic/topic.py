"""
Module to compute and store topic info
"""
import time

from datetime import datetime
from dataclasses import dataclass
from typing import List

import openai
import pandas as pd
import numpy as np

from bertopic import BERTopic
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from openai.error import RateLimitError

RANDOM_STATE = 42

openai.api_key = "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"


def build_subtopic_model(
    tweet_df: pd.DataFrame, source: str, min_date=None, max_relevant_posts=30
):
    tweet_df["created_at"] = tweet_df["created_at"].fillna(
        datetime.now().strftime("%Y-%m-%d")
    )
    tweet_df["date"] = pd.to_datetime(tweet_df["created_at"])
    tweet_df["created_at"] = pd.to_datetime(tweet_df["created_at"])
    tweet_df["date"] = pd.to_datetime(tweet_df["created_at"]).dt.date
    tweet_df["clean_text"] = tweet_df["clean_text"].astype(str)
    if min_date is not None:
        tweet_df = tweet_df[tweet_df["created_at"] >= min_date]
    tweet_filt_df = tweet_df.drop_duplicates(subset=["clean_text"])
    tweets = tweet_filt_df["clean_text"].tolist()
    raw_tweets = tweet_filt_df["text"].tolist()

    # train model
    vectorizer_model = CountVectorizer(stop_words="english")
    topic_model = BERTopic(
        vectorizer_model=vectorizer_model,
        n_gram_range=(1, 2),
    )
    topics, probs = topic_model.fit_transform(tweets)
    labels = topic_model.generate_topic_labels()
    print("num topics", len(labels))

    valid_topics = filter_topics(topics, probs)

    # get topic tweets for valid topics
    topics_info = {}
    for vt in valid_topics:
        # get tweets indices sorted by probability
        tweet_prob = [(idx, probs[idx]) for idx, t in enumerate(topics) if t == vt]
        tweet_prob = sorted(tweet_prob, key=lambda tup: tup[1], reverse=True)

        # get all tweets in this topic and put them in a df
        tweet_idx = [idx for idx, t in enumerate(topics) if t == vt]
        tweet_text = [tweets[i] for i in tweet_idx]
        topic_df = tweet_df[tweet_df["clean_text"].isin(tweet_text)]
        num_tweets = len(topic_df)
        # Get daily stats and the trend type of the topic
        num_likes, num_retweets, topic_df_grp = get_topic_stats(topic_df, source)
        try:
            if source == "twitter":
                trend = trend_type(topic_df_grp["likes"].values)
            elif source == "reddit":
                trend = trend_type(topic_df_grp["score"].values)
        except Exception:
            trend = "Trend just started"

        # Get topic label, description, generated tweets and final topic filter
        (
            topics_info,
            topic_label,
            topic_desc,
            generated_tweet_1,
            generated_tweet_2,
            valid_topic,
        ) = get_gen_tweets_and_label(raw_tweets, tweet_prob, topics_info)
        if valid_topic == False:  # if topic isnt valid then skip
            continue

        # get tweets that have high prob of beloning to topic and are most liked
        high_prob_tweets = []
        for twt_idx, prob in tweet_prob[:max_relevant_posts]:
            high_prob_tweets.append(tweets[twt_idx])

        most_relevant_tweets = tweet_df[  # TODO: dont only use high prob tweets
            tweet_df["clean_text"].isin(high_prob_tweets)
        ]
        most_relevant_tweets = format_relevant_posts(most_relevant_tweets, source)

        # put all topic data in list
        generated_tweets = [generated_tweet_1, generated_tweet_2]
        t = Topic(
            labels[vt],
            topic_label,
            topic_desc,
            trend,
            int(num_tweets),
            int(num_retweets),
            int(num_likes),
            generated_tweets,
            most_relevant_tweets,
        )
        topics_info[labels[vt]] = t

    return topic_model, topics_info


def get_topic_stats(df, source):
    if source == "twitter":
        return (
            df["likes"].sum(),
            df["retweets"].sum(),
            df.groupby("date", as_index=False).agg(
                {"likes": "sum", "retweets": "sum", "url": "count"}
            ),
        )
    elif source == "reddit":
        return (
            df["score"].sum(),
            0,
            df.groupby("date", as_index=False).agg({"score": "sum", "link": "count"}),
        )


def get_gen_tweets_and_label(raw_tweets, tweet_prob, topics_info):
    # use gpt to get topic label, validate if its a topic and generate tweets relevant to the topic
    body = ""
    for twt_idx, prob in tweet_prob[:5]:
        body += "\n\nMessage: " + raw_tweets[twt_idx]
    body = body[:4097]

    while True:
        try:
            valid_topic = (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": valid_topic_test(body)}],
                    temperature=0.2,
                )
                .choices[0]
                .message.content
            )
        except:
            time.sleep(60)
            continue
        break
    if valid_topic[:3] != "Yes":
        return topics_info, None, None, None, None, False

    while True:
        try:
            topic_label = (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": create_label(body)}],
                    temperature=0.2,
                )
                .choices[0]
                .message.content
            )
            for k, v in topics_info.items():
                if topic_label in v.readable_topic_name:
                    topic_label = topic_label + " (Second discussion)"
        except:
            time.sleep(60)
            continue
        break

    # fix formatting of topic label
    if "Label: " in topic_label:
        topic_label = topic_label.split("Label: ", 1)[1]

    while True:
        try:
            topic_desc = (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": create_description(body)}],
                    temperature=0.2,
                )
                .choices[0]
                .message.content
            )
        except:
            time.sleep(60)
            continue
        break

    while True:
        try:
            generated_tweet_1 = (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "user",
                            "content": generate_tweet(body, topic_label),
                        }
                    ],
                    temperature=0.8,
                )
                .choices[0]
                .message.content
            )
        except:
            time.sleep(60)
            continue
        break

    while True:
        try:
            generated_tweet_2 = (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {
                            "role": "user",
                            "content": generate_tweet(body, topic_label),
                        }
                    ],
                    temperature=0.8,
                )
                .choices[0]
                .message.content
            )
        except:
            time.sleep(60)
            continue
        break
    return (
        topics_info,
        topic_label,
        topic_desc,
        generated_tweet_1,
        generated_tweet_2,
        valid_topic,
    )


def filter_topics(topics, probs):
    # Filter Topics
    topic_max_prob = [0] * len(set(topics))
    topic_avg_prob = [0] * len(set(topics))
    topic_count = [0] * len(set(topics))
    # get topic statistics
    for t_i, p in zip(topics, probs):
        if topic_count[t_i] > 0:
            # update avergae
            topic_avg_prob[t_i] = (topic_count[t_i] * topic_avg_prob[t_i] + p) / (
                topic_count[t_i] + 1
            )
        else:
            topic_avg_prob[t_i] = p
        topic_count[t_i] += 1
        if topic_max_prob[t_i] < p:
            topic_max_prob[t_i] = p

    # filter out invalide topics using their statistics
    count_prob_valid_topics = [
        i
        for i in range(len(set(topics)))
        if topic_avg_prob[i] >= 0.5 and topic_count[i] >= 10
    ]
    print("num topics", len(count_prob_valid_topics))

    # for the remaining valid topics get in-topic similarity
    # for each topic get embeddings for each document
    """doc_embeddings = {}
    i_doc = []
    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    for i, doc in enumerate(tweets):
        if topics[i] in count_prob_valid_topics:
            i_doc.append((i, doc))

    embs = sentence_model.encode([item[1] for item in i_doc])
    doc_embeddings = {i_doc[i][0]: e for i, e in enumerate(embs)}

    # do cosine simialrity between every document and calculate average
    valid_topics = []
    for ti in count_prob_valid_topics:
        topic_doc_embeddings = [
            doc_embeddings[i]
            for i, tweet_topic_index in enumerate(topics)
            if tweet_topic_index == ti
        ]
        avg_sim = np.mean(cosine_similarity(topic_doc_embeddings, topic_doc_embeddings))
        if (avg_sim) >= 0.4:
            valid_topics.append(ti)"""

    valid_topics = count_prob_valid_topics
    print("num topics", len(valid_topics))
    return valid_topics[:30]


def format_relevant_posts(df, source):
    if source == "twitter":
        cols = ["date", "username", "text", "likes", "retweets", "url"]
        df = df.sort_values(by="likes", ascending=False)[cols]
        df["date"] = df["date"].astype(str)
        df["likes"] = df["likes"].astype(int)
        df["retweets"] = df["retweets"].astype(int)
        df = df.rename(
            columns={
                "date": "Date",
                "username": "Username",
                "text": "Text",
                "likes": "Likes",
                "retweets": "Retweets",
            }
        )
        return df
    elif source == "reddit":
        cols = ["date", "title", "body", "score", "link"]
        df = df.sort_values(by="score", ascending=False)[cols]
        df["date"] = df["date"].astype(str)
        df["score"] = df["score"].astype(int)

        df = df.rename(
            columns={
                "date": "Date",
                "title": "Title",
                "body": "Body",
                "score": "Score",
                "link": "Link",
            }
        )
        return df


def trend_type(points):
    x = np.arange(0, len(points))
    y = np.array(points)
    # Fit line
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= 0.7:
        return "Hot Trend"
    elif slope >= 0.4:
        return "Bubbling Trend"
    elif slope >= 0:
        return "Slowly Growing Trend"
    else:
        return "Trend getting smaller"


def valid_topic_test(text):
    return f"Are the tweets below about the same topics? Answer Yes or No. {text}"


def create_description(text):
    return f"Create a one sentence summary that describes the key topics in the tweets below. Start the description  'The posts in this topic are about'. Each tweet starts with the word Message. {text}"


def create_label(text):
    return f"Provide a label that captures the key words in all the messages below. Each message starts with the word Message. {text}"


def generate_tweet(text, topic_label):
    return f"You are a social media content creator. You write tweets that are thought provoking and authoritative. People learn alot from your tweets. I am going to show you a few tweets about the topic {topic_label}. I then want you to generate a new viral tweet. Do not mention any events, dates or company names. Here are the tweets: {text}"


@dataclass
class Topic:
    """Class for storing Topic data"""

    model_topic_name: str
    readable_topic_name: str
    description: str
    trend_type: str
    size: int
    num_retweets: int
    num_likes: int
    generated_tweets: List[str]
    topic_tweets: pd.DataFrame
