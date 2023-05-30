from dash import Dash, html, dcc, callback, Output, Input

app = Dash(__name__)

app.layout = html.Div([
    html.H1(children='Title of Dash App', style={'textAlign':'center'}),
])


if __name__ == '__main__':
    app.run_server(debug=False)