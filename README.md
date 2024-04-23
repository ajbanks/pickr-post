# topic-tweet

Automated Media Analysis and Post Generation App

## Flask
Environment should contain the following variables
```shell
SECRET_KEY
FLASK_APP
FLAKS_ENV
SQLALCHEMY_DATABASE_URI
STRIPE_PUBLISHABLE_KEY
STRIPE_SUBSCRIPTION_PRICE_ID
STRIPE_WEBHOOK_SECRET
```

Install requirements (use a venv)
```
pip install -r requirements.txt
```

Run flask app
```
flask run --debug
```

Start a flask shell with app context
```
flask shell
```

## Database
The Postgres schema is defined by SQLAlchemy ORM models in `models.py`.
Schema changes are handled by [Alembic](https://alembic.sqlalchemy.org/en/latest/). [Flask-Migrate](https://flask-migrate.readthedocs.io/en/latest/) provides convenient configuration to use with flask.


## Stripe
Subscriptions are through Stripe checkout. https://testdriven.io/blog/flask-stripe-subscriptions/ has a good summary.
