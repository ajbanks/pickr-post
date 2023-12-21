'''
Flask application factory
'''
from os import path, pardir, environ
from dotenv import load_dotenv

import stripe
from celery import Celery, Task
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_wtf import CSRFProtect

# load .env from repository root
basedir = path.abspath(path.join(path.dirname(__file__), pardir))
load_dotenv(path.join(basedir, ".env"))

login_manager = LoginManager()
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

# task_queue = Celery(__name__, broker=celery_broker_url)


def celery_init_app(app: Flask) -> Celery:
    '''
    Initialize celery and load it as flask app extension.
    This method of configuring celery is from
    https://flask.palletsprojects.com/en/2.2.x/patterns/celery/
    '''
    class FlaskTask(Task):
        def __call__(self, *args: object, **kwargs: object) -> object:
            with app.app_context():
                return self.run(*args, **kwargs)

    celery_app = Celery(app.name, task_cls=FlaskTask)
    celery_app.config_from_object(app.config["CELERY"])
    celery_app.set_default()
    app.extensions["celery"] = celery_app
    return celery_app


def init_app() -> Flask:
    '''
    Initialize flask app and extensions.
    This uses the application factory pattern that's conventional for Flask.
    '''
    app = Flask(__name__)

    if environ.get("ENV") == "DEV":
        app.config.from_object("config.DevConfig")
        app.logger.info("DEV config loaded")
    else:
        app.config.from_object("config.Config")
        app.logger.info("PROD config loaded")

    celery_init_app(app)
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    stripe.api_key = app.config["STRIPE_SECRET_KEY"]
    with app.app_context():
        from .models import PickrUser  # noqa: disable=F401
        from . import auth, routes, util  # noqa: disable=F401

        # db.create_all()
        return app
