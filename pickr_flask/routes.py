import json
import random
from time import time
from typing import List
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID
from typing import List

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
from sqlalchemy import Date
from .forms import LoginForm, SignupForm, TopicForm, ResetForm, SetPasswordForm
from .http import url_has_allowed_host_and_scheme
from .subscription import (
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_checkout_completed,
)
from .http import url_has_allowed_host_and_scheme
from .models import Niche, db, PickrUser, ModeledTopic, GeneratedPost, StripeSubscription, StripeSubscriptionStatus
from .forms import LoginForm, SignupForm, TopicForm
from .tasks import new_user_get_data
from .util import log_login, log_all_topics_activity, log_topic_click_activity
import random

###############################################################################
# Authentication endpoints

def is_user_stripe_subscription_active(pickr_user):
    stripe_subscription = StripeSubscriptionStatus(get_stripe_subscription_status(
        pickr_user.id))
    if stripe_subscription != StripeSubscriptionStatus.active and stripe_subscription != StripeSubscriptionStatus.trialing:

        return False
    else:
        return True

def is_user_account_valid(pickr_user):
    "check if a user is allowed to use pickr features"
    valid = True

    if is_user_older_than_14days(pickr_user) and not is_user_stripe_subscription_active(pickr_user):
        valid = False

    return valid

def is_user_older_than_14days(pickr_user):
    """Check if a users account is older than 14 days"""
    plus_14_days_old = False
    delta = datetime.today() - pickr_user.created_at

    if delta.days >= 14:
        plus_14_days_old = True

    return plus_14_days_old

def get_stripe_subscription_status(user_id):
    stripe_subscription = StripeSubscription.query.filter_by(
            user_id=user_id,
        ).first()

    if stripe_subscription is None:
        return StripeSubscriptionStatus.canceled

    retrieve_sub = stripe.Subscription.retrieve(stripe_subscription.stripe_subscription_id)
    status = retrieve_sub.status
    return status

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
            log_login(user)
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
            db.session.add(user)
            db.session.commit()

            login_user(user)
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
            msg.recipients = [existing_user.email] # existing_user.email #
            msg.sender = 'account@pickrsocial.com'
            token = get_reset_token(existing_user.username) 
            msg.html = render_template('reset_email_body.html', user=existing_user.username, token=token)
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
    return jwt.encode({'reset_password':    username,
            'exp':    time() + expires},
            algorithm='HS256',
            key=app.config['SECRET_KEY']
    )

def verify_reset_token(token):
    try:
        username = jwt.decode(token,
            key=app.config['SECRET_KEY'], algorithms=['HS256'])['reset_password']
        app.logger.info(f'reset password - username from token {username}')
    except Exception as e:
        app.logger.info(f'reset password - caught exception when trying to get token {e}')
        return
    return PickrUser.query.filter_by(username=username).first()

@app.route("/set_password/<token>", methods=["GET", "POST"])
def set_password(token):
    form = SetPasswordForm()
    user = verify_reset_token(token)
    password = form.password.data
    app.logger.info(f'reset password - new password  {password}')
    print('validate_on_submit()', form.validate_on_submit())
    if form.validate_on_submit():
        password = form.password.data
        password_hash = generate_password_hash(
                password,
                method="pbkdf2:sha512:1000",
            )
        user.password = generate_password_hash(password)
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
# TODO: implement usage limits based on subscription


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
            metadata={"user_id" : current_user.id},
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

    # log all stripe events in case we need them
    with open(app.config["STRIPE_WEBHOOK_LOG"], "a") as f:
        json.dump(event, f)
        f.write("\n")

    app.logger.info('event type')
    app.logger.info(event["type"])

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
    return render_template_string("Hello. This is a Pickr URL")


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

    topics = []
    if len(current_user.niches) == 0:
        return render_template(
            "home.html",
            title="Pickr - Your Daily Topics & Curated Tweets",
            date=datetime.today().strftime("%Y-%m-%d"),
            topics=topics,
        )
    niche_ids = [n.id for n in current_user.niches]
    print(
        "niche_ids -------------------------------------------------------",
        niche_ids,
    )

    all_topics = ModeledTopic.query.filter(ModeledTopic.niche_id.in_(niche_ids)).order_by(ModeledTopic.size.desc()).all()
    if len(all_topics) == 0:
        return render_template(
            "home.html",
            title="Pickr - Your Daily Topics & Curated Tweets",
            date=datetime.today().strftime("%Y-%m-%d"),
            topics=topics,
        )
    max_date = max([t.date.date() for t in all_topics])
    topics = [t for t in all_topics if t.date.date() == max_date][:3]
    for t in topics:
        if t.generated_posts is not None:
            print('num gen posts', len(t.generated_posts))
            print('type gen posts', type(t.generated_posts))
            print('gen posts', t.generated_posts[:2])
            random.shuffle(t.generated_posts)
            #print(posts)
            #t.generated_posts = posts

    print('unique niches in topics ', len(set([t.niche_id for t in topics])))
    '''topics = (
        ModeledTopic.query.filter(ModeledTopic.date.cast(Date) == max_date)
        .order_by(ModeledTopic.size.desc())
        .all()
    )[
        :3
    ]'''  # TODO: Should split these between niches and also max date may be different for each niche
    print("current_user.niches --------------", current_user.niches)
    return render_template(
        "home.html",
        title="Pickr - Your Daily Topics & Curated Tweets",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/all_topics")
@login_required
def all_topics():
    log_all_topics_activity(current_user)
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    topics = []
    if len(current_user.niches) == 0:
        return render_template(
            "home.html",
            title="Pickr - Your Daily Topics & Curated Tweets",
            date=datetime.today().strftime("%Y-%m-%d"),
            topics=topics,
        )

    niche_ids = [n.id for n in current_user.niches]
    all_topics = ModeledTopic.query.filter(ModeledTopic.niche_id.in_(niche_ids)).order_by(ModeledTopic.size.desc()).all()
    if len(all_topics) == 0:
        return render_template(
            "home.html",
            title="Pickr - Your Daily Topics & Curated Tweets",
            date=datetime.today().strftime("%Y-%m-%d"),
            topics=topics,
        )
    max_date = max([t.date.date() for t in all_topics])
    '''topics = (
        ModeledTopic.query.filter(ModeledTopic.date.cast(Date) == max_date)
        .order_by(ModeledTopic.size.desc())
        .all()
    )'''
    topics = [t for t in all_topics if t.date.date() == max_date]

    for t in topics:
        random.shuffle(t.generated_posts)
    return render_template(
        "all_topics.html",
        title="Pickr - Topics & Curated Tweets",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/topic/<topic_id>")
@login_required
def topic(topic_id):

    log_topic_click_activity(current_user, topic_id)

    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    try:
        uuid = UUID(topic_id, version=4)
    except ValueError:
        return abort(404)
    topic = ModeledTopic.query.get(uuid)
    generated_posts = topic.generated_posts
    return render_template(
        "topic.html",
        title="Pickr - Curated Tweets",
        topic=topic,
        posts=topic.reddit_posts,
        generated_posts=generated_posts,
    )


@app.route("/picker", methods=["GET", "POST"])
@login_required
def picker():

    """GET requests serve page for user to pick topics.
    POST requests validate form & associates topics with user.
    """
    # all_topics = Niche.query.order_by(Niche.category).all()
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    all_topics = Niche.query.order_by(Niche.title).all()
    all_topics = [n for n in all_topics if n.is_active is True and n.title != 'Empty Niche']
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
        user_custom_niches = []
        if form.custom_niche.data != "":
            user_custom_niches = form.custom_niche.data.split(",")
            user_custom_niches = [cn.strip().title() for cn in user_custom_niches]
            for n in user_custom_niches:
                current_user.niches.append(Niche(title=n))
        db.session.commit()
        # TODO: run task for new user, check celery docs
        if len(user_custom_niches) > 0:
            new_user_get_data.delay(user_custom_niches)
        return redirect(url_for("home"))

    return render_template(
        "picker.html",
        title="Pickr - Choose Your Niches",
        form=form,
        no_header=True,
        no_footer=True,
    )
