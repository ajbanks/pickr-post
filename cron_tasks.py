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
        from pickr_flask.looped_tasks import all_users_run_schedule_schdule
        all_users_run_schedule_schdule()


@app.command()
def schedule_run():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_users_run_schedule
        all_users_run_schedule()


@app.command()
def get_posts_run():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_niches_update
        all_niches_update()

@app.command()
def send_marketing_dms():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import send_marketing_dms
        send_marketing_dms()


@app.command()
def get_posts():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_niches_update_schedule
        all_niches_update_schedule()


@app.command()
def get_topics_run():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_niches_run_pipeline
        all_niches_run_pipeline()


@app.command()
def get_topics():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_niches_run_pipeline_schedule
        all_niches_run_pipeline_schedule()


if __name__ == "__main__":
    app()
