import csv
import datetime
import pickle


import dash_bootstrap_components as dbc
import pandas as pd
from flask import request

from dash import Dash, html, dcc, Output, Input, State, dash_table, ctx

external_stylesheets = [
    {
        "href": (
            "https://fonts.googleapis.com/css2?"
            "family=Inter:wght@400;700&display=swap"
        ),
        "rel": "stylesheet",
    },
    dbc.themes.BOOTSTRAP,
]

app_colors = {
    "background": "#0C0F0A",
    "text": "#FFFFFF",
    "sentiment-plot": "#41EAD4",
    "volume-bar": "#FBFC74",
    "someothercolor": "#FF206E",
}


def load_topic_data(username):
    username = username.lower()
    if username[0] == "@":
        username = username[1:]
    print(username)
    with open("data/" + username + ".pickle", "rb") as f:
        return pickle.load(f)


sorted_topics = None  # load_topic_data("pete")
# topics = [t.readable_topic_name for t in sorted_topics]
# topic_selected = sorted_topics[0]

app = Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server
app.title = "Pickr: Your daily topics"

# the styles for the main content position it to the right of the sidebar and
# add some padding.
CONTENT_STYLE = {
    # "margin-left": "10rem",
    # "margin-right": "2rem",
    # "padding": "2rem 1rem",
}

header = html.Div(
    children=[
        html.H1(children="Your Daily Topics 📈", className="header-title"),
        html.P(
            children=(
                "Trending topics in your niche and generated tweets - "
                + datetime.datetime.now().strftime(" %B %d, %Y")
            ),
            className="header-description",
        ),
        html.Div(
            children=[
                html.Div(
                    children=[
                        html.Div(
                            children="Enter your twitter handle and get your trending topics",
                            className="menu-title",
                        ),
                        html.P(
                            children="Create an account at pickrsocial.com/signup",
                            style={"font-size": "85%"},
                        ),
                        dcc.Input(
                            id="email-input",
                            placeholder="Twitter handle...",
                            className="aspect",
                        ),
                        html.Br(),
                        html.Br(),
                        dbc.Button(
                            "Enter",
                            id="email-submit",
                            # style={"margin-left": "0.5em"},
                            style={
                                "margin": "0 auto",
                                # "display": "block",
                                "width": "10em",
                            },
                        ),
                        dbc.Spinner(
                            html.Div(
                                id="loading-output",
                                style={"margin": "0 auto", "display": "block"},
                            )
                        ),
                        # html.Br(),
                        html.Div(
                            html.P(
                                id="wrong-username",
                                children="\nUser not found or topics not yet generated. Sign up or return in 24 hours.",
                            ),
                            id="wrong-email",
                            style={"display": "none", "color": "red"},
                        ),
                    ],
                ),
            ],
            className="menu",
        ),
    ],
    className="header",
)

topic_overiew_dt = dash_table.DataTable(
    id="topic-ov-dt",
    data=None,
    style_as_list_view=True,
    columns=[
        {"name": "Type", "id": "Type", "type": "text"},
        {"name": "Size", "id": "Size", "type": "numeric"},
        {"name": "Total Likes", "id": "Total Likes", "type": "numeric"},
        {"name": "Total Retweets", "id": "Total Retweets", "type": "numeric"},
    ],
    style_cell={
        "textAlign": "left",
        "height": "auto",
        "font-family": "Inter",
        "width": "10em",
    },
    style_header={
        "backgroundColor": "#6c2cec",
        "color": "white",
        "fontWeight": "bold",
        "font-family": "Inter",
    },
    style_data={
        "whiteSpace": "normal",
        "height": "auto",
    },
    fill_width=False,
)
generated_tweets_dt = dash_table.DataTable(
    id="gen-tweet-dt",
    data=None,
    style_as_list_view=True,
    columns=[
        {
            "name": "Viral Tweet 1",
            "id": "Viral Tweet 1",
            "type": "text",
        },
        {
            "name": "Viral Tweet 2",
            "id": "Viral Tweet 2",
            "type": "text",
        },
    ],
    style_data={
        "whiteSpace": "normal",
        "height": "auto",
    },
    style_header={
        "backgroundColor": "#6c2cec",
        "color": "white",
        "fontWeight": "bold",
        "font-family": "Inter",
    },
    style_cell={"textAlign": "left", "height": "auto", "font-family": "Inter"},
    fill_width=False,
)

ALL_POSTS_COLS = ["Posts"]
topic_posts_dt = dash_table.DataTable(
    id="all-posts-dt",
    data=None,
    columns=[
        {
            "name": "Posts",
            "id": "Posts",
            "type": "text",
        }
    ],
    page_action="native",
    page_current=0,
    page_size=10,
    filter_action="native",
    style_as_list_view=True,
    # style_table={
    #    "padding-top": "10px",
    #    "padding-left": "10px",
    #    "padding-right": "10px",
    # },
    style_header={
        "backgroundColor": "#6c2cec",
        "color": "white",
        "fontWeight": "bold",
        "font-family": "Inter",
    },
    style_cell={"maxWidth": "100%", "textAlign": "left", "font-family": "Inter"},
    style_data={
        "whiteSpace": "pre-line",
        "height": "auto",
    },
    fill_width=False,
)


topic_content = html.Div(
    id="topic-content",
    children=[
        html.Div(
            children=[
                html.Br(),
                html.H5(
                    children="Select a topic...",
                    # style={"margin": "0 auto", "display": "block"},
                ),
                dcc.Dropdown(
                    id="topic-dropdown",
                    # style={"width": "100%"},
                ),
            ],
            style={"margin": "0 auto", "display": "block"},
        ),
        html.Br(),
        dcc.Tabs(
            [
                dcc.Tab(
                    label="Topic Overview",
                    children=[
                        html.Div(
                            style={"padding-left": "0.25em"},
                            children=[
                                html.Br(),
                                html.H2(id="topic-name"),
                                html.Hr(),
                                html.Br(),
                                html.H5(id="topic-desc"),
                                topic_overiew_dt,
                                html.Br(),
                                html.Hr(),
                                html.H5(
                                    id="gen-tweets",
                                    children="\n\nTweets you can post or use as inspiration",
                                ),
                                html.Br(),
                                html.P(
                                    "Generated Tweet 1:", style={"font-weight": "bold"}
                                ),
                                html.P(id="gen-tweet-1"),
                                html.P(
                                    "Generated Tweet 2:", style={"font-weight": "bold"}
                                ),
                                html.P(id="gen-tweet-2"),
                            ],
                        )
                    ],
                ),
                dcc.Tab(
                    label="Posts from topic",
                    children=[
                        html.Div(
                            style={"padding-left": "0.25em"},
                            children=[
                                html.Br(),
                                html.H5(
                                    children="Posts from social media about this topic are below"
                                ),
                                topic_posts_dt,
                            ],
                        )
                    ],
                ),
            ]
        ),
    ],
)

app.layout = html.Div(
    children=[
        html.Div(children=[header, topic_content], style=CONTENT_STYLE),
    ]
)


@app.callback(
    Output("topic-dropdown", "options"),
    Output("topic-name", "children"),
    Output("topic-desc", "children"),
    Output("topic-ov-dt", "data"),
    Output("gen-tweet-1", "children"),
    Output("gen-tweet-2", "children"),
    Output("all-posts-dt", "data"),
    Output("wrong-email", "style"),
    Output("topic-content", "style"),
    Output("loading-output", "children"),
    Input("email-submit", "n_clicks"),
    Input("topic-dropdown", "value"),
    State("email-input", "value"),
    # prevent_intial_call=True,
)
def update_output(submit_n_clicks, url, username):
    print("url", url)
    triggered_id = ctx.triggered_id
    global sorted_topics
    if triggered_id == "email-submit":
        print("in email submit")
        try:
            sorted_topics = load_topic_data(username)
            log_activity(username, "Login")
        except Exception as e:
            print(e)
            log_activity(username, "Failed Login")
            return (
                [{"label": " i.readable_topic_name", "value": "i.readable_topic_name"}],
                None,
                None,
                None,
                None,
                None,
                None,
                {"display": "block", "color": "red"},
                {"visibility": "hidden"},
                None,
            )

        return update_all_cells(sorted_topics[0])
    elif triggered_id == "topic-dropdown":
        print("in url", url)
        if sorted_topics is None:
            log_activity(username, "No topics but dropdown is picked")
            print("log user activity")
            return (
                [{"label": " i.readable_topic_name", "value": "i.readable_topic_name"}],
                None,
                None,
                None,
                None,
                None,
                None,
                {"display": "block", "color": "red"},
                {"visibility": "hidden"},
                None,
            )
        print("going to render for url")
        log_activity(username, "New Topic")
        return render_page_content(url)
    print("didnt enter an if")
    log_activity(username, "Initial Load")
    return (
        [{"label": " i.readable_topic_name", "value": "i.readable_topic_name"}],
        None,
        None,
        None,
        None,
        None,
        None,
        {"display": "none"},
        {"visibility": "hidden"},
        None,
    )


def log_activity(username: str, action: str):
    if username is None or username == "":
        username = "No new login"
    with open("data/log.csv", "a") as csvfile:
        writer = csv.writer(csvfile, delimiter=",")
        writer.writerow(
            [
                datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                str(username),
                str(request.remote_addr),
                action,
            ]
        )


def render_page_content(pathname):
    if pathname == "" or pathname is None:
        return update_all_cells(sorted_topics[0])

    for i, t in enumerate(sorted_topics):
        print(pathname, t.readable_topic_name.replace(" ", "_").replace('"', ""))
        if pathname == t.readable_topic_name:
            return update_all_cells(sorted_topics[i])
    print("returning as didnt find match")
    return update_all_cells(sorted_topics[0])


def update_all_cells(topic):
    """nav = (
        [
            dbc.NavLink(
                treadable_topic_name,
                href="/" + t.readable_topic_name.replace(" ", "_").replace('"', ""),
                active="exact",
            )
            for t in sorted_topics
        ],
    )"""

    nav = [
        {"label": i.readable_topic_name, "value": i.readable_topic_name}
        for i in sorted_topics
    ]

    ov_df = pd.DataFrame(
        [
            [
                topic.trend_type,
                topic.size,
                topic.num_likes,
                topic.num_retweets,
            ]
        ],
        columns=["Type", "Size", "Total Likes", "Total Retweets"],
    )

    all_posts_df = topic.topic_tweets
    all_posts_df["Posts"] = (
        all_posts_df["Text"]
        + "\n\nTweet link: "
        + all_posts_df["url"]
        + "\nUsername:"
        + all_posts_df["Username"].astype(str)
        + "\nLikes:"
        + all_posts_df["Likes"].astype(str)
        + "\nRetweets:"
        + all_posts_df["Retweets"].astype(str)
    )
    all_posts_df = all_posts_df[ALL_POSTS_COLS]

    return (
        nav,
        topic.readable_topic_name,
        topic.description,
        ov_df.to_dict("records"),
        topic.generated_tweets[0],
        topic.generated_tweets[1],
        all_posts_df.to_dict("records"),
        {"display": "none"},
        {"visibility": "visible"},
        None,
    )


if __name__ == "__main__":
    app.run_server(debug=True)
