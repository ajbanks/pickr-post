from os import environ, path
from dotenv import load_dotenv
from celery.schedules import crontab

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, ".env"))

# TODO: split into dev/prod configs


class Config:
    # Flask
    FLASK_APP = environ.get("FLASK_APP")
    FLASK_ENV = environ.get("FLASK_ENV")
    SECRET_KEY = environ.get("SECRET_KEY")
    TEMPLATES_FOLDER = "templates"

    # login sessions
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True

    # Database
    SQLALCHEMY_DATABASE_URI = environ.get("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_size": 6,
        "pool_recycle": 120,
        "pool_pre_ping": True,
    }

    # Stripe
    STRIPE_PUBLISHABLE_KEY = environ.get("STRIPE_PUBLISHABLE_KEY")
    STRIPE_SECRET_KEY = environ.get("STRIPE_SECRET_KEY")
    STRIPE_SUBSCRIPTION_PRICE_ID = environ.get("STRIPE_SUBSCRIPTION_PRICE_ID")
    STRIPE_WEBHOOK_SECRET = environ.get("STRIPE_WEBHOOK_SECRET")
    STRIPE_ENDPOINT_SECRET = environ.get("STRIPE_ENDPOINT_SECRET")
    STRIPE_WEBHOOK_LOG = "./stripe-webhook.log"

    # Twitter/X
    TWITTER_API_KEY = environ["TWITTER_API_KEY"]
    TWITTER_API_KEY_SECRET = environ["TWITTER_API_KEY_SECRET"]
    TWITTER_CALLBACK_URL = environ["TWITTER_CALLBACK_URL"]

    # Celery
    timezone = "Europe/London"  # timezone for cron jobs
    CELERY = dict(
        broker_url=environ.get("CELERY_BROKER_URL"),
        result_backend=environ.get("CELERY_RESULT_BACKEND"),
        broker_connection_retry_on_startup=True,
        task_ignore_result=False,
        task_create_missing_queues=True,
        # The following determines what queue the tasks are on.
        # Any compute-heavy tasks should be put on "model_runner" queue.
        task_default_queue="default",
        task_routes={
            "pickr_flask.tasks.run_niche_topic_model": {
                "queue": "model_runner"
            }
        },
        # Set schedules for periodic tasks using celery beat
        beat_schedule={
            "task_update_reddit_every_morning": {
                "task": "pickr_flask.tasks.all_niches_reddit_update",
                "schedule": crontab(hour=4, minute=30),  # morning schedule
            },
            "task_run_topic_model_every_morning": {
                "task": "pickr_flask.tasks.all_niches_run_pipeline",
                "schedule": crontab(hour=5, minute=0),
            },
            "task_post_scheduled_tweets": {
                "task": "pickr_flask.tasks.post_scheduled_tweets",
                "schedule": crontab(minute="*/5"),  # every 5 min
            }
        }
    )

    # SMTP settings
    MAIL_SERVER = environ.get("MAIL_SERVER")
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USERNAME = environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = environ.get("MAIL_PASSWORD")
