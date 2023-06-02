"""Mian function to run topic extraction from"""

import csv
import random
import pickle
import json
import time

from datetime import datetime

import pandas as pd

from pickr.topic.topic import build_subtopic_model
from pickr.twitter import twitter
from pickr.frontend import sheets


def post_fetch_topic_fetch(schedule_path, source, max_posts=10000, max_attempts=2):
    # Load scheduel csv
    schedule_df = pd.read_csv(schedule_path)
    date_str = datetime.now().strftime("%Y-%m-%d")

    print("Iterating through users")
    for index, row in schedule_df.iterrows():
        email = row["email"]
        username = row["twitter handle"]

        keywords = json.loads(row["keywords"])
        print("username", username)

        # try and load posts from file , otherwise retrieve from reddit
        path = (
            "data/" + "_".join(keywords)[:10] + "_" + date_str + "_" + source + ".csv"
        )
        pickle_path = (
            "data/" + "_".join(keywords)[:10] + "_" + date_str + "_sorted_topics.pickle"
        )

        try:
            with open(pickle_path, "rb") as f:
                sorted_topics = pickle.load(f)
            print("loaded data from file for ", source)
        except:
            attempts = 0
            while attempts < max_attempts:
                try:
                    print("data not on file, gettng from twitter")
                    try:
                        posts_df = pd.read_csv(path)
                    except:
                        if source == "twitter":
                            posts_df = twitter.fetch_tweets_from_search_sns(  # TODO put this in a try catch with a while loop
                                "temp", keywords, max_tweets=1000
                            )
                        elif source == "reddit":
                            print("data not on file, gettng from reddit")
                            subreddits_list = twitter.find_subreddits(keywords)
                            print("num subreddits: ", len(subreddits_list))
                            if len(subreddits_list) > 80:
                                random.shuffle(subreddits_list)
                                subreddits_list = subreddits_list[:80]
                                print("shortening number of subreddits")
                                print(subreddits_list)
                            posts_df = twitter.get_hot_submissions_from_subreddit_list(
                                subreddits_list
                            )
                            if len(posts_df) > max_posts:
                                posts_df = posts_df.sample(max_posts)
                            posts_df.to_csv(path, index=False)
                except Exception as e:
                    time.sleep(120)
                    attempts += 1
                    print("attempts", attempts, e)
                break

            print("number of posts", len(posts_df))
            # get topics for this user using the posts
            print("building topic model")

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
                    if len(sorted_topics) == 0:
                        print("no topcis left for ", email)
                        continue
                    # save sorted topics
                    print("saving topic list to file")
                    with open(
                        pickle_path,
                        "wb",
                    ) as handle:
                        pickle.dump(
                            sorted_topics, handle, protocol=pickle.HIGHEST_PROTOCOL
                        )
                    with open(
                        str(username) + ".pickle",
                        "wb",
                    ) as handle:
                        pickle.dump(
                            sorted_topics, handle, protocol=pickle.HIGHEST_PROTOCOL
                        )
                except Exception as e:
                    time.sleep(60)
                    attempts += 1
                    print("attempts", attempts, e)
                break

        # create google sheet as output
        print("creating excel sheet")
        attempts = 0
        while attempts < max_attempts:
            try:
                sheet_url = sheets.create_sheet(  # TODO put this in a try catch with a while loop
                    username, sorted_topics, source, max_topics=13
                )
                print(sheet_url)
                # save output URL to file
                with open("data/sheet_output.csv", "a") as csvfile:
                    writer = csv.writer(csvfile, delimiter=",")
                    writer.writerow([date_str, username, email, sheet_url])
            except Exception as e:
                time.sleep(60)
                attempts += 1
                print("attempts", attempts, e)
                continue
            break

    print("Done")


if __name__ == "__main__":
    post_fetch_topic_fetch("data/schedule.csv", "twitter")
