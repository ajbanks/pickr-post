import os
import sys
from os import environ, path
from dotenv import load_dotenv

sys.path.append("../")

import json
import stripe
from celery import Celery
from celery.schedules import crontab
from flask import Flask, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate

task_queue = Celery(__name__)
login_manager = LoginManager()
db = SQLAlchemy()
migrate = Migrate()

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, ".env"))

celery_broker_url = os.getenv("CELERY_BROKER_URL")

task_queue = Celery(__name__, broker=celery_broker_url)
task_queue.conf.beat_schedule = {
    "task_update_reddit_every_morning": {
        "task": "pickr_flask.tasks.daily_update_reddit",
        "schedule": crontab(hour=4, minute=30),  # morning schedule
        # "schedule": 30,  # schedule every 20 mins
    },
}

def init_app():
    global initial_start
    app = Flask(__name__)
    app.config.from_object("config.Config")
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    stripe.api_key = app.config["STRIPE_SECRET_KEY"]
    app.logger.info("App started")
    with app.app_context():
        from .models import PickrUser  # noqa: disable=F401
        from . import auth, routes, util  # noqa: disable=F401

        db.create_all()

        # load inital topics from a json file
        topics_file = app.config.get(
            "TOPICS_FILE_JSON",
            f"{app.root_path}/static/data/initial-topics.json",
        )
        app.logger.info("Loading initial data")
        test_user_file = f"{app.root_path}/static/data/test-user.json"
        with open(test_user_file) as f:
            test_data = json.load(f)
        load_res = util.load_initial_data(test_data)
        if load_res:
            app.logger.info(
                "Loaded initial data and user, user loaded is %s",
                test_data["user"]["username"],
            )
        else:
            app.logger.info(
            "Initial data has already been loaded"
        )      

        return app
