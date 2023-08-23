import json
import random
from time import time
from typing import List
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from sqlalchemy import Date, cast, and_, exc
from sqlalchemy.sql.expression import func

import jwt
import stripe
from flask import (
    flash,
    redirect,
    url_for,
    request,
    abort,
    render_template,
    render_template_string,
    jsonify,
)
from flask import current_app as app
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Mail, Message
from werkzeug.security import check_password_hash, generate_password_hash
from .forms import LoginForm, SignupForm, TopicForm, ResetForm, SetPasswordForm
from .http import url_has_allowed_host_and_scheme
from .subscription import (
    is_user_stripe_subscription_active,
    is_user_account_valid,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_checkout_completed,
)
from .models import (
    db, Niche, PickrUser,
    ModeledTopic, RedditPost
)
from .tasks import generate_niche_topics
from .util import log_user_activity

@app.errorhandler(exc.SQLAlchemyError)
def handle_db_exception(e):
    app.logger.error(e)
    db.session.rollback()


###############################################################################
# Authentication endpoints


@app.route("/favicon.ico")
def favicon():
    return url_for("static", filename="img/favicon.ico")


@app.route("/login", methods=["GET", "POST"])
def login():
    """GET requests serve Log-in page.
    POST requests validate and redirect user to home.
    """

    form = LoginForm()
    if form.validate_on_submit():
        user = PickrUser.query.filter_by(
            email=form.email.data,
        ).first()

        app.logger.info(user)
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            log_user_activity(user, "login")
            # validate redirect, if provided
            next_page = request.args.get("next")
            if next_page is not None and not url_has_allowed_host_and_scheme(
                next_page, request.host
            ):
                return abort(400)

            return redirect(next_page or url_for("home"))

        flash("Invalid username/password")
        return redirect(url_for("login"))

    return render_template(
        "login.html",
        form=form,
        title="Pickr - Log in.",
        template="login-page",
        no_header=True,
        no_footer=True,
        body="Log in with your User account.",
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """GET requests serve sign-up page.
    POST requests validate form & creates user.
    """
    form = SignupForm()
    if form.validate_on_submit():
        existing_user = PickrUser.query.filter_by(
            email=form.email.data,
        ).first()
        if existing_user is None:
            password_hash = generate_password_hash(
                form.password.data,
                method="pbkdf2:sha512:1000",
            )
            user = PickrUser(
                username=form.name.data,
                email=form.email.data,
                password=password_hash,
                created_at=datetime.now(),
            )
            app.logger.info(
                f"New user signup: username={user.username}"
            )
            db.session.add(user)
            db.session.commit()

            login_user(user)
            log_user_activity(user, "completed_signup_step_1")
            return redirect(url_for("picker"))

        flash("An account already exists with that email address.")

    return render_template(
        "signup.html",
        title="Pickr - Create an Account.",
        form=form,
        no_header=True,
        no_footer=True,
        template="signup-page",
    )


@app.route("/user")
@login_required
def user():
    return render_template(
        "user.html",
        title="Pickr - User Account",
    )

@app.route("/reset", methods=["GET", "POST"])
def reset():
    # send email
    form = ResetForm()
    if form.validate_on_submit():
        existing_user = PickrUser.query.filter_by(
            email=form.email.data,
        ).first()
        if existing_user:
            # send email
            mail = Mail(app)

            msg = Message()
            msg.subject = "Pickr Social - Reset Password"
            msg.recipients = [existing_user.email]
            msg.sender = 'account@pickrsocial.com'
            token = get_reset_token(existing_user.username)
            msg.html = render_template(
                'reset_email_body.html',
                user=existing_user.username,
                token=token
            )
            mail.send(msg)
            return render_template(
                "reset_email_sent.html",
                title="Pickr - Reset Password",
                no_header=True,
                no_footer=True,
            )

        flash("Account not found with this email.")

        
    return render_template(
        "reset.html",
        title="Pickr - Reset Password",
        form=form,
        no_header=True,
        no_footer=True,
        template="signup-page",
    )


def get_reset_token(username, expires=500):
    return jwt.encode(
        {'reset_password': username, 'exp': time() + expires},
        algorithm='HS256',
        key=app.config['SECRET_KEY']
    )


def verify_reset_token(token):
    try:
        username = jwt.decode(
            token,
            key=app.config['SECRET_KEY'],
            algorithms=['HS256']
        )['reset_password']
        app.logger.info(f'reset password - username from token {username}')
    except Exception as e:
        app.logger.error(f'reset password - caught exception when trying to get token {e}')
        return
    return PickrUser.query.filter_by(username=username).first()


@app.route("/set_password/<token>", methods=["GET", "POST"])
def set_password(token):
    form = SetPasswordForm()
    user = verify_reset_token(token)
    password = form.password.data
    app.logger.info(f'reset password - new password  {password}')
    if form.validate_on_submit():
        password = form.password.data
        password_hash = generate_password_hash(
                password,
                method="pbkdf2:sha512:1000",
            )
        user.password = password_hash
        db.session.add(user)
        db.session.commit()
        app.logger.info(f'reset password - password is set for {user.username}')
        return redirect(url_for("login"))

    # verify that the token is valid for the user
    if not user:
        app.logger.info('reset password - user not found')
        return redirect(url_for("login"))

    app.logger.info(f'hasnt gone in to submit')
    return render_template(
        "set_password.html",
        title="Pickr - Reset Password",
        form=form,
        no_header=True,
        no_footer=True,
        template="signup-page",
    )


@app.route("/logout", methods=["GET"])
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


###############################################################################
# Stripe endpoints

# TODO: show user subscription status
# TODO: ability to cancel subscription


@app.route("/stripe-pub-key", methods=["GET"])
def stripe_pub_key():
    return jsonify({"publicKey": app.config["STRIPE_PUBLISHABLE_KEY"]})


@app.route("/checkout-session", methods=["GET"])
@login_required
def stripe_checkout_session():
    """
    Creates a stripe checkout session for subscriptions.
    Client opens checkout using the session generated here, and
    server listens for webhook to confirm payment.
    """
    try:
        root_url = request.url_root.rstrip("/")
        success_url = (
            root_url
            + url_for("stripe_checkout_success")
            + "?session_id={CHECKOUT_SESSION_ID}"
        )
        cancel_url = root_url + url_for("stripe_checkout_cancel")
        checkout_session = stripe.checkout.Session.create(
            client_reference_id=current_user.id,
            success_url=success_url,
            cancel_url=cancel_url,
            payment_method_types=["card"],
            subscription_data={},
            payment_method_collection="if_required",
            mode="subscription",
            metadata={"user_id": current_user.id},
            line_items=[
                {
                    "price": app.config["STRIPE_SUBSCRIPTION_PRICE_ID"],
                    "quantity": 1,
                }
            ],
        )

    except Exception as e:
        app.logger.error(e)
        return jsonify(error=str(e)), 400
    return jsonify({"sessionId": checkout_session["id"]})


@app.route("/checkout-success")
def stripe_checkout_success():
    app.logger.info('stripe_checkout_success activated ')
    return render_template("success.html")


@app.route("/checkout-cancel")
def stripe_checkout_cancel():
    app.logger.info('stripe_checkout_cancelled')
    return render_template("cancel.html")


@app.route("/webhooks", methods=["POST"])
def webhook():
    """
    Handles webhook events from stripe, cf https://stripe.com/docs/webhooks
    """

    payload = request.get_data(as_text=True)
    stripe_header = request.headers.get("Stripe-Signature")
    app.logger.info('stripe_webhook activated')
    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_header,
            app.config["STRIPE_ENDPOINT_SECRET"],
        )
    except stripe.error.SignatureVerificationError as e:
        app.logger.info('webhook SignatureVerificationError')
        return jsonify(error=str(e)), 400
    except ValueError:
        app.logger.info('webhook ValueError')
        return jsonify(error="Invalid payload"), 400

    app.logger.info(f'stripe event type: {event["type"]}')

    if event["type"] == "checkout.session.completed":
        app.logger.info('checkout.session.completed')
        handle_checkout_completed(event)
    elif event["type"] == "customer.subscription.created":
        app.logger.info('customer.subscription.created')
        # handle_subscription_created(event)
    elif event["type"] == "customer.subscription.updated":
        app.logger.info('customer.subscription.updated')
        handle_subscription_updated(event)
    elif event["type"] == "customer.subscription.deleted":
        app.logger.info('customer.subscription.deleted')
        handle_subscription_deleted(event)

    return jsonify(success=True)


###############################################################################
# Main app page routes


@app.route("/")
@login_required
def index():
    return redirect(url_for("home"))


@app.route("/upgrade")
def upgrade():
    if is_user_stripe_subscription_active(current_user):
        return render_template("success.html")
    else:
        return render_template("upgrade.html")


@dataclass
class UITopic:
    name: str
    description: str
    generated_posts: List[str]


@app.route("/home")
@login_required
def home():
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))
    log_user_activity(current_user, "home")
    niche_ids = [n.id for n in current_user.niches]
    topics = ModeledTopic.query.filter(
        and_(
            ModeledTopic.niche_id.in_(niche_ids)
        )
    ).order_by(
        ModeledTopic.date.desc(),
        ModeledTopic.size.desc()
    ).limit(3).all()

    for t in topics:
        random.shuffle(t.generated_posts)

    # TODO: Should split these between niches and also max date may
    # be different for each niche
    return render_template(
        "home.html",
        title="Pickr - Your Daily Topics & Curated Tweets",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/all_topics")
@login_required
def all_topics():
    log_user_activity(current_user, "all_topics")
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    niche_ids = [n.id for n in current_user.niches]

    '''topics = ModeledTopic.query.filter(
        and_(
            ModeledTopic.niche_id.in_(niche_ids),
            ModeledTopic.date > datetime.now().date()
        )
    ).order_by(
        ModeledTopic.size.desc()
    ).all()

    for t in topics:
        random.shuffle(t.generated_posts)'''

    topics = []
    for n in niche_ids:
        max_date = ModeledTopic.query.filter(
            ModeledTopic.niche_id.in_(niche_ids),
            ).order_by(
                ModeledTopic.date
        ).first().date.date()
        topics += ModeledTopic.query.filter(
            and_(
                ModeledTopic.niche_id.in_([n]),
                cast(ModeledTopic.date, Date) == max_date
            )
        ).order_by(
            ModeledTopic.size.desc()
        ).all()

        for t in topics:
            random.shuffle(t.generated_posts)
    return render_template(
        "all_topics.html",
        title="Pickr - Topics & Generated Tweets",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/topic/<topic_id>")
@login_required
def topic(topic_id):

    log_user_activity(current_user, f"topic_click:{topic_id} ")

    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    try:
        uuid = UUID(topic_id, version=4)
    except ValueError:
        return abort(404)
    topic = ModeledTopic.query.get(uuid)
    if topic is None:
        return abort(404)

    generated_posts = topic.generated_posts
    posts = RedditPost.query.filter(
        and_(
            RedditPost.modeled_topic_id == uuid,
            func.length(RedditPost.body) > 10
        )
    ).order_by(
        RedditPost.score
    ).limit(30).all()

    return render_template(
        "topic.html",
        title="Pickr - Curated Tweets",
        topic=topic,
        posts=posts,
        generated_posts=generated_posts,
    )


@app.route("/picker", methods=["GET", "POST"])
@login_required
def picker():
    """GET requests serve page for user to pick topics.
    POST requests validate form & associates topics with user.
    """
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    all_topics = Niche.query.filter(
        Niche.is_active
    ).order_by(
        Niche.title
    ).all()

    form = TopicForm()
    choices = [("", "")] + [(t.id, t.title) for t in all_topics]
    form.topic_1.choices = choices
    form.topic_2.choices = choices
    form.topic_3.choices = choices

    if form.validate_on_submit():
        topic_ids = [t.data for t in [form.topic_1, form.topic_2, form.topic_3]]
        try:
            ids = [UUID(tid) for tid in topic_ids if tid != ""]
        except ValueError:
            app.logger.error()
            return abort(400)

        current_user.niches = list(filter(lambda t: t.id in ids, all_topics))

        # TODO: form.custom_niche.data needs to be sanitized/processed
        custom_niches = []
        if form.custom_niche.data != "":
            custom_niche_names = [
                cn.strip().title() for cn in
                form.custom_niche.data.split(",")
            ]
            for n in custom_niche_names:
                # Save niche and start task to generate GPT topics for it
                custom_niche = Niche(title=n, is_active=False, is_custom=True)
                current_user.niches.append(custom_niche)
                custom_niches.append(custom_niche)
                db.session.commit()

                generate_niche_topics.apply_async(
                    args=(custom_niche.id,)
                )
        log_user_activity(current_user, "completed_signup_step_2")
        return redirect(url_for("home"))

    return render_template(
        "picker.html",
        title="Pickr - Choose Your Niches",
        form=form,
        no_header=True,
        no_footer=True,
    )
