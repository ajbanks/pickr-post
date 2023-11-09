"""
Module to compute topic info
"""
import string
import os
import math
import uuid
from typing import List, Tuple
from datetime import datetime, timedelta
import re

import backoff
import openai
from openai.error import OpenAIError
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import CountVectorizer
# from sklearn.metrics.pairwise import cosine_similarity

RANDOM_STATE = 42

openai.api_key = os.getenv("OPENAI_API_KEY")
OPEN_AI_MODEL = "gpt-4"
STRIP_CHARS = "'" + '"' + " \t\n"
BRAND_VOICES = [
    "Playful and Youthful",
    "Professional and Authoritative",
    "Inspirational and Empowering",
    "Friendly and Supportive",
    "Bold and Innovative",
]
with open('tweet_examples.txt', 'r') as read_file:
    TWEET_EXAMPLES = read_file.read()
    

def build_subtopic_model(texts: List[str], reduce_topics=False):
    '''
    Take a list of document text and returns trained BERTopic model.
    '''
    # local import because this import is slow
    from bertopic import BERTopic
    from bertopic.representation import KeyBERTInspired
    from hdbscan import HDBSCAN
    from sentence_transformers import SentenceTransformer

    vectorizer_model = CountVectorizer(stop_words="english")
    sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
    representation_model = KeyBERTInspired()
    hdbscan_model = HDBSCAN(
        min_cluster_size=3,
        min_samples=1,
        metric='euclidean',
        cluster_selection_method='eom',
        prediction_data=True
    )
    topic_model = BERTopic(
        vectorizer_model=vectorizer_model,
        n_gram_range=(1, 2),
        embedding_model=sentence_model,
        hdbscan_model=hdbscan_model,
        representation_model=representation_model
    )

    embeddings = sentence_model.encode(texts, show_progress_bar=False)
    topic_model.fit_transform(texts, embeddings)
    if reduce_topics:
        topic_model.reduce_topics(texts, nr_topics='auto')
    return topic_model


def analyze_topics(
        topics: List[int],
        probs: List[float],
        topic_keywords: List[List[str]],
        topic_rep_docs: List[List[str]],
        posts: List[dict],
        source: str,
        min_date=None,
        trend_prev_days=14,
):
    '''
    Analyze the trend and rank of each topic given a trained BERTopic model and
    the posts it was trained on.
    Trends are ranked from 0-5, with 0 the highest.

    @topics: topics[i] is the BERTopic ID of the posts[i].
    @probs: probs[i] is the probability of posts[i] belonging to topics[i].
    @param source: "reddit" or "twitter"
    '''
    valid_topics = filter_topics(topics, probs)

    posts_df = pd.DataFrame(posts)
    posts_df["date"] = posts_df["created_at"].apply(lambda x: x.date())
    posts_df["probs"] = probs

    topics_list = []
    for topic_id in valid_topics:
        # get all tweets in this topic and put them in a df
        topic_posts_idx = [
            i for i, t in enumerate(topics) if t == topic_id
        ]
        topic_df = posts_df.iloc[topic_posts_idx]
        topic_df.sort_values(["probs"], ascending=False, inplace=True)
        num_posts = len(topic_df)

        # Get daily stats and trend type of the topic
        num_likes, topic_df_grp = get_topic_stats(topic_df, source)
        date_thres = datetime.now() - timedelta(days=trend_prev_days)
        recent_posts = topic_df_grp[topic_df_grp["date"] >= date_thres.date()]

        if len(recent_posts) == 0:
            rank = 5
        elif source == "twitter":
            rank = trend_type(recent_posts["likes"].values)
        elif source == "reddit":
            rank = trend_type(recent_posts["score"].values)
        else:
            rank = 5

        post_ids = topic_df["id"].apply(str).tolist()
        topics_list.append({
            "topic_id": topic_id,
            "topic_keywords": topic_keywords[topic_id+1],  # +1 offset is used because first topic is the noise topic
            "topic_rep_docs": topic_rep_docs[topic_id+1],
            "size": num_posts,
            "likes": num_likes,
            "rank": rank,
            "post_ids": post_ids,
        })

    # sort topics by trend rank then by number of likes
    return sorted(topics_list, key=lambda t: (t["rank"], -t["likes"]))


def generate_topic_overview(
        docs: List[str],
        topic_keywords: List[str],
        topic_rep_docs: List[str],
        niche_title: str,
) -> Tuple[str, str]:
    '''
    Generate topic labels and description with GPT.
    Return empty strings if GPT determines the topic is not good.
    '''

    # TODO(meiji163) change this to count tokens.
    # the limit is 4097 tokens for body + response
    topic_documents = "\n\n".join([
        "Message:    " + d[:1000]
        for d in topic_rep_docs[:4]
    ])
    # if not is_valid_topic_gpt(body):
    #     return "", ""
    topic_label, topic_desc = get_label_and_description(topic_documents, topic_keywords)
    if not is_topic_relevant_gpt(niche_title, topic_desc):
        return "", ""
    return topic_label, topic_desc


def get_topic_stats(df, source):
    if source == "twitter":
        return (
            int(df["likes"].sum()),
            df.groupby("date", as_index=False).agg(
                {"likes": "sum", "url": "count"}
            ),
        )
    elif source == "reddit":
        return (
            int(df["score"].sum()),
            df.groupby("date", as_index=False).agg(
                {"score": "sum", "url": "count"}
            ),
        )


def is_valid_topic_gpt(body: str) -> bool:
    resp = send_chat_gpt_message(
        valid_topic_test(body),
        temperature=0.2
    )
    return resp.lower().strip(string.punctuation) == "yes"


def is_topic_relevant_gpt(niche: str, topic: str) -> bool:
    resp = send_chat_gpt_message(
        is_topic_related_to_niche(topic, niche),
        temperature=0.2
    )
    return resp.lower().strip(string.punctuation) == "yes"

def is_topic_informational_gpt(text) -> bool:
    resp = send_chat_gpt_message(
        is_informational_post(text),
        temperature=0.2
    )
    return resp.lower().strip(string.punctuation) == "yes"
    


@backoff.on_exception(backoff.expo, OpenAIError)
def get_label_and_description(topic_documents, topic_keywords):
    topic_label = send_chat_gpt_message(create_label_prompt(topic_documents, topic_keywords), temperature=0.2)
    try:
        topic_label = topic_label.split('topic:')[1].strip(STRIP_CHARS)
    except Exception:
        pass
    topic_desc = send_chat_gpt_message(create_summary_prompt(topic_documents, topic_keywords), temperature=0.2)
    try:
        topic_desc = topic_desc.split('topic:')[1].strip(STRIP_CHARS)
        topic_desc = send_chat_gpt_message(create_summarise_topic_summary_prompt(topic_documents, topic_keywords), temperature=0.2)
        topic_desc = topic_desc.split('topic:')[1].strip(STRIP_CHARS)
    except Exception:
        pass
    return topic_label, topic_desc


def filter_topics(
        topics: List[int],
        probs: List[float],
        min_avg_prob=0.5
) -> List[int]:
    '''
    Given output of BERTopic model, filter topic int IDs
    by avg. document probabilty.
    '''
    n_topics = max(topics) + 1
    topic_avg_prob = [0] * n_topics
    topic_count = [0] * n_topics

    for topic_id, pr in zip(topics, probs):
        if topic_id == -1:
            # in BERTopic -1 is the "catchall topic" which we filter out
            continue
        topic_count[topic_id] += 1
        topic_avg_prob[topic_id] += pr
    for i, pr in enumerate(topic_avg_prob):
        if topic_count[i] > 0:
            topic_avg_prob[i] = pr / topic_count[i]

    return list(filter(
        lambda i: topic_avg_prob[i] > min_avg_prob,
        range(0, n_topics)
    ))


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
    n = len(points)
    if n < 3:
        return 5
    x = np.arange(0, n)
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


@backoff.on_exception(backoff.expo, OpenAIError)
def send_chat_gpt_message(message, temperature=0.8):
    # TODO: check the temperature is correct
    return (
        openai.ChatCompletion.create(
            model=OPEN_AI_MODEL,
            messages=[{"role": "user", "content": message}],
            temperature=temperature,
        )
        .choices[0]
        .message.content
    )


def rewrite_tweets_in_brand_voices(tweet_list):
    """rewrite tweets in different brand voices"""
    new_tweets = []

    for tweet in tweet_list:
        for brand_voice in BRAND_VOICES:
            new_tweets.append(rewrite_post_in_brand_voice(brand_voice, tweet))

    return tweet_list + new_tweets


# TODO(meiji163) Use the BERTopic keywords for generation too
def generate_tweets_for_topic(
        num_tweets,
        topic_label,
        topic_summary,
        num_topics_from_topic_label=5
):
    """
    Take a topic label and query GPT for related topics,
    then generate tweets for each of those related topics.
    Returns (related_topics, generated_tweets)
    """
    num_tweets_per_tweet_type = math.ceil(
        (num_tweets / num_topics_from_topic_label) / 2
    )
    num_tweets_per_tweet_type = (
        1 if num_tweets_per_tweet_type <= 0 else num_tweets_per_tweet_type
    )

    generated_tweets = []
    
    for i in range(num_tweets):
        tweet = send_chat_gpt_message(generate_informative_tweet_for_topic_awesome_prompt(topic_label))
        if is_topic_informational_gpt(tweet):
            generated_tweets.append({
                "topic_label": topic_label,
                "information_type": "informative",
                "text": tweet,
            })

        tweet = send_chat_gpt_message(generate_informative_tweet_for_topic_awesome_prompt(topic_summary))
        if is_topic_informational_gpt(tweet):
            generated_tweets.append({
                "topic_label": topic_label,
                "information_type": "funny",
                "text": tweet,
            })

    return generated_tweets


def valid_topic_test(text):
    return f"You will answer my questions to the best of your ability and truthfully. Are the social media posts below about the same topic? Answer Yes or No. {text}"


def is_topic_related_to_niche(topic_label, niche_label):
    prompt_string = f"You will answer my questions to the best of your ability and truthfully. Is the topic descroption below related to {niche_label}? Answer Yes or No. \n\n '{topic_label}'"
    return prompt_string


def create_summarise_topic_summary_prompt(summary):
    return f"""
        You are excellent at creating concise and short descriptions that summarise the description of a topic. Your summarisations cover a maximum of two themes and are easy to to understand.
        I have a topic that has the following description: {summary}
        
        Based on the information above, please give a description of this topic that covers a maximum of two themes, in the following format:
        topic: <description>
        """

def create_summary_prompt(documents, keywords):
    return f"""
        You are excellent at creating concise and short descriptions that capture a maximum of two themes in a topic that is represented by a set of keywords and documents.
        I have a topic that is described by the following keywords: {keywords}
        In this topic, the following documents are a small but representative subset of all documents in the topic:
        {documents}
        
        Based on the information above, please give a description of this topic that covers a maximum of two themes, in the following format:
        topic: <description>
        """


def create_label_prompt(documents, keywords):
    return f"""
        You are excellent at creating concise and short labels that capture a maximum of two themes in a topic that is represented by a set of keywords and documents.
        I have a topic that contains the following documents: 
        {documents}
        The topic is described by the following keywords: {keywords}
        
        Based on the information above, extract a short topic label in the following format:
        topic: <topic label>
        """


def convert_chat_gpt_response_to_list(str_response):
    return [s.strip(STRIP_CHARS) for s in re.split("\n", str_response)]


def generate_tweet(text, topic_label):
    return f"You are a social media content creator. You write tweets that are thought provoking and authoritative. People learn alot from your tweets. I am going to show you a few tweets about the topic {topic_label}. I then want you to generate a new viral tweet. Do not mention any events, dates or company names. Here are the tweets: {text}"


def generate_related_topics(
    num_topics, topic_label
):  # TODO: this might only work for high level topics, check this
    message = f"You are a highly skilled social media content creator. You come up with viral topics to tweet about. Create {num_topics} topics to tweet about related to {topic_label}. Don't add any numbering to the topics and separate each topic with a new line character."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


# def generate_10_brand_voice_tweets_for_topic(brand_voice, topic):
#     return f"You are a social media content creator. You manage social media profiles and have been asked to come up with tweets that your client should tweet. Create 10 tweets related to {topic} written in a {brand_voice} brand voice. Don't add any numbering to the tweets and separate each tweet with a new line character."


def is_informational_post(post_text):
    return f"""
    
    You are excellent at answering questions accurately and determining whether a tweet is informational and sharing knowledge. I will give you a tweets and you will reply 'Yes' if the tweet is informational or 'No' if it is not:

    TWEET: {post_text}
    """


def generate_informative_tweet_for_topic_awesome_prompt(topic_summary):
    """Implementation: original_gpt4_awesome-chatgpt-prompts_3examples_tweet_generation_results.csv
    """
    message = f"I want you to act as a social media manager. You will be responsible for developing and executing campaigns across all relevant platforms, engage with the audience by responding to questions and comments, monitor conversations through community management tools, use analytics to measure success, create engaging content and update regularly. You manage social media profiles and have been asked to come up with a tweet that your client should tweet. I want you to read this topic summary, pick out an interesting topic and write a tweet about it. Use the topic summary to help you. Here is the topic summary: {topic_summary}. think step-by-step. Analyse the topic and identify its relevance to the audience. Then think of a good point that the audience should know. Then create the tweet. Don't mention any personal stories or situations from the past. Don't introduce the topic at the beginning of the tweet with words like 'exploring', 'diving', or 'unlock'. Don't mention any specific twitter users, or tools/resources. You aren't selling anything Don't include any emoji's. Here is a good example of a tweet: here are some tweet examples you can use as inspiration (don't directly copy the styles/formats: {TWEET_EXAMPLES}."
    return message


def generate_informative_tweet_for_topic(topic):
    message = f"You are an educational social media content creator. You manage social media profiles and have been asked to come up with a tweet that your client should tweet. Create a brief tweet that explains {topic}. Don't mention any specific twitter users, tools or resources. Don't include any emoji's. Write in the style of a 16 year old."
    return send_chat_gpt_message(message).strip(STRIP_CHARS)


def generate_funny_tweet_for_topic(topic):
    message = f"You are a satirical Twitter account. You post funny tweets about various different topics. Create a tweet about {topic}. Don't mention any specific twitter users or tools. Don't include any emoji's. write concisely."
    return send_chat_gpt_message(message).strip(STRIP_CHARS)


def generate_informative_tweet_for_topic_desc(topic_label, topic_desc):
    message = f"You are an educational social media content creator. You manage social media profiles and have been asked to come up with a tweet that your client should tweet. Create a brief tweet for the topic '{topic_label}' with the following description: {topic_desc}. \n\nDon't mention any specific twitter users, tools or resources. Don't include any emoji's. Write in the style of a 16 year old."
    return send_chat_gpt_message(message).strip(STRIP_CHARS)


def generate_funny_tweet_for_topic_desc(topic_label, topic_desc):
    message = f"You are a satirical Twitter account. You post funny tweets about various different topics. Create a tweet about the topic '{topic_label}' with the following description: {topic_desc}. \n\nDon't mention any specific twitter users or tools. Don't include any emoji's. write concisely."
    return send_chat_gpt_message(message).strip(STRIP_CHARS)


def generate_future_focused_tweet_for_topic(topic):
    message = f"You are a futurist social media content creator. You manage social media profiles and have been asked to come up with tweets that your client should tweet. Create a brief tweet that talks about the future of {topic} and how it will change over time. Don't mention any specific twitter users, tools or resources. Don't include any emoji's. Write in the style of a 16 year old"
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


def generate_past_focused_tweets_for_topic(num_tweets, topic):
    message = f"You are a historian social media content creator. You manage people's social media profiles and have been asked to come up with tweets that your client should tweet. Create {num_tweets} tweets that talks about the history of {topic} and how it changed over time. Don't mention any specific twitter users or tools. Don't include any emoji's. Don't add any numbering to the tweets and separate each tweet with a new line character."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))


def generate_controversial_tweets_for_topic(topic):
    message = f"You are a controversial Twitter content creator that creates viral tweets with lots of likes and retweets. Create a tweet the topic '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users or tools and use a maximum of two emojis."
    return send_chat_gpt_message(message)


def generate_hyperbole_tweets_for_topic(topic):
    message = f"You are a Twitter content creator that creates viral tweets with lots of likes and retweets. You use emotive and hyperbolic language. Create a tweet about '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users, tools or resources. Don't include any emoji's. Write in the style of a 16 year old"
    return send_chat_gpt_message(message)


def generate_advice_tweets_for_topic(topic):
    message = f"You are a Twitter content creator that creates viral tweets with lots of likes and retweets. You give advice using emotive and hyperbolic language. Create a tweet about '{topic}'. The tweet must be a maximum of 280 characters. Don't mention any specific twitter users or tools and use a maximum of two emojis."
    return send_chat_gpt_message(message)


def rewrite_post_in_brand_voice(brand_voice, tweet):
    message = f"You are a social media content creator. You manage people's social media profiles and have been asked to come up with tweets that your client should tweet. Your client has given you the following tweet and wants it to be rewritten in a {brand_voice} brand voice. Don't include any emoji's. Here is the tweet: {tweet}.  Return nothing but the new tweet."
    return convert_chat_gpt_response_to_list(send_chat_gpt_message(message))
