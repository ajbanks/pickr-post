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
def dms():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import send_marketing_dms
        send_marketing_dms()


@app.command()
def dms_run():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.tasks import run_marketing_functions
        run_marketing_functions()


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


@app.command()
def get_topics_run_days():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.looped_tasks import all_niches_run_pipeline
        import datetime
        date_from = datetime.datetime.strptime('2024-01-03', "%Y-%m-%d")
        date_to = datetime.datetime.strptime('2024-01-10', "%Y-%m-%d")
        all_niches_run_pipeline(date_from, date_to)

        date_from = datetime.datetime.strptime('2024-01-02', "%Y-%m-%d")
        date_to = datetime.datetime.strptime('2024-01-09', "%Y-%m-%d")
        all_niches_run_pipeline(date_from, date_to)


@app.command()
def clean_posts():
    from pickr_flask import init_app
    app = init_app()
    with app.app_context():
        from pickr_flask.tasks import clean_all_generated_tweets
        clean_all_generated_tweets()


if __name__ == "__main__":
    app()
