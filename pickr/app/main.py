"""Mian function to run topic extraction from"""

import random
import pickle
import json

from datetime import datetime

import pandas as pd

from pickr.topic.topic import build_subtopic_model
from pickr.twitter import twitter
from pickr.frontend import sheets


def post_fetch_topic_fetch(schedule_path, source, max_posts=10000):
    # Load scheduel csv
    schedule_df = pd.read_csv(schedule_path)
    date_str = datetime.now().strftime("%Y-%m-%d")

    print("Iterating through users")
    for index, row in schedule_df.iterrows():
        email = row["email"]
        keywords = json.loads(row["keywords"])
        print("email", email)

        # try and load posts from file , otherwise retrieve from reddit
        path = (
            "data/" + "_".join(keywords)[:10] + "_" + date_str + "_" + source + ".csv"
        )
        pickle_path = "data/" + "_".join(keywords)[:10] + "_" + date_str+ "_sorted_topics.pickle"
        try:
            with open(pickle_path, 'rb') as f:
                sorted_topics = pickle.load(f)
            print("loaded data from file for ", source)
        except:
            print("data not on file, gettng from twitter")
            if source == "twitter":
                posts_df = twitter.fetch_tweets_from_search_sns(
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

            posts_df.to_csv(path)

            print("number of posts", len(posts_df))
            # get topics for this user using the posts
            print("building topic model")
            topic_model, topic_info = build_subtopic_model(posts_df, source)
            sorted_topics = [
                v
                for k, v in sorted(
                    topic_info.items(), reverse=True, key=lambda item: item[1].size
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
                pickle.dump(sorted_topics, handle, protocol=pickle.HIGHEST_PROTOCOL)
            with open(
                str(email) + '.pickle',
                "wb",
            ) as handle:
                pickle.dump(sorted_topics, handle, protocol=pickle.HIGHEST_PROTOCOL)

        # create output file
        print("creating excel sheet")
        sheets.create_sheet(email, sorted_topics, source, max_topics=13)
    print("Done")


def post_batch_topic_fetch(schedule_path, max_posts=10000):
    # Load scheduel csv
    schedule_df = pd.read_csv(schedule_path)
    all_keywords = schedule_df["keywords"].apply(json.loads).tolist()
    unique_keywords = list(set([item for sublist in all_keywords for item in sublist]))
    print("num keywords", len(unique_keywords))
    print(unique_keywords)

    print("Getting keyword posts")
    # for each keyword get latest posts
    date_str = datetime.now().strftime("%Y-%m-%d")

    for keyword in unique_keywords:
        print("keyword", keyword)
        # get posts for keyword
        subreddits_list = twitter.find_subreddits([keyword])
        print("num subreddits: ", len(subreddits_list))
        print(subreddits_list)
        random.shuffle(subreddits_list)
        subreddits_list = subreddits_list[:5]
        print(subreddits_list)
        posts_df = twitter.get_hot_submissions_from_subreddit_list(subreddits_list)
        # save posts
        posts_df.to_csv("data/" + keyword + "_" + date_str + ".csv", index=False)

    print("Building topic models")
    for index, row in schedule_df.iterrows():
        email = row["email"]
        keywords = json.loads(row["keywords"])
        print(email, keywords)
        # get all posts for this user
        df_list = []
        for keyword in keywords:
            df_list.append(pd.read_csv("data/" + keyword + "_" + date_str + ".csv"))

        user_posts_df = pd.concat(df_list)
        if len(user_posts_df) == 0:
            continue

        if len(user_posts_df) > max_posts:
            user_posts_df = user_posts_df.sample(max_posts)

        # get topics for this user using the posts
        topic_model, topic_info = build_subtopic_model(user_posts_df)
        sorted_topics = [
            v
            for k, v in sorted(
                topic_info.items(), reverse=True, key=lambda item: item[1].size
            )
        ]
        # save sorted topics
        with open(
            "data/" + email + "_" + date_str + "_sorted_topics.pickle", "wb"
        ) as handle:
            pickle.dump(sorted_topics, handle, protocol=pickle.HIGHEST_PROTOCOL)

        # create output file
        sheets.create_sheet_reddit(email, sorted_topics, max_topics=13)


if __name__ == "__main__":
    post_fetch_topic_fetch("data/schedule.csv", "twitter")
