# Boilerplate
import sys
import os

sys.path.append("../../")

from typing import Union, List
from tqdm import tqdm
import uuid
from dotenv import load_dotenv

# Standard boilerplate imports
import logging
import pandas as pd
from sqlalchemy import exc

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import exc

# Flask SQLAlchemy - import other tables
from pickr_flask.models import (
    Niche,
    ModeledTopic,
    GeneratedPost,
    RedditPost,
    Subreddit,
)

logging.basicConfig(level=logging.INFO)

load_dotenv()
db_uri = os.getenv("SQLALCHEMY_DATABASE_URI")

# get access to the postgres database using flask
app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = db_uri
db = SQLAlchemy(app)


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


def write_generated_posts(generated_posts: pd.DataFrame, option: str) -> None:
    """ """
    with app.app_context():
        try:
            try:
                val = generated_posts["topic_label"]
            except KeyError as e:
                logging.error(f"No data for generated_post - {e}")
            else:
                for index, row in tqdm(generated_posts.iterrows()):
                    generated_post_dict = {}
                    # If we also have subreddits avaliable
                    if option == "subreddit":
                        generated_post_dict["id"] = row["id"]
                        generated_post_dict["topic_label"] = row["topic_label"]
                        generated_post_dict["text"] = row["text"]
                        generated_post_dict["information_type"] = row["information_type"]
                        # generated_post_dict["brand_style"] = row["brand_style"]
                        generated_post_dict["modeled_topic_id"] = row[
                            "modelled_id_uuid"
                        ]
                        record = (
                            db.session.query(GeneratedPost)
                            .filter(GeneratedPost.id == row["id"])
                            .first()
                        )
                        if record is None:
                            record = GeneratedPost(**generated_post_dict)
                            db.session.add(record)
                    # if not store the gpt generated post
                    elif option == "gpt":
                        generated_post_dict["id"] = row["id"]
                        generated_post_dict["topic_label"] = row["gpt_topic_label"]
                        generated_post_dict["text"] = row["text"]
                        generated_post_dict["information_type"] = row["information_type"]
                        # generated_post_dict["brand_style"] = row["brand_style"]
                        generated_post_dict["modeled_topic_id"] = row[
                            "modeled_topic_id"
                        ]
                        record = (
                            db.session.query(GeneratedPost)
                            .filter(GeneratedPost.id == row["id"])
                            .first()
                        )
                        if record is None:
                            record = GeneratedPost(**generated_post_dict)
                            db.session.add(record)

                db.session.commit()
                logging.info("Write successful! - generated post")
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()


def write_reddit_modeled_overview(
    overview_df: pd.DataFrame
) -> None:
    """
    Store the niche id related work into the Niche from the
    post_fetch_topic_fetch function.

    We are using the readable topic name as the
    """
    with app.app_context():
        try:
            try:
                val = overview_df["name"]
            except KeyError as e:
                logging.error(f"No data for overview - {e}")
            else:
                for index, row in tqdm(overview_df.iterrows()):
                    # modelled topic part
                    modelled_topic_dict = {}
                    # modelled_id_uuid = uuid.uuid4()  # generate key uuid for topic
                    modelled_topic_dict["id"] = row["id"]
                    modelled_topic_dict["name"] = row["name"]  # true topic nam
                    modelled_topic_dict["description"] = row["description"]
                    modelled_topic_dict["size"] = row["size"]
                    modelled_topic_dict["trend_type"] = row["trend_type"]
                    modelled_topic_dict["date"] = row["date"]

                    # modelled_topic_dict["num_likes"] = row["num_likes"]
                    # modelled_topic_dict["num_retweets"] = row["num_retweets"]
                    # modelled_topic_dict["niche_id"] = row["niche_id"]
                    record = (
                        db.session.query(ModeledTopic)
                        .filter(ModeledTopic.id == row["id"])
                        .first()
                    )
                    if record is None:  # if we cannot detect a record, we update
                        record = ModeledTopic(**modelled_topic_dict)
                        db.session.add(record)
                db.session.commit()
                logging.info(f"Write successful! - overview")
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()


def write_reddit_niche(niche_list: List[str]):
    """
    Adding reddit posts
    """
    with app.app_context():
        try:
            topic_id_dict = {}

            for topic in niche_list:
                # store the niche uuids
                niche_id_uuid = uuid.uuid4()
                topic_id_dict[topic] = niche_id_uuid
                # store subreddit ids with the niche ids
                # update Niche input - if we have a duplicated niche
                topic_dict = {}
                topic_dict[
                    "id"
                ] = niche_id_uuid  # topic_id_dict[row["topic"]]  # we have a unique id for each niche
                topic_dict["title"] = topic
                topic_dict["category"] = None
                topic_dict["is_active"] = True
                topic_dict["is_custom"] = False
                # find whether we have an entry for the record
                record = db.session.query(Niche).filter(Niche.title == topic).first()

                if record is None:  # if we cannot detect a record, we update
                    niche_record = Niche(**topic_dict)
                    db.session.add(niche_record)

            db.session.commit()
            logging.info("Write successful! - reddit niche")
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()


def retrieve_reddit_niche() -> Union[pd.DataFrame, str]:
    """
    Get the ids for the niche title from the niche table, then join with the
    rsubreddit names and make a new table
    """
    with app.app_context():
        try:
            # first of all, get the Niche data, ensure we have an entry
            query = db.session.query(Niche)
            df = query.all()
            df = pd.DataFrame(
                [row.__dict__ for row in df]
            )  # get the pandas table for the Niche
            # return just the niche id and its associated title
            return df[["id", "title"]]

        except exc.SQLAlchemyError as e:
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")


def retrieve_model_id() -> Union[pd.DataFrame, str]:
    """ """
    with app.app_context():
        try:
            # first of all, get the Niche data, ensure we have an entry
            query = db.session.query(ModeledTopic)
            df = query.all()
            df = pd.DataFrame(
                [row.__dict__ for row in df]
            )  # get the pandas table for the Niche
            # return just the niche id and its associated title
            return df[["id", "niche_id"]]

        except exc.SQLAlchemyError as e:
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")


def retrieve_niche_subreddit() -> Union[pd.DataFrame, str]:
    """
    Database call for the niche and linked subreddit to a
    pandas table
    """
    niche_df = retrieve_reddit_niche()  # id, niche
    niche_df = niche_df.rename(columns={"id": "niche_id"})
    subreddit_df = retrieve_subreddit()  # id, niche_id, title
    subreddit_df = subreddit_df.rename(columns={"title": "subreddit_title"})
    niche_subreddit = niche_df.merge(subreddit_df, how="left", on="niche_id").rename(
        columns={"title": "niche", "subreddit_title": "subreddit"}
    )
    niche_subreddit = niche_subreddit[["niche", "subreddit", "id", "niche_id"]]
    return niche_subreddit


def retrieve_subreddit() -> Union[pd.DataFrame, str]:
    """
    Get the ids for the niche title from the niche table, then join with the
    rsubreddit names and make a new table
    """
    with app.app_context():
        try:
            # first of all, get the Niche data, ensure we have an entry
            query = db.session.query(Subreddit)
            df = query.all()
            df = pd.DataFrame(
                [row.__dict__ for row in df]
            )  # get the pandas table for the Niche
            # return just the niche id and its associated title
            return df[["id", "niche_id", "title"]]

        except exc.SQLAlchemyError as e:
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")


def write_subreddit(
    file_path: str,
) -> None:
    """
    Reshape the subreddit data and store the subreddit as a relational database with the niche id
    """
    with app.app_context():
        # empty entries in subreddit
        # try:
        #    db.session.query(Subreddit).delete()
        #    db.session.commit()
        #    logging.info(f"Resetting the subreddit table")
        # except Exception as e:
        #    logging.error(f"error in deleting the subreddit table")
        #    db.session.rollback()
        # finally:
        #    db.session.close()
        try:
            niches = retrieve_reddit_niche()
            niches = niches.rename(columns={"title": "niche"})
            # Read subreddit data
            subreddit_data = pd.read_csv(file_path)
            # Remove rows with NaNs
            subreddit_data = subreddit_data.dropna()
            # Ensure that the format of the niche we read with the subreddit file
            # is consistent with the niche identified with the reddits posts niche
            subreddit_data["niche"] = (
                subreddit_data["niche"].str.replace("_", " ").str.lower()
            )
            # isolate only the niche and subreddits associated with that niche
            subreddit_data = subreddit_data.merge(niches, how="outer")
            subreddit_data = subreddit_data.rename(columns={"id": "niche_id"})

            for index, row in tqdm(subreddit_data.iterrows()):
                subreddit_dict = {}
                subreddit_id_uuid = uuid.uuid4()  # generate key uuid for topic
                subreddit_dict["id"] = subreddit_id_uuid
                subreddit_dict["title"] = row["subreddits"]
                subreddit_dict["niche_id"] = row["niche_id"]
                # ensure that we are not adding a repeated topic here
                record = (
                    db.session.query(Subreddit)
                    .filter(
                        Subreddit.title == row["subreddits"],
                    )
                    .first()
                )
                if record is None:
                    record = Subreddit(**subreddit_dict)
                    db.session.add(record)
            db.session.commit()
            logging.info("Write successful! - subreddit")
        except exc.SQLAlchemyError as e:
            db.session.rollback()

            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()


def write_reddit_posts(topic_posts_df: pd.DataFrame) -> None:
    """
    With the niche and subreddit data updated, now join the data and load the
    data as necessary

    Need toniche_id_uuid = uuid.uuid4()
                 implement the part for which we want to
    implement the writing to the RedditPost

    """
    with app.app_context():
        try:
            try:
                posts = topic_posts_df[
                    ["Title", "Body", "Score", "Date", "Link", "modeled_topic_id"]
                ]
            except KeyError as e:
                logging.error(f"Couldn't filter the file! - {e}")
            else:
                for index, row in tqdm(topic_posts_df.iterrows()):
                    reddit_dict = {}
                    reddit_dict["id"] = row["id"]
                    reddit_dict["title"] = row["title"]
                    reddit_dict["body"] = row["body"]
                    reddit_dict["score"] = row["score"]
                    reddit_dict["date"] = row["date"]
                    reddit_dict["link"] = row["link"]
                    reddit_dict["modeled_topic_id"] = row["modeled_topic_id"]
                    # ensure that we are not adding a repeated topic here
                    record = (
                        db.session.query(RedditPost)
                        .filter(RedditPost.id == row["id"])
                        .first()
                    )
                    if record is None:
                        record = RedditPost(**reddit_dict)
                        db.session.add(record)
                db.session.commit()
                logging.info("Write successful! - topic posts")
        except exc.SQLAlchemyError as e:
            db.session.rollback()
            logging.error("Database error occurred:")
            logging.error(f"error - {e}")
        finally:
            db.session.close()
