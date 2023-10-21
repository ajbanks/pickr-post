from time import time

import jwt
from flask import redirect, url_for

from . import login_manager
from .models import PickrUser

PASSWORD_HASH_METHOD = "pbkdf2:sha512:1000"

@login_manager.user_loader
def load_user(user_id):
    if user_id is not None:
        return PickrUser.query.get(user_id)
    return None


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for("login"))


def get_reset_token(username, secret_key, expires=500):
    return jwt.encode(
        {'reset_password': username, 'exp': time() + expires},
        algorithm='HS256',
        key=secret_key,
    )


def verify_reset_token(token, secret_key):
    username = jwt.decode(
        token,
        key=secret_key,
        algorithms=['HS256']
    )['reset_password']
    return PickrUser.query.filter_by(username=username).first()
