import pandas as pd
from datetime import datetime
import tweepy

# from .models import db, Topic, ModeledTopic, Tweet, PickrUser, GeneratedPost, Niche

TWITTER_USERS_CSV = ""
AUTO_DM_MESSAGE = """Hi!. I can see you're building your x following. Get help here pickrsocial.com"""

class X_Caller:

    def __init__(self):
        self.client = self.create_client()




    def create_client(self):
        return  tweepy.Client(
        bearer_token=app.config["TWITTER_BEARER_TOKEN"],
        consumer_key=app.config["TWITTER_CLIENT_ID"],
        consumer_secret=app.config["TWITTER_CLIENT_SECRET"],
        access_token=app.config["TWITTER_ACCESS_TOKEN"],
        access_token_secret=app.config["TWITTER_ACCESS_TOKEN_SECRET"],
        wait_on_rate_limit=True,
    )


    def auto_dm(self, user_id, message):
        return self.client.create_direct_message(participant_id=user_id, text=message, user_auth=True)

    def get_tweets_for_tone_matching(self, user_twitter_id, max_results=30):

        tweets = ""

        response = self.client.get_users_tweets(user_twitter_id, max_results=max_results, exclude=["retweets"])

        # if there isn't enough tweet examples then try again ,this time including retweets
        if response.data is not None and len(response.data) > 10:
            tweets = "\n\n public statement example: \n".join(
                [status.text for status in response.data])
        else:
            response = client.get_users_tweets(user_twitter_id, max_results=max_results)
            if response.data is not None:
                tweets = "\n\n public statement example: \n".join(
                    [status.text for status in response.data])

        return tweets


    def return_twitterid(self, screen_name):
        twitterid = self.client.get_user(username=screen_name)
        return twitterid.data.id


    def is_x_bio_valid(self, bio):
        valid_terms = ["marketing", "marketer", "seo", "advertising", "content", "writer", "entrepreneur", "fitness", "muscle", "course", "startup", "saas", "diet"]

        for term in valid_terms:

            if term in bio:
                return True

        return False

    def dm_next_person_in_csv(self):

        dm_df = pd.read_csv(TWITTER_USERS_CSV, header=0)

        for i in range(len(dm_df)):

            if dm_df["been_messaged"].values[i] == 1:
                continue

            elif self.is_x_bio_valid(dm_df["Bio"].values[i]):
                dm_df["been_messaged"].values[i] = 1
                user_id = dm_df["User Id"].values[i]
                self.auto_dm(user_id, AUTO_DM_MESSAGE)

                break

        dm_df.to_csv(TWITTER_USERS_CSV)






