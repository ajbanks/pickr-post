from flask import redirect, url_for

from . import login_manager
from .models import PickrUser


@login_manager.user_loader
def load_user(user_id):
    if user_id is not None:
        return PickrUser.query.get(user_id)
    return None


@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for("login"))
