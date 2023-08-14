from os import environ, path
from dotenv import load_dotenv

basedir = path.abspath(path.dirname(__file__))
load_dotenv(path.join(basedir, ".env"))

# TODO: split into dev/prod configs


class Config:
    # Flask
    FLASK_APP = environ.get("FLASK_APP")
    FLASK_ENV = environ.get("FLASK_ENV")
    SECRET_KEY = environ.get("SECRET_KEY")
    TEMPLATES_FOLDER = "templates"

    # login sessions #TODO when ready for produciton uncomment cookie settings
    # SESSION_COOKIE_SAMESITE = "strict"
    # SESSION_COOKIE_SECURE = True
    # REMEMBER_COOKIE_SAMESITE = "strict"
    # REMEMBER_COOKIE_SECURE = True

    # Database
    SQLALCHEMY_DATABASE_URI = environ.get("SQLALCHEMY_DATABASE_URI")
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
    }

    # Stripe
    STRIPE_PUBLISHABLE_KEY = environ.get("STRIPE_PUBLISHABLE_KEY")
    STRIPE_SECRET_KEY = environ.get("STRIPE_SECRET_KEY")
    STRIPE_SUBSCRIPTION_PRICE_ID = environ.get("STRIPE_SUBSCRIPTION_PRICE_ID")
    STRIPE_WEBHOOK_SECRET = environ.get("STRIPE_WEBHOOK_SECRET")
    STRIPE_ENDPOINT_SECRET = environ.get("STRIPE_ENDPOINT_SECRET")
    STRIPE_WEBHOOK_LOG = "./stripe-webhook.log"

    # timezone for cron jobs
    timezone = "Europe/London"
    
    # Celery for redis broker address - this requires a working redis server
    CELERY_BROKER_URL = environ.get("CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND = environ.get("CELERY_RESULT_BACKEND")

    # SMTP settings
    MAIL_SERVER = environ.get("MAIL_SERVER")
    MAIL_PORT = 465
    MAIL_USE_SSL = True
    MAIL_USERNAME = environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = environ.get("MAIL_PASSWORD")
