"""
Module to compute topic info
"""
import logging
import time
import os
import math
import uuid
from datetime import datetime, timedelta

import re
import openai
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
# from sklearn.metrics.pairwise import cosine_similarity
# from sentence_transformers import SentenceTransformer
# from openai.error import RateLimitError

RANDOM_STATE = 42

openai.api_key = os.getenv("OPENAI_API_KEY")
BRAND_VOICES = [
    "Playful and Youthful",
    "Professional and Authoritative",
    "Inspirational and Empowering",
    "Friendly and Supportive",
    "Bold and Innovative",
]


# TODO: split this into smaller functions
def build_subtopic_model(
    tweet_df: pd.DataFrame,
    source: str,
    niche_title: str,
    min_date=None,
    trend_prev_days: int = 14,
    max_relevant_topics: int = 20,
    num_gen_tweets: int = 2,
    num_topics_from_topic_label: int = 5,
):
    # local import because this is import is slow
    from bertopic import BERTopic
    from hdbscan import HDBSCAN

    tweet_df = tweet_df.reset_index(drop=True)
    tweet_df["created_at"] = tweet_df["created_at"].fillna(
        datetime.now().strftime("%Y-%m-%d")
    )
    tweet_df["date"] = pd.to_datetime(tweet_df["created_at"]).dt.date
    tweet_df["clean_text"] = tweet_df["clean_text"].astype(str)
    tweet_df["modeled_topic_id"] = np.nan
    if min_date is not None:
        tweet_df = tweet_df[tweet_df["created_at"] >= min_date]
    tweets = tweet_df["clean_text"].tolist()

    # train model
    vectorizer_model = CountVectorizer(stop_words="english")
    hdbscan_model = HDBSCAN(min_cluster_size=3, min_samples=1, metric='euclidean', cluster_selection_method='eom', prediction_data=True)
    topic_model = BERTopic(
        vectorizer_model=vectorizer_model,
        n_gram_range=(1, 2),
        hdbscan_model=hdbscan_model
    )
    topics, probs = topic_model.fit_transform(tweets)

    # TODO: Reintroduce gpt topic filter
    valid_topics = filter_topics(topics, probs)

    # Remove topics that aren't trending
    topics_list = []
    for vt in valid_topics:

        # get all tweets in this topic and put them in a df
        tweet_idx = [idx for idx, t in enumerate(topics) if t == vt]
        topic_df = tweet_df.iloc[tweet_idx]
        num_posts = len(topic_df)
        # Get daily stats and the trend type of the topic
        (
            num_likes,
            num_retweets,
            topic_df_grp
        ) = get_topic_stats(topic_df, source)
        date_thres = datetime.now() - timedelta(days=trend_prev_days)
        recent_posts = topic_df_grp[topic_df_grp["date"] >= date_thres.date()]
        try:
            if len(recent_posts) == 0:
                trend = 5
            elif source == "twitter":
                trend = trend_type(recent_posts["likes"].values)
            elif source == "reddit":
                trend = trend_type(recent_posts["score"].values)
        except Exception as e:
            trend = 3
        topics_list.append(
            (vt, num_posts, num_likes, num_retweets, trend, topic_df_grp)
        )


    # sort topics first by trend and then by number of posts in the topic
    s_topics_list = sorted(topics_list, key=lambda x: (x[4], -x[1]))

    # update topic size
    topics_list = []
    topic_rank = len(s_topics_list)
    for t in s_topics_list:
        topics_list.append((t[0], topic_rank, t[2], t[3], t[4], t[5]))
        topic_rank -= 1

    topic_overviews = []
    generated_tweets = []
    count = 0
    for vt, size, num_likes, num_retweets, trend, topic_df_grp in topics_list:
        # get tweets from topic,
        # ordered by probability of belonging to the topic
        tweet_idx_prob = [(idx, probs[idx]) for idx, t in enumerate(topics) if t == vt]
        tweet_idx_prob = sorted(tweet_idx_prob, key=lambda tup: tup[1], reverse=True)
        tweet_idx = [idx_prob[0] for idx_prob in tweet_idx_prob]
        topic_df = tweet_df.iloc[tweet_idx]

        body = ""
        for twt in topic_df["clean_text"].tolist()[:5]:
            body += "\n\nMessage: " + twt
        body = body[:4097]
        if count >= max_relevant_topics:
            break

        # (meiji163) is this a good strategy, seems overkill?
        # TODO: check if topic is part of the niche via gpt
        valid_topic = send_chat_gpt_message(valid_topic_test(body), temperature=0.2)
        if valid_topic[:3] != "Yes":
            continue
        
        # Get topic label, description, generated tweets and final topic filter
        (
            topic_label,
            topic_desc,
        ) = get_label_and_description(body)
        valid_topic = send_chat_gpt_message(is_topic_related_to_niche(niche_title, topic_label), temperature=0.2)
        if valid_topic[:3] != "Yes":
            continue

        topic_id = uuid.uuid4()
        # TODO(nathan): add probabilities so that tweets can be sorted by
        # probabilities in the UI
        tweet_df.loc[tweet_idx, 'modeled_topic_id'] = topic_id
        # generate tweets based on topic label
        _, topic_gen_tweets = generate_tweets_for_topic(
            num_gen_tweets, topic_label, num_topics_from_topic_label
        )
        for t in topic_gen_tweets:
            t["modeled_topic_id"] = topic_id
        generated_tweets.extend(topic_gen_tweets)
        topic_overviews.append({
            "id": topic_id,
            "name": topic_label,
            "description": topic_desc,
            "size": size,
            "trend_type": trend,
            "date": datetime.now(),
        })
        count += 1

    return (
        topic_overviews,
        generated_tweets,
        tweet_df["modeled_topic_id"].values
    )


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
            df.groupby("date", as_index=False).agg(
                {"score": "sum", "url": "count"}
            ),
        )


# TODO: add rate limit backoff
def get_label_and_description(body):
    """use gpt to get topic label and description"""
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

    return topic_label, topic_desc


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
        if topic_avg_prob[i] >= 0.5
    ]

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
    return valid_topics


def format_relevant_posts(df, source):
    if source == "twitter":
        cols = [
            "date",
            "username",
            "text",
            "likes",
            "retweets",
            "url",
            "modeled_topic_id"
        ]
        df = df.sort_values(by="likes", ascending=False)[cols]
        df["date"] = df["date"].astype(str)
        df["likes"] = df["likes"].astype(int)
        df["retweets"] = df["retweets"].astype(int)
    elif source == "reddit":
        cols = [
            "reddit_id",
            "date",
            "title",
            "body",
            "score",
            "url",
            "modeled_topic_id"
        ]
        df = df.sort_values(by="score", ascending=False)[cols]
        df["date"] = df["date"].astype(str)
        df["score"] = df["score"].astype(int)
    df["id"] = uuid.uuid4()
    return df


def trend_type(points):
    x = np.arange(0, len(points))
    y = np.array(points)
    # Fit line
    slope, intercept = np.polyfit(x, y, 1)
    if slope >= 0.7:
        return 0
    elif slope >= 0.4:
        return 1
    elif slope >= 0:
        return 2
    else:
        return 4


def send_chat_gpt_message(message, temperature=0.8):  # TODO: check the temperature is correct
    while True:
        try:
            return (
                openai.ChatCompletion.create(
                    model="gpt-3.5-turbo",
                    messages=[{"role": "user", "content": message}],
                    temperature=temperature,
                )
                .choices[0]
                .message.content
            )
        except:
            time.sleep(60)
            continue


def rewrite_tweets_in_brand_voices(tweet_list):
    """rewrite tweets in different brand voices"""
    new_tweets = []

    for tweet in tweet_list:
        for brand_voice in BRAND_VOICES:
            new_tweets.append(rewrite_post_in_brand_voice(brand_voice, tweet))

    return tweet_list + new_tweets


def generate_tweets_for_topic(
        num_tweets,
        topic_label,
        num_topics_from_topic_label=5
):
    """
    Take a topic label and query GPT for related topics,
    then generate tweets for each of those related topics.
    Returns (related_topics, generated_tweets)
    """
    num_tweets_per_tweet_type = math.ceil(
        num_tweets / num_topics_from_topic_label
    )
    num_tweets_per_tweet_type = (
        1 if num_tweets_per_tweet_type <= 0 else num_tweets_per_tweet_type
    )

    # get topics related to topic label
    # TODO: potentially remove the generate_related_topics as it might not be necessary
    related_topics = generate_related_topics(
        num_topics_from_topic_label, topic_label
    )[:num_topics_from_topic_label]
    related_topics = [r for r in related_topics if r.strip() != ""]
    generated_tweets = []
    for topic in related_topics:
        # TODO: generate_informative_tweets_for_topic and
        # generate_future_focused_tweets_for_topic dont reliably create
        # the correct number of tweets (maybe due to temp value)
        # and the split function doesnt accurately split tweets

        for i in range(num_tweets_per_tweet_type):
            tweet = generate_controversial_tweets_for_topic(topic)           
            generated_tweets.append({
                "topic_label": topic_label + "; " + topic,
                "information_type": "controversial",
                "text": tweet,
            })

            tweet = generate_hyperbole_tweets_for_topic(topic)
            generated_tweets.append({
                "topic_label": topic_label + "; " + topic,
                "information_type": "hyperbole",
                "text": tweet,
            })

            tweet = generate_advice_tweets_for_topic(topic)
            generated_tweets.append({
                "topic_label": topic_label + "; " + topic,
                "information_type": "advice",
                "text": tweet,
            })

    generated_tweets = list(filter(
        lambda t: len(t["text"]) >= 30,
        generated_tweets
    ))

    return related_topics, generated_tweets


def valid_topic_test(text):
    return f"You will answer my questions to the best of your ability and truthfully. Are the social media posts below about the same topic? Answer Yes or No. {text}"


def is_topic_related_to_niche(topic_label, niche_label):
    test_string = f"You will answer my questions to the best of your ability and truthfully. Is the topic label '{topic_label}' related to {niche_label}? Answer Yes or No."
    return test_string


def create_description(text):
    return f"Create a one sentence summary that describes the key topics in the tweets below. Start the description  'The posts in this topic are about'. Each tweet starts with the word Message. {text}"


def create_label(text):
    return f"You are a highly skilled social media assistant that follows my instructions to the best of your ability. Provide a short label that captures the key words in all the social media posts below. The label you create must be a maximum of five words long. The label you create must be clear and concise and focus one one topic. {text}"


def convert_chat_gpt_response_to_list(str_response):
    return [s.strip("'-" + '"') for s in re.split("\n", str_response)]


def generate_tweet(text, topic_label):
    return f"You are a social media content creator. You write tweets that are thought provoking and authoritative. People learn alot from your tweets. I am going to show you a few tweets about the topic {topic_label}. I then want you to generate a new viral tweet. Do not mention any events, dates or company names. Here are the tweets: {text}"


def generate_related_topics(
    num_topics, topic_label
):  # TODO: this might only work for high level topics, check this
    message = f"You are a highly skilled social media content creator. You come up with viral topics to tweet about. Create {num_topics} topics to tweet about related to {topic_label}. Don't add any numbering to the topics and separate each topic with a new line character."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


# def generate_10_brand_voice_tweets_for_topic(brand_voice, topic):
#     return f"You are a social media content creator. You manage social media profiles and have been asked to come up with tweets that your client should tweet. Create 10 tweets related to {topic} written in a {brand_voice} brand voice. Don't add any numbering to the tweets and separate each tweet with a new line character."


def generate_informative_tweets_for_topic(num_tweets, topic):
    message = f"You are a educational social media content creator. You manage social media profiles and have been asked to come up with tweets that your client should tweet. Create {num_tweets} tweets that explain {num_tweets} different aspects of {topic}. Don't mention any specific twitter users or tools. Don't include any emoji's. Don't add any numbering to the tweets and separate each tweet with a new line character. Each tweet should be on a new line with no gaps in between them."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


def generate_future_focused_tweets_for_topic(num_tweets, topic):
    message = f"You are a futurist social media content creator. You manage social media profiles and have been asked to come up with tweets that your client should tweet. Create {num_tweets} tweets that talks about the future of {topic} and how it will change over time from {num_tweets} different perspectives. Don't mention any specific twitter users or tools. Don't include any emoji's. Don't add any numbering to the tweets and separate each tweet with a new line character. Each tweet should be on a new line with no gaps in between them."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


def generate_past_focused_tweets_for_topic(num_tweets, topic):
    message = f"You are a historian social media content creator. You manage people's social media profiles and have been asked to come up with tweets that your client should tweet. Create {num_tweets} tweets that talks about the history of {topic} and how it changed over time. Don't mention any specific twitter users or tools. Don't include any emoji's. Don't add any numbering to the tweets and separate each tweet with a new line character."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


def generate_controversial_tweets_for_topic(topic):
    message = f"You are a controversial Twitter content creator that creates viral tweets with lots of likes and retweets. Create a tweet about '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users or tools and use a maximum of two emojis."
    return send_chat_gpt_message(message)


def generate_hyperbole_tweets_for_topic(topic):
    message = f"You are a Twitter content creator that creates viral tweets with lots of likes and retweets. You use emotive and hyperbolic language. Create a tweet about '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users or tools and use a maximum of two emojis."
    return send_chat_gpt_message(message)


def generate_advice_tweets_for_topic(topic):
    message = f"You are a Twitter content creator that creates viral tweets with lots of likes and retweets. You give advice using emotive and hyperbolic language. Create a tweet about '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users or tools and use a maximum of two emojis."
    return send_chat_gpt_message(message)


def rewrite_post_in_brand_voice(brand_voice, tweet):
    message = f"You are a social media content creator. You manage people's social media profiles and have been asked to come up with tweets that your client should tweet. Your client has given you the following tweet and wants it to be rewritten in a {brand_voice} brand voice. Don't include any emoji's. Here is the tweet: {tweet}.  Return nothing but the new tweet."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))
