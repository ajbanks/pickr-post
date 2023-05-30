from datetime import datetime, timedelta
from typing import List

import pandas as pd
import praw
import snscrape.modules.twitter as sntwitter

from bs4 import BeautifulSoup

from pickr.utils import normalise_tweet, lang


reddit = praw.Reddit(
    client_id="RxpU8nuSs_6RNQ",
    client_secret="Bt58INZOgAGPHbFSGYwLX2L-wBQ",  # password='$Ferrari94',
    user_agent="Alexander Joseph",
)  # , username='techinnovator')

business_subreddits = [
    "startups",
    "Kickstarter",
    "entrepreneur",
    "venturecapital",
    "marketing",
]
tech_subreddits = ["techolitics", "technology", "tech", "realtech", "Futurology"]
finance_subreddits = [
    "wallstreetbets",
    "stocks",
    "trading",
    "bitcoin",
    "BitcoinMarkets",
    "CryptoMarkets",
]
all_subreddits = business_subreddits + tech_subreddits + finance_subreddits


def search_subreddit_for_term(subreddit_string, search_term, time_filter="week"):
    output_rows = []
    for submission in reddit.subreddit(subreddit_string).search(
        search_term, time_filter=time_filter
    ):
        title = submission.title
        link = submission.url
        author = submission.author_fullname
        score = submission.score
        created = datetime.utcfromtimestamp(int(submission.created))
        body = submission.selftext
        output_dict = {
            "author": author,
            "title": title,
            "body": body,
            "score": score,
            "created_at": created,
            "link": link,
        }
        output_rows.append(output_dict)

    reddit_df = pd.DataFrame(output_rows)
    reddit_df["title"] = reddit_df["title"].apply(
        lambda text: BeautifulSoup(text, "html.parser").get_text()
    )
    reddit_df["body"] = reddit_df["body"].apply(
        lambda text: BeautifulSoup(text, "html.parser").get_text()
    )
    reddit_df["text"] = reddit_df["title"] + reddit_df["body"]
    reddit_df["clean_text"] = reddit_df["text"].apply(normalise_tweet)

    return reddit_df


def get_hot_submissions_from_subreddit_list(subreddit_list):
    post_rows = []
    for subreddit_string in subreddit_list:
        post_rows += get_hot_submissions(reddit.subreddit(subreddit_string))

    reddit_df = pd.DataFrame(post_rows)
    reddit_df["title"] = reddit_df["title"].apply(
        lambda text: BeautifulSoup(text, "html.parser").get_text()
    )
    reddit_df["body"] = reddit_df["body"].apply(
        lambda text: BeautifulSoup(text, "html.parser").get_text()
    )
    reddit_df["text"] = reddit_df["title"] + reddit_df["body"]
    reddit_df["clean_text"] = reddit_df["text"].apply(normalise_tweet)
    reddit_df["lang"] = reddit_df["clean_text"].apply(lang)
    reddit_df = reddit_df[reddit_df["lang"] == "en"]
    return reddit_df


def get_hot_submissions(subreddit):
    post_rows = []
    comments = []
    # assuming you run this script every hour
    ten_days_ago = datetime.utcnow() - timedelta(days=30)

    for submission in subreddit.hot(limit=1000):
        title = submission.title
        link = submission.url
        # author = submission.author_fullname
        score = submission.score
        created = datetime.utcfromtimestamp(int(submission.created))
        body = submission.selftext
        output_dict = {
            "title": title,
            "body": body,
            "score": score,
            "created_at": created,
            "link": link,
        }
        if created >= ten_days_ago:
            output_dict = {
                "title": title,
                "body": body,
                "score": score,
                "created_at": created,
                "link": link,
            }
            post_rows.append(output_dict)

    return post_rows


def find_subreddits(search_terms):
    found_subreddits = []
    subreddits = reddit.subreddits
    for term in search_terms:
        found_subreddits += subreddits.search_by_name(term, include_nsfw=False)
    return [s.display_name for s in found_subreddits]


def fetch_tweets_from_search_sns(
    name: str, search_terms: List[str], max_tweets: int = 100
) -> pd.DataFrame:

    query_tweets_dict = {}
    all_tweets = []
    for term in search_terms:
        print(term)
        query_tweets_dict[term] = []
        for i, tweet in enumerate(sntwitter.TwitterSearchScraper(term).get_items()):
            query_tweets_dict[term].append(tweet)
            all_tweets.append(tweet)
            if i > max_tweets:
                print(i)
                break
    # all_tweets = query_tweets_dict[search_terms[0]]+query_tweets_dict[search_terms[1]]+query_tweets_dict[search_terms[2]]
    all_tweets_content = [
        (
            t.id,
            t.username,
            t.date,
            t.rawContent,
            t.replyCount,
            t.quoteCount,
            t.retweetCount,
            t.likeCount,
            t.user.followersCount,
            t.user.followersCount,
            t.url,
        )
        for t in all_tweets
    ]
    cols = [
        "id",
        "username",
        "created_at",
        "text",
        "reply_count",
        "quote_count",
        "retweets",
        "likes",
        "followers_count",
        "followers_count",
        "url",
    ]
    tweets_df = pd.DataFrame(data=all_tweets_content, columns=cols)
    tweets_df["clean_text"] = tweets_df["text"].apply(normalise_tweet)
    filename = name + ".csv"
    tweets_df.to_csv(filename, index=False)
    return tweets_df
