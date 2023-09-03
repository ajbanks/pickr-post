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
    num_topic_clicks = len(get_topic_clicks(user_df))
    num_events = len(user_df)
    return {'username':username, 'num_topic_clicks': num_topic_clicks, 'num_events':num_events}


def generate_activity_data(from_date=(date.today() - timedelta(days=30)).isoformat(), to_date=date.today()):

    df = get_user_activity_data()

    mask = (df['time'] >= pd.to_datetime(from_date)) & (df['time'] <= pd.to_datetime(to_date))
    time_period_df = df.loc[mask]

    user_activity_rows = []

    for user in time_period_df['username'].unique():
        user_activity_rows.append(get_users_activity(user, time_period_df))

    activity_df = pd.DataFrame(user_activity_rows)

    activity_df.to_csv('activity_log_' + str(from_date) + "_to_" + str(to_date) + ".csv")




def create_viral_tweets_table(worksheet, header_background_color, topic):
    # Generated Tweets
    worksheet.update("A9", "Potentially Viral Tweet 1:")
    worksheet.format("A9:A10", {"textFormat": {"bold": True, "fontSize": 14}})
    worksheet.format("A9", header_background_color)
    worksheet.format("A9:A10", {"verticalAlignment": "middle"})
    worksheet.format("A9:A10", {"wrapStrategy": "WRAP"})
    worksheet.update("B9", topic.generated_tweets[0])
    worksheet.format("B9:B10", {"wrapStrategy": "WRAP"})

    worksheet.update("A10", "Potentially Viral Tweet 2:")
    worksheet.format("A10", header_background_color)
    worksheet.update("B10", topic.generated_tweets[1])

    # set_column_width(worksheet, 'H', 266)
    # set_column_width(worksheet, 'I', 380)
    time.sleep(14)


def update_acivity_sheet():

    cols = ["Username", "Total Topic Clicks", "Total Actions"]

    # grey blue
    header_background_color = {
        "backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.9}
    }
    gc = gspread.service_account(filename="service_account.json")
    date_str = datetime.now().strftime("%Y-%m-%d")
    sh = gc.create("activity_log" + date_str)
    sh.share("", perm_type="anyone", role="reader")


    return "https://docs.google.com/spreadsheets/d/%s" % sh.id


generate_activity_data()