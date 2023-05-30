import pytest
import os
import pathlib
import datetime
from funcy import lmap
import tweepy
import pickr.twitter.backend as backend
import psycopg2

@pytest.fixture
def session():
    conn = psycopg2.connect(
        host="localhost",
        user="pickr_test",
        database="pickr_test",
        password="pickr_test",
    )
    cur = conn.cursor()
    yield cur
    conn.close()

@pytest.fixture
def setup_db(session):
    root_dir = pathlib.Path(__file__).parent.parent.parent
    sql_file = str(root_dir) + "/schema/structure.sql"

    session.execute("CREATE SCHEMA IF NOT EXISTS twitter;")
    session.connection.commit()

    with open(sql_file, 'r') as f:
        script = f.read()
        session.execute(script)
        session.connection.commit()

@pytest.fixture
def mock_tweets():
    data = [
        {"id": 1,
         "text": "hello world",
         "created_at": "2022-09-19T22:07:46.000Z",
         "author_id": 1,
         "retweets": 100,
         "likes": 5555,
         "retweet_id": 0,
         "quote_id": 0,
         "lang": "uk",
         },
        {"id": 2,
         "text": "goodbye world",
         "created_at": "2022-10-19T22:07:46.000Z",
         "author_id": 1,
         "retweets": 100,
         "likes": 10,
         "retweet_id": 0,
         "quote_id": 0,
         "lang": "en",
         },
         {"id": 3,
          "text": "I'm on twitter LOL",
          "created_at": "2022-10-22T10:07:46.000Z",
          "author_id": 2,
          "retweets": 10,
          "likes": 2,
          "retweet_id": 0,
          "quote_id": 0,
          "lang": "en",
        },
        {"id": 4,
         "text": "pls give me more followers",
         "created_at": "2021-10-22T10:07:46.000Z",
         "author_id": 2,
         "retweets": 0,
         "likes": 2,
         "retweet_id": 0,
         "quote_id": 0,
         "lang": "en",
         }
    ]
    return data

@pytest.mark.usefixtures("setup_db")
def test_insert_tweets(session, mock_tweets):
    backend.insert_tweets(session, mock_tweets)

    got_tweets = backend.get_tweets_by_uids(session, [1])
    assert len(got_tweets) == 2
    assert all([t["author_id"]==1 for t in got_tweets])

    got_all_tweets = backend.get_all_tweets(session)
    assert len(got_all_tweets) == 4

    got_by_ids = backend.get_tweets_by_ids(session, [1,3,4])
    assert len(got_by_ids) == 3

@pytest.mark.usefixtures("setup_db")
def test_update_tweet(session, mock_tweets):
    backend.insert_tweets(session, mock_tweets)
    data = ["@elon you suck!!! :P","you suck"]
    backend.update_tweet(session,
        1, ["text","processed_text"], data)

    got_tweet = backend.get_tweets_by_ids(session, [1])
    assert len(got_tweet)==1
    assert got_tweet[0]["text"] == data[0]

@pytest.mark.usefixtures("setup_db")
def test_update_tweets(session, mock_tweets):
    backend.insert_tweets(session, mock_tweets)

    fields = ["id", "retweet_count", "text"]
    rows = [(1, 1000, "tweet 1"),
            (2, 2000, "tweet 2"),
            (3, 3000, "tweet 3")]
    backend.update_tweets(session, fields, rows)

    for tid in [1,2,3]:
        got_tweet = backend.get_tweets_by_ids(session, [tid])
        assert len(got_tweet)==1
        assert got_tweet[0]["text"] == f"tweet {tid}"

@pytest.mark.usefixtures("setup_db")
def test_insert_users(session):
    data = [{"id": 1,
             "name": "Elon Musk",
             "username": "elonmusk",
             "public_metrics": {
                 "followers_count": 1000000,
                 "tweet_count": 555555,
             }},
            {"id": 5,
             "name": "François Chollet",
             "username": "fchollet",
             "public_metrics": {
                 "followers_count": 200000,
                 "tweet_count": 55555,
             }},
            {"id": 1519809726,
             "name": "Nathan Francis",
             "username": "Frankly_Francis",
             "public_metrics": {
                 "followers_count": 500,
                 "tweet_count": 555,
             }}]
    users = [tweepy.User(data=d) for d in data]
    backend.insert_users(session, users)

    for user in users:
        got_user = backend.get_user_by_id(session, user.id)

@pytest.mark.usefixtures("setup_db")
def test_insert_topics(session):
    data = [{"name": "football", "source": "hashtag"},
            {"name": "AI_overlords_rule", "source": "GPT3"},
            {"name": "Donald_Trump", "source": "BERTopic"}]

    ids = lmap(
        lambda d: backend.insert_topic(session, d["name"], d["source"]),
        data)
    assert ids == [1,2,3]

@pytest.mark.usefixtures("setup_db")
def test_follow_graph(session):
    edges = [(2,1), (1,2), (1,3), (2,3), (3,4), (4,5), (5,6)]
    backend.insert_follows(session, edges)

    for mode, expect in zip([0,1,2],[2,5,5]):
        print(f"mode: {mode}")
        got_edges = backend.get_follow_graph(session, 1, 2, mode=mode)
        assert len(set(got_edges)) == expect
