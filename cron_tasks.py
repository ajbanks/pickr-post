import typer

app = typer.Typer()


@app.command()
def posts():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import post_scheduled_tweets
        post_scheduled_tweets()


@app.command()
def schedule():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_users_run_schedule
        all_users_run_schedule()



@app.command()
def schedule_debug():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_users_run_schedule_debug
        all_users_run_schedule_debug()


if __name__ == "__main__":
    app()

