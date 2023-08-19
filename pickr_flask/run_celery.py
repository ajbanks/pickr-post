'''
This is the entrypoint for celery workers
'''
from . import init_app

flask_app = init_app()
celery_app = flask_app.extensions["celery"]
