import random
import json
import time
import logging

from datetime import datetime
import pandas as pd

# logging configurations
logging.basicConfig(level=logging.INFO)

from pickr.topic.topic import build_subtopic_model
from pickr.twitter import twitter


def post_fetch_topic_fetch(
    schedule_path: str, source: str, max_posts: int = 10000, max_attempts: int = 2
):
    """
    From the schedule input, we try to get topic information, construct the generated posts,
    and the trend as well
    """
    # Load schedule csv
    schedule_df = pd.read_csv(schedule_path)
    datetime.now().strftime("%Y-%m-%d")
    output = []
    logging.info("Iterating through users")
    for index, row in schedule_df[:1].iterrows():
        row["email"]
        username = row["twitter handle"]
        username = username.lower()
        if username[0] == "@":
            username = username[1:]

        keywords = json.loads(row["keywords"])
        logging.info(f"username - {username}")
        if source == "twitter":
            posts_df = twitter.fetch_tweets_from_search_sns(  # TODO put this in a try catch with a while loop
                "temp", keywords, max_tweets=max_posts
            )
        elif source == "reddit":
            logging.info("Data not on file, gettng from reddit")
            subreddits_list = twitter.find_subreddits(keywords)
            logging.info(f"num subreddits: {len(subreddits_list)}")
            if len(subreddits_list) > 80:
                # shuffle the subreddits - not sure why we are doing this
                random.shuffle(subreddits_list)
                logging.info("shortening number of subreddits")
                subreddits_list = subreddits_list[:80]
                logging.info(
                    f"The final subreddits we find for the keywords are as follows: {subreddits_list}"
                )
                posts_df = twitter.get_hot_submissions_from_subreddit_list(
                    subreddits_list
                )
                # limit the number of max posts we wish to have
                if len(posts_df) > max_posts:
                    posts_df = posts_df.sample(max_posts)
        attempts = 0
        while attempts < max_attempts:
            try:
                topic_model, topic_info = build_subtopic_model(
                    posts_df, source
                )  # TODO put this in a try catch with a while loop
                sorted_topics = [
                    v
                    for k, v in sorted(
                        topic_info.items(),
                        reverse=True,
                        key=lambda item: item[1].size,
                    )
                ]
                sorted_topics.append(subreddits_list)
                output.append([posts_df, sorted_topics])
            except Exception as e:
                time.sleep(60)
                attempts += 1
                print("attempts", attempts, e)
    return output


if __name__ == "__main__":
    output = post_fetch_topic_fetch("~/Desktop/data/schedule.csv", "reddit")
