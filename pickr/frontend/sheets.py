import time
from datetime import datetime
import gspread
from gspread_formatting import (
    set_column_width,
    set_row_height,
    format_cell_range,
    Borders,
    CellFormat,
)


def create_topic_list_sheet(topics, spreadsheet, header_background_color):
    worksheet = spreadsheet.get_worksheet(0)
    worksheet.update_title("Your trending topics")

    worksheet.update(
        "D1",
        "This spreadsheet contains sheets for each of the topics listed.\n\n"
        "In each topic sheet you will find a topic description beneath the topic title."
        "and examples of posts that are part of the topic. \n\n"
        "You also have two potentially viral generated tweets that you can post or use as inspiration",
    )
    worksheet.format("D1", {"wrapStrategy": "WRAP"})
    worksheet.format("A1", {"wrapStrategy": "WRAP"})
    worksheet.format("A1", {"verticalAlignment": "middle"})
    worksheet.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
    worksheet.update("A1", "Your trending topics:")
    worksheet.format("A1", header_background_color)
    set_column_width(worksheet, "A", 266)
    set_column_width(worksheet, "D", 380)

    for i in range(len(topics)):
        cell = "A" + str(i + 2)
        worksheet.update(cell, "• " + topics[i].readable_topic_name)
        worksheet.format(cell, {"textFormat": {"bold": False, "fontSize": 11}})
        worksheet.format(cell, {"wrapStrategy": "WRAP"})
        if i % 2 == 0:
            time.sleep(14)


def create_trend_table(worksheet, header_background_color, t):
    set_column_width(worksheet, "A", 193)
    set_column_width(worksheet, "B", 393)
    worksheet.update("A1", "Topic Name:")
    worksheet.format("A1", {"verticalAlignment": "middle"})
    worksheet.update("B1", t.readable_topic_name)
    worksheet.format("A1", {"textFormat": {"bold": True, "fontSize": 14}})
    worksheet.format("A1", {"wrapStrategy": "WRAP"})
    worksheet.format("A1", header_background_color)
    worksheet.format("B1", {"wrapStrategy": "WRAP"})
    time.sleep(14)
    worksheet.update("A2", "Topic Description:")
    worksheet.format("A2", {"textFormat": {"bold": True, "fontSize": 14}})
    worksheet.format("A2", header_background_color)
    worksheet.format("A2", {"verticalAlignment": "middle"})
    worksheet.update("B2", t.description)
    worksheet.format("B2", {"wrapStrategy": "WRAP"})

    worksheet.update(
        "A5:C8",
        [
            ["Trend Type", "Num Posts", "Likes"],
            [t.trend_type, int(t.size), int(t.num_likes)],
        ],
    )
    worksheet.format("A5:C5", {"textFormat": {"bold": True, "fontSize": 14}})
    worksheet.format("A5:C8", {"horizontalAlignment": "center"})
    worksheet.format("A5:C8", {"verticalAlignment": "middle"})
    worksheet.format("A5:C5", header_background_color)

    time.sleep(14)


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


def create_topic_post_table(worksheet, header_background_color, t, cols, source):
    set_column_width(worksheet, "C", 380)
    topic_tweets = t.topic_tweets.copy()
    topic_tweets["Date"] = topic_tweets["Date"].astype(str)
    for col_name in ["Likes", "Retweets", "Score"]:
        if col_name in topic_tweets.columns:
            topic_tweets[col_name] = topic_tweets[col_name].astype(int)
    if source == "reddit":
        topic_tweets["Post Text"] = topic_tweets["Title"] + " - " + topic_tweets["Body"]
    elif source == "twitter":
        topic_tweets["Post Text"] = topic_tweets["Text"]
    topic_tweets["Post Text"].astype(str)
    topic_tweets["Post Text"] = topic_tweets["Post Text"].str[:3000]
    topic_tweets["Post Text"] = topic_tweets["Post Text"].fillna("")
    topic_tweets = topic_tweets.drop_duplicates(subset=["Post Text"])

    topic_tweets = topic_tweets[cols]
    end_column = chr(ord("@") + len(topic_tweets.columns))
    worksheet.update(
        "A15", "Posts from social media sites that are related to this topic:"
    )
    worksheet.format("A15", {"wrapStrategy": "WRAP"})
    worksheet.format("A15", header_background_color)
    worksheet.format("A15", {"textFormat": {"bold": True, "fontSize": 12}})
    worksheet.update("A16:" + end_column + "16", [topic_tweets.columns.tolist()])
    worksheet.format("A16:" + end_column + "16", {"verticalAlignment": "middle"})
    worksheet.format(
        "A16:" + end_column + "16", {"textFormat": {"bold": True, "fontSize": 12}}
    )
    worksheet.format("A16:" + end_column + "16", header_background_color)
    worksheet.update(
        "A17:" + end_column + str(17 + len(topic_tweets)),
        topic_tweets.values.tolist(),
    )
    worksheet.format(
        "A17:" + end_column + str(17 + len(topic_tweets)), {"wrapStrategy": "CLIP"}
    )
    # worksheet.format('A7:' + end_column + str(14 + len(t.topic_tweets)), {"horizontalAlignment": "center"})
    worksheet.format(
        "A17:" + end_column + str(17 + len(topic_tweets)),
        {"verticalAlignment": "middle"},
    )


def create_sheet(username, topics, source, max_topics=13):
    if source == "twitter":
        cols = ["Date", "Username", "Text", "Likes", "Retweets", "url"]
    elif source == "reddit":
        cols = ["Date", "Post Text", "Link"]
    # grey blue
    header_background_color = {
        "backgroundColor": {"red": 0.85, "green": 0.93, "blue": 0.9}
    }
    gc = gspread.service_account(filename="service_account.json")
    date_str = datetime.now().strftime("%Y-%m-%d")
    sh = gc.create("Pickr - Trending Topics for You " + date_str + " " + username)
    sh.share("", perm_type="anyone", role="reader")

    readable_topic_names = []
    create_topic_list_sheet(topics, sh, header_background_color)
    for i, t in enumerate(topics[:max_topics]):
        topic_name = t.readable_topic_name[:100]
        readable_topic_names.append(topic_name)
        worksheet = sh.add_worksheet(
            title=t.readable_topic_name[:100], rows=1300, cols=50
        )

        create_trend_table(worksheet, header_background_color, t)

        create_viral_tweets_table(worksheet, header_background_color, t)

        create_topic_post_table(worksheet, header_background_color, t, cols, source)

        if i % 2 == 0:
            print("sheets sleep")
            time.sleep(30)

    return "https://docs.google.com/spreadsheets/d/%s" % sh.id
