import uuid
import logging
import os
from dotenv import load_dotenv
from os import environ
from urllib.parse import urlparse

import pandas as pd
import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO)
load_dotenv("../.env")


def get_modeled_topic_id(username, topic_name, cur):
    mt_ids = []
    try:
        cur.execute(
            """
            select mt.id
            from pickr.user u
            left join pickr.user_niche_assoc una
                on u.id = una.user_id
            left join pickr.modeled_topic mt 
                on mt.niche_id = una.niche_id
            where u.username = %(username)s
            and mt.name = %(topic_name)s;
            """,
            {'username': username, 'topic_name': topic_name}
        )
        res = cur.fetchall()
        mt_ids = [(r[0]) for r in res]
    except Exception as e:
        logging.info('get_modeled_topic_id exception', e)
        cur.execute("rollback")
    return mt_ids


def get_generated_post_id(username, post_text, cur):
    gp_ids = []
    try:
        cur.execute(
            """
            select gp.id
            from pickr.user u
            left join pickr.user_niche_assoc una
                on u.id = una.user_id
            left join pickr.modeled_topic mt 
                on mt.niche_id = una.niche_id
            left join pickr.generated_post gp
                on mt.id = gp.modeled_topic_id
            where u.username = %(username)s
            and gp.text = %(post_text)s;
            """,
            {'username': username, 'post_text': post_text}
        )
        res = cur.fetchall()
        gp_ids = [(r[0]) for r in res]
    except Exception as e:
        logging.info('get_generated_post_id exception', e)
        cur.execute("rollback")
    return gp_ids


def modify_modeled_topic(username, topic_name, new_name, cur):
    # set modeled topic name to new_name for posts with whose name is equal to post_name
    mt_ids = get_modeled_topic_id(username, topic_name, cur)
    
    # update row(s) with the id(s) we havve returned
    if len(mt_ids) == 0:
        logging.info(f"no rows found for {username} and {topic_name[:20]}...")
        return
    try:
        logging.info(f"Modeled Topic IDs {mt_ids}")
        cur.execute(
            """
            update pickr.modeled_topic
            set
            name = %(new_name)s
            where id in (%(mt_ids)s)
            """,
            {'new_name': new_name, 'mt_ids': tuple(mt_ids)}
        )
        logging.info(f"modify_modeled_topic - Modifyed {topic_name[:20]}...")
    except Exception as e:
        logging.info('modify_modeled_topic exception', e)
        cur.execute("rollback")


def delete_modeled_topic(username, topic_name, cur):
    # delete modeleted topic with topic_name as its name
    mt_ids = get_modeled_topic_id(username, topic_name, cur)
    
    # delete row(s) with the id(s) we have returned, must also delete generated posts in generated_post table and set modeleted_topic_id to NULL in reddit table
    if len(mt_ids) == 0:
        logging.info(f"no rows found for {username} and {topic_name[:20]}...")
        return
    try:
        logging.info(f"Modeled Topic IDs {mt_ids}")
        cur.execute(
            """
            delete from pickr.generated_post gp
            where gp.modeled_topic_id in (%(mt_ids)s)
            """,
            {'mt_ids': tuple(mt_ids)}
        )
        logging.info(f"delete_modeled_topic - Deleted Generated Posts Under Modeled Topic {topic_name[:20]}...")

        cur.execute(
            """
            update pickr.reddit
            set
            modeled_topic_id = NULL
            where modeled_topic_id in (%(mt_ids)s)
            """,
            {'mt_ids': tuple(mt_ids)}
        )
        logging.info(f"delete_modeled_topic - Deleted Generated Posts Under Modeled Topic {topic_name[:20]}...")
        
        cur.execute(
            """
            delete from pickr.modeled_topic mt
            where mt.id in (%(mt_ids)s)
            """,
            {'mt_ids': tuple(mt_ids)}
        )
        logging.info(f"delete_modeled_topic - Deleted Modeled Topic {topic_name[:20]}...")
    except Exception as e:
        logging.info('delete_modeled_topic exception', e)
        cur.execute("rollback")
    

def modify_generated_post(username, post_text, new_text, cur):
    # set generated posts text to new_text for posts with whose text is equal to post_text
    gp_ids = get_generated_post_id(username, post_text, cur)
    
    # update row(s) with the id(s) we havve returned
    if len(gp_ids) == 0:
        logging.info(f"no rows found for {username} and {post_text[:20]}...")
        return
    try:
        logging.info(f"Generated Post IDs {gp_ids}")
        cur.execute(
            """
            update pickr.generated_post
            set
            text = %(new_text)s
            where id in (%(gp_ids)s)
            """,
            {'new_text': new_text, 'gp_ids': tuple(gp_ids)}
        )
        logging.info(f"delete_generated_post - Modifyed {post_text[:20]}...")
    except Exception as e:
        logging.info('delete_generated_post exception', e)
        cur.execute("rollback")


def delete_generated_post(username, post_text, cur):
    # delete generated posts with post_text as its text
    gp_ids = get_generated_post_id(username, post_text, cur)
    
    # delete row(s) with the id(s) we have returned
    if len(gp_ids) == 0:
        logging.info(f"no rows found for {username} and {post_text[:20]}...")
        return
    try:
        logging.info(f"Generated Post IDs {gp_ids}")
        cur.execute(
            """
            delete from pickr.generated_post gp
            where gp.id in (%(gp_ids)s)
            """,
            {'gp_ids': tuple(gp_ids)}
        )
        logging.info(f"delete_generated_post - Deleted {post_text[:20]}...")
    except Exception as e:
        logging.info('delete_generated_post exception', e)
        cur.execute("rollback")


def update_db():
    psycopg2.extras.register_uuid()
    p = urlparse(os.getenv("SQLALCHEMY_DATABASE_URI"))
    logging.info(f"DB Connection: {p.hostname, p.path[1:], p.username}")
    pg_connection_dict = {
        'database': p.path[1:],
        'user': p.username,
        'password': p.password,
        'host': p.hostname
    }
    conn = psycopg2.connect(**pg_connection_dict)

    logging.info('Loading CSVs')
    modeled_topic_modify_df = pd.read_csv('data/modeled_topic_modify.csv')
    modeled_topic_delete_df = pd.read_csv('data/modeled_topic_delete.csv')
    generated_post_modify_df = pd.read_csv('data/generated_post_modify.csv')
    generated_post_delete_df = pd.read_csv('data/generated_post_delete.csv')

    logging.info('Running Modeled Topic Modify')
    for idx, row in modeled_topic_modify_df.iterrows():
        username = row["username"]
        topic_name = row["modeled_topic_name"]
        new_name = row["new_name"]
        with conn.cursor() as cur:
            modify_modeled_topic(username, topic_name, new_name, cur)
            conn.commit()

    logging.info('Running Modeled Topic Delete')
    for idx, row in modeled_topic_delete_df.iterrows():
        username = row["username"]
        topic_name = row["modeled_topic_name"]
        with conn.cursor() as cur:
            delete_modeled_topic(username, topic_name, cur)
            conn.commit()

    logging.info('Running Generated Post Modify')
    for idx, row in generated_post_modify_df.iterrows():
        username = row["username"]
        post_text = row["generated_post_text"]
        new_text = row["new_text"]
        with conn.cursor() as cur:
            modify_generated_post(username, post_text, new_text, cur)
            conn.commit()

    logging.info('Running Generated Post Delete')
    for idx, row in generated_post_delete_df.iterrows():
        username = row["username"]
        post_text = row["generated_post_text"]
        with conn.cursor() as cur:
            delete_generated_post(username, post_text, cur)
            conn.commit()


if __name__ == "__main__":
    update_db()
