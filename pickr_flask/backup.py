from typing import List
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID
from typing import List

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
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func, Date
from .forms import LoginForm, SignupForm, TopicForm
from .http import url_has_allowed_host_and_scheme
from .subscription import (
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
    handle_checkout_completed,
)
from .http import url_has_allowed_host_and_scheme
from .models import Niche, db, PickrUser, ModeledTopic, GeneratedPost
from .forms import LoginForm, SignupForm, TopicForm
from .tasks import new_user_get_data


###############################################################################
# Authentication endpoints


@app.route("/login", methods=["GET", "POST"])
def login():
    """GET requests serve Log-in page.
    POST requests validate and redirect user to home.
    """
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    form = LoginForm()
    if form.validate_on_submit():
        user = PickrUser.query.filter_by(
            email=form.email.data,
        ).first()

        app.logger.info(user)
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)

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
        title="Log in.",
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
    if current_user.is_authenticated:
        return redirect(url_for("home"))

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
        title="Create an Account.",
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
        title="User Account",
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
            mode="subscription",
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
    if current_user.is_authenticated:
        app.logger.info("/checkout-success: User %s", str(current_user))

    # TODO: payment confirmation message
    return redirect(url_for("home"))


@app.route("/checkout-cancel")
def stripe_checkout_cancel():
    return redirect(url_for("home"))


@app.route("/stripe-webhook", methods=["POST"])
def stripe_webhook():
    """
    Handles webhook events from stripe, cf https://stripe.com/docs/webhooks
    """
    payload = request.get_data(as_text=True)
    stripe_header = request.headers.get("Stripe-Signature")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            stripe_header,
            app.config["STRIPE_WEBHOOK_SECRET"],
        )
    except stripe.error.SignatureVerificationError as e:
        return jsonify(error=str(e)), 400
    except ValueError:
        return jsonify(error="Invalid payload"), 400

    # log all stripe events in case we need them
    with open(app.config["STRIPE_WEBHOOK_LOG"], "a") as f:
        json.dump(event, f)
        f.write("\n")

    if event["type"] == "checkout.session.completed":
        handle_checkout_completed(event)
    elif event["type"] == "customer.subscription.created":
        handle_subscription_created(event)
    elif event["type"] == "customer.subscription.updated":
        handle_subscription_updated(event)
    elif event["type"] == "customer.subscription.deleted":
        handle_subscription_deleted(event)

    return jsonify(success=True)


###############################################################################
# Main app page routes


@app.route("/")
@login_required
def index():
    return render_template_string("Hello")


@app.route("/upgrade")
def upgrade():
    return render_template("upgrade.html")


@dataclass
class UITopicGen:
    title: str
    desription: str
    generated_posts: List[str]


@dataclass
class UITopic:
    title: str
    desription: str


@app.route("/home")
@login_required
def home():

    if not current_user.is_authenticated:
        return redirect(url_for("upgrade"))

    print("current_user.niches --------------", current_user.niches)
    topics = []
    if len(current_user.niches) > 0:
        niche_ids = [n.id for n in current_user.niches]
        print(
            "niche_ids -------------------------------------------------------",
            niche_ids,
        )
        print(type(niche_ids[0]))
        all_topics = ModeledTopic.query.filter(
            ModeledTopic.niche_id.in_(niche_ids)
        ).all()  # ModeledTopic.query.filter(ModeledTopic.niche_id.in_(niche_ids)).all()
        max_date = max([t.date.date() for t in all_topics])
        print("max date", max_date)
        modelled_topics = (
            ModeledTopic.query.filter(ModeledTopic.date.cast(Date) == max_date)
            .order_by(ModeledTopic.size)
            .all()
        )[:3]
        print("len mt", len(modelled_topics))

        for mt in modelled_topics:
            generated_posts = GeneratedPost.query.filter(
                GeneratedPost.modeled_topic_id == mt.id
            ).all()
            topics.append(UITopicGen(mt.name, mt.description, generated_posts))
        print("len topics", len(topics))

    return render_template(
        "home.html",
        title="Your Daily Topics",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/all_topics")
@login_required
def all_topics():
    topics = []
    if len(current_user.niches) > 0:
        niche_ids = [n.id for n in current_user.niches]
        # topics = ModeledTopic.query.filter(ModeledTopic.niche_id.in_(niche_ids)).all()
        all_topics = (
            ModeledTopic.query.filter(ModeledTopic.niche_id.in_(niche_ids))
            .order_by(ModeledTopic.size)
            .all()
        )
        for t in all_topics:
            topics.append([UITopic(t.name, t.description)])
    print("current_user.niches --------------", current_user.niches)
    return render_template(
        "home.html",
        title="Your Daily Topics",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
    )


@app.route("/topic/<topic_id>")
@login_required
def topic(topic_id):
    try:
        uuid = UUID(topic_id, version=4)
    except ValueError:
        return abort(404)
    topic = ModeledTopic.query.get(uuid)
    generated_posts = topic.generated_posts

    return render_template(
        "topic.html",
        topic=topic,
        tweets=topic.tweets,
        generated_posts=generated_posts,
    )


@app.route("/picker", methods=["GET", "POST"])
@login_required
def picker():
    """GET requests serve page for user to pick topics.
    POST requests validate form & associates topics with user.
    """
    # all_topics = Niche.query.order_by(Niche.category).all()
    all_topics = Niche.query.all()
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
        if form.custom_niche.data != "":
            current_user.niches.append(Niche(title=form.custom_niche.data))
        db.session.commit()
        # TODO: run task for new user, check celery docs
        new_user_get_data.apply_async(list(filter(lambda t: t.id in ids, all_topics)))
        return redirect(url_for("home"))

    return render_template(
        "picker.html",
        title="Choose Your Niches",
        form=form,
        no_header=True,
        no_footer=True,
    )
