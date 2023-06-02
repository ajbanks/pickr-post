import pickle

from collections import OrderedDict

import dash_bootstrap_components as dbc
import pandas as pd

from dash import Dash, html, dcc, callback, Output, Input, State, dash_table, ctx

external_stylesheets = [
    {
        "href": (
            "https://fonts.googleapis.com/css2?" "family=Lato:wght@400;700&display=swap"
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


sorted_topics = None  # load_topic_data("pete")
# topics = [t.readable_topic_name for t in sorted_topics]
# topic_selected = sorted_topics[0]

app = Dash(__name__, external_stylesheets=external_stylesheets)
server = app.server
app.title = "Pickr: Your daily topics"

# the style arguments for the sidebar. We use position:fixed and a fixed width
SIDEBAR_STYLE = {
    "position": "fixed",
    "top": 0,
    "left": 0,
    "bottom": 0,
    "width": "16rem",
    "padding": "2rem 1rem",
    "background-color": "#f8f9fa",
    # "display": "none",
}

# the styles for the main content position it to the right of the sidebar and
# add some padding.
CONTENT_STYLE = {
    "margin-left": "18rem",
    "margin-right": "2rem",
    "padding": "2rem 1rem",
}


header = html.Div(
    children=[
        html.H1(children="Your Daily Topics 📈", className="header-title"),
        html.P(
            children=(
                "Find the topics that are trending in your niche and get hand crafted tweets for you"
            ),
            className="header-description",
        ),
        html.Hr(),
    ],
    className="header_alt",
)

login = html.Div(
    id="login-div",
    style={"position": "absolute", "top": "50%", "left": "50%"},
    children=[
        html.Div(
            children=[
                html.H2("Log In"),
                html.Div(
                    children="Enter your email",
                    className="menu-title",
                ),
                dcc.Input(
                    id="email-input",
                    placeholder="Enter the email you signed up with...",
                    className="aspect",
                ),
                dbc.Button("Submit", id="email-submit"),
                html.P(
                    children="If you haven't signed up for an account sign up account, then sign up at www.pickrsocial.com",
                ),
                html.Div(
                    html.P(
                        id="wrong-username",
                        children="\n\nThe email was not found or your topics haven't been generated. Sign up or come back in 24 hours.",
                    ),
                    id="wrong-email",
                    style={"display": "none", "color": "red"},
                ),
                dbc.Spinner(html.Div(id="loading-output")),
            ]
        ),
    ],
)

topic_overiew_dt = dash_table.DataTable(
    id="topic-ov-dt",
    data=None,
    # style_as_list_view=True,
    columns=[
        {"name": "Trend Type", "id": "Trend Type", "type": "text"},
        {"name": "Topic Size", "id": "Topic Size", "type": "numeric"},
        {"name": "Number of Likes", "id": "Number of Likes", "type": "numeric"},
        {"name": "Number of Retweets", "id": "Number of Retweets", "type": "numeric"},
    ],
    style_cell={"textAlign": "left", "height": "auto", "font-family": "Lato"},
    style_header={
        "backgroundColor": "white",
        "fontWeight": "bold",
        "font-family": "Lato",
    },
    fill_width=False,
)
generated_tweets_dt = dash_table.DataTable(
    id="gen-tweet-dt",
    data=None,
    # style_as_list_view=True,
    columns=[
        {
            "name": "Potentially Viral Tweet 1",
            "id": "Potentially Viral Tweet 1",
            "type": "text",
        },
        {
            "name": "Potentially Viral Tweet 2",
            "id": "Potentially Viral Tweet 2",
            "type": "text",
        },
    ],
    style_data={
        "whiteSpace": "normal",
        "height": "auto",
    },
    style_header={
        "backgroundColor": "white",
        "fontWeight": "bold",
        "font-family": "Lato",
    },
    style_cell={"textAlign": "left", "height": "auto", "font-family": "Lato"},
    fill_width=False,
)

topic_posts_dt = dash_table.DataTable(
    id="all-posts-dt",
    data=None,
    columns=[
        {
            "name": "Date",
            "id": "Date",
            "type": "text",
        },
        {
            "name": "Title",
            "id": "Title",
            "type": "text",
        },
        {
            "name": "Body",
            "id": "Body",
            "type": "text",
        },
        {
            "name": "Score",
            "id": "Score",
            "type": "numeric",
        },
        {
            "name": "Link",
            "id": "Link",
            "type": "text",
        },
    ],
    page_action="native",
    page_current=0,
    page_size=10,
    filter_action="native",
    sort_action="native",
    sort_mode="multi",
    style_as_list_view=True,
    style_table={
        "padding-top": "10px",
        "padding-left": "10px",
        "padding-right": "10px",
    },
    style_header={
        "backgroundColor": "white",
        "fontWeight": "bold",
        "font-family": "Lato",
    },
    style_cell={"textAlign": "left", "padding": "5px", "font-family": "Lato"},
    style_data={
        "whiteSpace": "normal",
        "height": "auto",
    },
    fill_width=False,
)

sidebar = html.Div(
    id="side-bar",
    children=[
        html.H2("Topics", className="display-4"),
        html.Hr(),
        html.P("Click on your topics", className="lead"),
        dbc.Nav(
            id="nav-menu",
            vertical=True,
            pills=True,
        ),
    ],
    # style=SIDEBAR_STYLE,
)
topic_content = html.Div(
    id="topic-div",
    style={"display": "none"},
    children=[
        sidebar,
        html.Div(
            id="topic-content",
            children=[
                dcc.Tabs(
                    [
                        dcc.Tab(
                            label="Topic Overview",
                            children=[
                                html.H2(id="topic-name"),
                                html.H5(id="topic-desc"),
                                topic_overiew_dt,
                                html.Hr(),
                                html.P(
                                    id="gen-tweets",
                                    children="\n\nHandcrafted tweets for you",
                                ),
                                generated_tweets_dt,
                            ],
                        ),
                        dcc.Tab(
                            label="Posts from this topic",
                            children=[
                                html.P(
                                    children="Posts from social media about this topic are below"
                                ),
                                topic_posts_dt,
                            ],
                        ),
                    ]
                )
            ],
        ),
    ],
)


app.layout = html.Div(
    children=[
        dcc.Location(id="url"),
        html.Div(children=[header, login, topic_content], style=CONTENT_STYLE),
    ]
)


@app.callback(
    # Output("topic-div", "style"),
    # Output("login-div", "style"),
    Output("loading-output", "children"),
    Input("email-submit", "n_clicks"),
    #    Input("url", "pathname"),
    State("email-input", "value"),
    #    prevent_intial_call=True,
)
def update_output(submit_n_clicks, username):
    print("hi")
    """try:
        print("try")
        topics = load_topic_data(username)
        print("got topic")
        return update_all_cells(topics[0])
    except Exception as e:
        print("pass")
        # print(e)
        pass"""
    return (
        # {"display": "none"},
        # {"display": "block"},
        None,
    )


def load_topic_data(username):
    with open(username + ".pickle", "rb") as f:
        return pickle.load(f)


def render_page_content(pathname):
    if pathname == "/" or pathname is None:
        return update_all_cells(sorted_topics[0])

    for i, t in enumerate(sorted_topics):
        if pathname == "/" + t.readable_topic_name.replace(" ", "_").replace('"', ""):
            return update_all_cells(sorted_topics[i])
    return update_all_cells(sorted_topics[0])


def update_all_cells(topic):
    nav = (
        [
            dbc.NavLink(
                t.readable_topic_name,
                href="/" + t.readable_topic_name.replace(" ", "_").replace('"', ""),
                active="exact",
            )
            for t in sorted_topics
        ],
    )

    ov_df = pd.DataFrame(
        [
            [
                topic.trend_type,
                topic.size,
                topic.num_likes,
                topic.num_retweets,
            ]
        ],
        columns=["Trend Type", "Topic Size", "Number of Likes", "Number of Retweets"],
    )

    gen_df = pd.DataFrame(
        [
            [
                topic.generated_tweets[0],
                topic.generated_tweets[1],
            ]
        ],
        columns=["Potentially Viral Tweet 1", "Potentially Viral Tweet 2"],
    )
    return (
        {"display": "block"},
        {"display": "block"},
        None,
    )


if __name__ == "__main__":
    app.run_server(debug=True)
