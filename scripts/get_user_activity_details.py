import logging
import os
from dotenv import load_dotenv
from os import environ
from urllib.parse import urlparse
import gspread
from gspread_formatting import (
    set_column_width,
    set_row_height,
    format_cell_range,
    Borders,
    CellFormat,
)
import pandas as pd
import psycopg2
import psycopg2.extras
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO)
load_dotenv("../.env")

def get_user_activity_data():
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
    cur = conn.cursor()

    df = None
    try:
        cur.execute(
            """
            SELECT * FROM pickr.activity_log;
            """,
        )

        df = pd.DataFrame(cur.fetchall(), columns = ['id', 'username', 'email', 'time', 'event'])
        logging.info('loaded activity log succesfully')

    except Exception as e:
        logging.info('get_user_activity_data exception', e)

    return df

def get_topic_clicks(df):
    return df[df['event'].str.contains("topic_click")]

def get_users_activity(username, df):
    user_df = df[df['username'] == username]
    user_df = user_df.sort_values(by='time', ascending=False)
    num_topic_clicks = len(get_topic_clicks(user_df))
    num_events = len(user_df)
    time_grouped_df = user_df.groupby(user_df['time'].dt.normalize())
    days_distinct_usage = len(time_grouped_df['time'].unique())
    return {'username':username, 'num_topic_clicks': num_topic_clicks, 'num_events':num_events, 'last_sign_in':user_df['time'].values[0], 'days_distinct_usage':days_distinct_usage}


def generate_activity_data(from_date=(date.today() - timedelta(days=30)).isoformat(), to_date=date.today()):

    df = get_user_activity_data()

    mask = (df['time'] >= pd.to_datetime(from_date)) & (df['time'] <= pd.to_datetime(to_date))
    time_period_df = df.loc[mask]

    user_activity_rows = []

    for user in time_period_df['username'].unique():
        user_activity_rows.append(get_users_activity(user, time_period_df))

    activity_df = pd.DataFrame(user_activity_rows)

    activity_df.to_csv('activity_log_' + str(from_date) + "_to_" + str(to_date) + ".csv")

generate_activity_data()