import pandas as pd
import logging
from datetime import datetime
import tweepy
import time
from flask import current_app as app
from typing import Union, List
import emoji
import nltk
from sqlalchemy import exc, insert
import re
from topic_model.util import normalise_tweet, parse_html
from .models import (
    db,
    Niche, ModeledTopic, GeneratedPost,
    Tweet,TwitterTerm,
    tweet_modeled_topic_assoc
)

log = logging.getLogger(__name__)
TWITTER_USERS_CSV = "data/all_competitor_followers.csv"
AUTO_DM_MESSAGE = """Hi!. I can see you're building your X following.

I'd love to help you build your audience.

I've built a bespoke tool that analyses the type of content your target audience loves, and then generates 
human-like viral tweets for you based on this analysis. More followers = more opportunities.
We're making it available free for 14 days as we are in Beta testing. Interested?

pickrsocial.com

"""


class X_Caller:

    def __init__(self):
        self.client = self.create_client()

    def create_client(self):
        return tweepy.Client(
            bearer_token=app.config["TWITTER_BEARER_TOKEN"],
            consumer_key=app.config["TWITTER_CLIENT_ID"],
            consumer_secret=app.config["TWITTER_CLIENT_SECRET"],
            access_token=app.config["TWITTER_ACCESS_TOKEN"],
            access_token_secret=app.config["TWITTER_ACCESS_TOKEN_SECRET"],
            wait_on_rate_limit=True,
        )

    def auto_dm(self, user_id, message):

        dm_client = tweepy.Client(
            consumer_key=app.config["TWITTER_API_KEY"],
            consumer_secret=app.config["TWITTER_API_KEY_SECRET"],
            access_token=app.config["TWITTER_OAUTH_TOKEN"],
            access_token_secret=app.config["TWITTER_OAUTH_TOKEN_SECRET"],
            wait_on_rate_limit=True,
        )
        return dm_client.create_direct_message(participant_id=user_id, text=message, user_auth=True)

    def get_tweets_for_tone_matching(self, user_twitter_id, max_results=30):

        tweets = ""

        response = self.client.get_users_tweets(user_twitter_id, max_results=max_results, exclude=["retweets"])

        # if there isn't enough tweet examples then try again ,this time including retweets
        if response.data is not None and len(response.data) > 10:
            tweets = "\n\n public statement example: \n".join(
                [status.text for status in response.data])

        return tweets

    def return_twitterid(self, screen_name):
        twitterid = self.client.get_user(username=screen_name)
        return twitterid.data.id

    def is_x_bio_valid(self, bio):
        valid_terms = ["marketing", "marketer", "seo", "advertising", "content", "creator", "writer", "entrepreneur",
                       "fitness", "muscle", "course", "startup", "saas", "diet"]

        for term in valid_terms:

            if term in bio.lower():
                return True

        return False

    def send_marketing_dms(self, number_dms=5):
        """
            5 requests / 15 mins PER USER
            500 requests / 24 hours PER USER

        """

        for i in range(number_dms):
            self.dm_next_person_in_csv()
            time.sleep(180)

    def post_tweet(self, tweet: str):
        return self.client.create_tweet(text=tweet)

    def clean_tweet_response(self, response):
        """
        Converts a tweepy search tweets repsonse into a list of dictionaries formatted to be compatible with our db

        :param response:
        :return: tweet_dicts : List
        """
        tweet_dicts = []

        for tweet_object in response.data:
            post_dict = {}
            post_dict["id"] = tweet_object['id']
            post_dict["text"] = tweet_object['text']
            post_dict["published_at"] = tweet_object['created_at']
            post_dict["author_id"] = tweet_object['author_id']
            post_dict["retweets"] = tweet_object.public_metrics['retweet_count']
            post_dict["likes"] = tweet_object.public_metrics['like_count']

            tweet_dicts.append(post_dict)


        return tweet_dicts

    def search_tweets(self, search_term, max_results=100):
        """Search tweets on twitter from the last 7 days using search term """

        """
        [attachments,author_id,card_uri,context_annotations,conversation_id,created_at,
        edit_controls,edit_history_tweet_ids,entities,geo,id,in_reply_to_user_id,lang,
        non_public_metrics,note_tweet,organic_metrics,possibly_sensitive,promoted_metrics,
        public_metrics,referenced_tweets,reply_settings,source,text,withheld]
        """

        # This endpoint/method returns Tweets from the last seven days
        max_results = min(100, max_results)
        response = self.client.search_recent_tweets(search_term, tweet_fields=['created_at', 'public_metrics', 'author_id'], max_results=max_results)
        # The method returns a Response object, a named tuple with data, includes,
        # errors, and meta fields

        # The data field of the Response returned is a list of Tweets that need to be reformatted
        tweets = self.clean_tweet_response(response)

        return tweets

    def dm_next_person_in_csv(self):

        dm_df = pd.read_csv(TWITTER_USERS_CSV, header=0)

        for i in range(len(dm_df)):

            if dm_df["been_messaged"].values[i] == 1:
                continue

            elif self.is_x_bio_valid(str(dm_df["Bio"].values[i])):

                dm_df["been_messaged"].values[i] = 1
                user_id = dm_df["User Id"].values[i]
                resp = self.auto_dm(user_id, AUTO_DM_MESSAGE)
                dm_df.to_csv(TWITTER_USERS_CSV)
                return resp

        return "FALSE"


def write_twitter_posts(posts: List[dict]) -> int:
    num_written = 0
    for post in posts:
        record = (
            db.session.query(Tweet)
            .filter(Tweet.id == post["id"])
            .first()
        )
        if record is None:
            record = Tweet(**post)
            try:
                db.session.add(record)
            except exc.SQLAlchemyError as e:
                db.session.rollback()
                log.error(f"Error writing twitter post: {e}")
            else:
                db.session.commit()
                num_written += 1
    return num_written


def write_generated_posts(generated_posts: List[dict]) -> None:
    """
    """
    for post in generated_posts:
        record = GeneratedPost(**post)
        try:
            db.session.add(record)
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            log.error(f"Database error occurred: {e}")
        else:
            db.session.commit()


def write_modeled_topic_with_twitter_posts(
        topic: dict,
        post_ids: List[int]
) -> None:
    '''
    Save a modeled topic to the database and associate twitter IDs
    with the topic.
    '''
    modeled_topic = ModeledTopic(**topic)
    try:
        db.session.add(modeled_topic)
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        log.error(f"Database error occured: {e}")
    else:
        db.session.commit()

    try:
        print('pids to execute: ', post_ids)
        db.session.execute(
            insert(tweet_modeled_topic_assoc),
            [
                {"tweet_id": pid, "modeled_topic_id": modeled_topic.id}
                for pid in post_ids
            ],
        )
        print('pids done: ', post_ids)
    except exc.SQLAlchemyError as e:
        db.session.rollback()
        log.error(f"Database error occured: {e}")
    else:
        db.session.commit()


def clean_tweet(tweet: str) -> str:
    words = set(nltk.corpus.words.words())
    tweet = re.sub("@[A-Za-z0-9]+","",tweet) #Remove @ sign
    tweet = re.sub(r"(?:\@|http?\://|https?\://|www)\S+", "", tweet) #Remove http links
    tweet = " ".join(tweet.split())
    tweet = emoji.replace_emoji(tweet, replace='')
    tweet = tweet.replace("#", "").replace("_", " ") #Remove hashtag sign but keep the text
    tweet = " ".join(w for w in nltk.wordpunct_tokenize(tweet) \
         if w.lower() in words or not w.isalpha())
    return tweet


def write_twitter_modeled_overview(topic_overviews: List[dict]) -> None:
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


def get_twitter_posts_from_term(search_term: str, num_posts) -> List[dict]:
    x_caller = X_Caller()
    num_posts = min(100, num_posts)
    tweet_dicts = x_caller.search_tweets(search_term, max_results=num_posts)
    return tweet_dicts

