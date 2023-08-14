# Boilerplate
import sys
import os

sys.path.append("../../")

from typing import Tuple
from dotenv import load_dotenv
from tqdm import tqdm

# Standard boilerplate imports
import logging
import pandas as pd
import pandasql as ps  # allows the convenient use of SQLLike commands

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import exc

# Flask SQLAlchemy - import dimensional tables
from pickr_flask.models import (
    tweet_modeled_topic_assoc,
)

# Flask SQLAlchemy - import other tables
from pickr_flask.models import (
    TwitterUser,
)

# Pydantic model for model vaidation
# from model_validation import PickrValidation
# logging configurations
logging.basicConfig(level=logging.INFO)

# load database endpoint from the env file
# instead of having it hardcoded

load_dotenv()
db_uri = os.getenv("SQLALCHEMY_DATABASE_URI")
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
db = SQLAlchemy(app)

if not db_uri:
    logging.error("DB_URL environment variable is not set")
    exit(1)


def validate_and_convert_data(data: pd.DataFrame) -> pd.DataFrame:
    """
    Use pydantic to load and convert invalid strings within
    columns as necessary
    """
    valid_rows = []
    for index, row in tqdm(data.iterrows()):
        try:
            validated_data = PickrValidation(**row)
            valid_rows.append(validated_data.dict())
        except Exception as e:
            print(f"An exception: {e}")
    valid_df = pd.DataFrame(valid_rows)
    return valid_df


def load_data_from_csv(file_path: str) -> None:
    """
    Load data into pandas, then write to the postgres database

    Load data from CSV and insert into the table
    """
    df = pd.read_csv(file_path).drop(
        "followers_count.1", axis=1
    )  # remove the followers_count.1 as it is redundant
    df = df.drop_duplicates(subset=["id"])  # remove the same ids within the same file
    df = validate_and_convert_data(df)
    logging.info(f"We have validated the schema for {file_path}")
    # updating the tables
    logging.info("updating the user table")
    write_twitter_user_db(df)
    logging.info("updating the tweet table")


def load_data_from_pickle(file_path: str) -> None:
    """
    Primarily working with writing the Modeled topcis here
    Load data from CSV and insert into the table
    """
    df = pd.read_pickle(file_path)
    logging.info(f"Writing the data for the modeled topic for {file_path}")
    # updating the tables
    logging.info("updating the user table")
    return df


def sort_key(file_path: str) -> Tuple[str, str]:
    """
    Custom sorting key function.
    Sorts the file paths based on the topic and datetime string.
    """
    # Extract the topic and datetime from the file path
    file_name = file_path.stem  # Get the file name without the extension
    parts = file_name.split("_")
    # Find the topic by joining the first part(s) before the datetime
    topic = "_".join(parts[:-1])
    # Return a tuple with the topic and datetime as the sorting key
    return (topic, parts[-1])


def write_twitter_user(data: pd.DataFrame) -> None:
    """
    Writing to the postgres database for the users
    """
    try:
        with session.no_autoflush:
            # Completely temporary queries at the moment
            q1 = """SELECT id AS id,
            username AS username,
            username AS name,
            MAX(followers_count) AS followers,
            COUNT(text) as tweet_count,
            CURRENT_TIMESTAMP AS updated_at FROM data GROUP BY id, name"""

            # what is this query doing?
            q2 = """SELECT id,
            MAX(created_at) AS max_date,
            followers_count
            FROM data
            GROUP BY id"""

            main_dataframe = ps.sqldf(q1, locals())
            sub_dataframe = ps.sqldf(q2, locals())

            df = main_dataframe.merge(sub_dataframe)[
                [
                    "id",
                    "username",
                    "name",
                    "followers_count",
                    "tweet_count",
                    "updated_at",
                ]
            ]

            # write to the database
            for index, row in tqdm(df.iterrows()):
                # Query if the data is already in the table through checking with id
                record = (
                    session.query(TwitterUsers)
                    .filter(TwitterUsers.id == row["id"])
                    .first()
                )
                if record:
                    id = row["id"]
                    # if we find a record with the same id, then update as necessary
                    record.followers_count = row["followers_count"]
                    record.tweet_count = row["tweet_count"]
                    record.updated_at = row["updated_at"]
                    logging.info(f"Users - Updating for user {id}")
                else:
                    id = row["id"]
                    # else, we add in a new record representing the new user
                    record = TwitterUsers(**row)
                    logging.info(f"Users - Adding for user {id}")
                    session.add(record)

    except DatabaseError as e:
        logging.error("Database error occurred:")
        logging.error(f"error - {e}")

    # commit the dataframe to the sql table - ensure there are
    # rollback options
    try:
        session.commit()
        logging.info("Upsert successful!")
    except Exception as e:
        session.rollback()
        logging.info(f"rolling back changes - failed! - {e}")
    finally:
        session.close()


def write_twitter_tweets(data: pd.DataFrame) -> None:
    """
    Writing to the postgres database for the tweets
    """
    try:
        # with session.no_autoflush:
        with app.app_context():
            q3 = """
            SELECT id AS id,
            username AS username,
            text AS text,
            clean_text AS processed_text,
            created_at AS created_at,
            id AS author_id,
            retweets AS retweet_count,
            likes AS like_count,
            'ENG' AS lang,
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS retweet_id,
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS quote_id,
            CURRENT_TIMESTAMP AS updated_at
            from data
            """
            df = ps.sqldf(q3, locals())
            for index, row in tqdm(df.iterrows()):
                # Query if the data is already in the table through checking with id
                record = (
                    session.query(TwitterTweets)
                    .filter(TwitterTweets.id == row["id"])
                    .first()
                )
                if record:
                    # if we find a record with the same id, then update as necessary
                    id = row["id"]
                    record.retweet_count = row["retweet_count"]
                    record.like_count = row["like_count"]
                    record.updated_at = row["updated_at"]
                    logging.info(f"Tweets - updating for user {id}")
                else:
                    id = row["id"]
                    # else, we add in a new record representing the new user
                    record = TwitterTweets(**row)
                    logging.info(f"Tweets - We are adding new data for {id}")
                    session.add(record)

    except exc.DatabaseError as e:
        logging.error("Database error occurred:")
        logging.error(f"error - {e}")
    try:
        session.commit()
        logging.info("Upsert successful!")
    except Exception as e:
        logging.info(f"Input syntax error - {e}")
        session.rollback()
    finally:
        session.close()


def write_twitter_user_db(data: pd.DataFrame) -> None:
    """
    Writing to the postgres database for the users
    """
    with app.app_context():
        try:
            # with db.session.no_autoflush:
            # Completely temporary queries at the moment
            q1 = """SELECT id AS id,
            username AS username,
            username AS name,
            MAX(followers_count) AS followers,
            COUNT(text) as tweet_count,
            CURRENT_TIMESTAMP AS updated_at FROM data GROUP BY id, name"""

            # what is this query doing?
            q2 = """SELECT id,
            MAX(created_at) AS max_date,
            followers_count
            FROM data
            GROUP BY id"""

            main_dataframe = ps.sqldf(q1, locals())
            sub_dataframe = ps.sqldf(q2, locals())

            df = main_dataframe.merge(sub_dataframe)[
                [
                    "id",
                    "username",
                    "name",
                    "followers_count",
                    "tweet_count",
                    "updated_at",
                ]
            ]

            # write to the database
            for index, row in tqdm(df.iterrows()):
                # Query if the data is already in the table through checking with id
                record = (
                    db.session.query(TwitterUser)
                    .filter(TwitterUser.id == row["id"])
                    .first()
                )
                if record:
                    id = row["id"]
                    # if we find a record with the same id, then update as necessary
                    record.followers_count = row["followers_count"]
                    record.tweet_count = row["tweet_count"]
                    record.updated_at = row["updated_at"]
                    logging.info(f"Users - Updating for user {id}")
                else:
                    id = row["id"]
                    # else, we add in a new record representing the new user
                    record = TwitterUser(**row)
                    logging.info(f"Users - Adding for user {id}")
                    db.session.add(record)

            db.session.commit()
            logging.info("Upsert successful!")

        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()


def write_twitter_tweets_db(data: pd.DataFrame, modeled_topic_id: str) -> None:
    """
    Writing to the postgres database for the tweets
    """
    try:
        # with session.no_autoflush:
        with app.app_context():
            q3 = """
            SELECT id AS id,
            username AS username,
            text AS text,
            clean_text AS processed_text,
            created_at AS created_at,
            id AS author_id,
            retweets AS retweet_count,
            likes AS like_count,
            'ENG' AS lang,
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS retweet_id,
            ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS quote_id,
            CURRENT_TIMESTAMP AS updated_at
            from data
            """
            df = ps.sqldf(q3, locals())
            for index, row in tqdm(df.iterrows()):
                # Query if the data is already in the table through checking with id
                record = (
                    session.query(TwitterTweets)
                    .filter(TwitterTweets.id == row["id"])
                    .first()
                )
                if record:
                    # if we find a record with the same id, then update as necessary
                    id = row["id"]
                    record.retweet_count = row["retweet_count"]
                    record.like_count = row["like_count"]
                    record.updated_at = row["updated_at"]
                    logging.info(f"Tweets - updating for user {id}")
                else:
                    id = row["id"]
                    # else, we add in a new record representing the new user
                    record = TwitterTweets(**row)
                    logging.info(f"Tweets - We are adding new data for {id}")
                    session.add(record)

                # update tweet_modeled_topic_assoc
                tweet_modeled_topic_dict = {}
                tweet_modeled_topic_dict["tweet_id"] = row["id"]
                tweet_modeled_topic_dict["modeled_topic_id"] = modeled_topic_id

                tweet_model = tweet_modeled_topic_assoc(**tweet_modeled_topic_dict)
                session.add(tweet_model)

    except exc.DatabaseError as e:
        logging.error("Database error occurred:")
        logging.error(f"error - {e}")
    try:
        session.commit()
        logging.info("Upsert successful!")
    except Exception as e:
        logging.info(f"Input syntax error - {e}")
        session.rollback()
    finally:
        session.close()


if __name__ == "__main__":
    store_reddit_niche(
        "/home/sang/Desktop/Sandbox/Nathan/data/reddit/reddit_posts.csv",
    )
    store_subreddit("/home/sang/Desktop/Sandbox/Nathan/data/reddit/subreddits.csv")
    posts = write_reddit_posts(
        "/home/sang/Desktop/Sandbox/Nathan/data/reddit/reddit_posts.csv"
    )
