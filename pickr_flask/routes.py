import random
import datetime as dt
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID
from zoneinfo import ZoneInfo

import stripe
import tweepy
from flask import Markup, abort
from flask import current_app as app
from flask import (flash, jsonify, redirect, render_template,
                   render_template_string, request, url_for)
from flask_login import current_user, login_required, login_user, logout_user
from flask_mail import Mail, Message
from flask_wtf.csrf import CSRFError
from sqlalchemy import Date, and_, cast, exc
from werkzeug.security import check_password_hash, generate_password_hash
from topic_model.topic import generate_informative_tweets_from_long_content
from .auth import PASSWORD_HASH_METHOD, get_reset_token, verify_reset_token
from .constants import (DATETIME_FRIENDLY_FMT, DATETIME_ISO_FMT,
                        MAX_FUTURE_SCHEDULE_DAYS, MAX_TWEET_LEN)
from .forms import LoginForm, ResetForm, SetPasswordForm, SignupForm, TopicForm, BlogForm
from .http import url_has_allowed_host_and_scheme
from .models import (GeneratedPost, ModeledTopic, Niche, OAuthSession,
                     PickrUser, PostEdit, RedditPost, Schedule, ScheduledPost,
                     db)
from .queries import (get_scheduled_post, latest_post_edit,
                      oauth_session_by_token, oauth_session_by_user,
                      reddit_posts_for_topic_query, top_modeled_topic_query,
                      top_trending_modeled_topic_query)
from .subscription import (handle_checkout_completed,
                           handle_subscription_deleted,
                           handle_subscription_updated, is_user_account_valid,
                           is_user_stripe_subscription_active)
from .tasks import generate_niche_gpt_topics, create_schedule
from .util import log_user_activity, render_post_html_from_id, urlsafe_uuid
from .twitter import X_Caller

TWITTER_STATUS_URL = "https://twitter.com/i/status"
TWITTER_INTENTS_URL = "https://twitter.com/intent/tweet"


###############################################################################
# Error handlers

@app.errorhandler(CSRFError)
def handle_csrf_error(e):
    app.logger.error(e)
    abort(400)


@app.errorhandler(exc.SQLAlchemyError)
def handle_db_exception(e):
    app.logger.error(e)
    db.session.rollback()


###############################################################################
# Authentication endpoints

@app.route("/twitter/auth", methods=["GET"])
def twitter_auth():
    oauth_handler = tweepy.OAuth1UserHandler(
        app.config["TWITTER_API_KEY"],
        app.config["TWITTER_API_KEY_SECRET"],
        callback=app.config["TWITTER_CALLBACK_URL"],
    )
    oauth_url = oauth_handler.get_authorization_url()
    oauth_token = oauth_handler.request_token["oauth_token"]
    oauth_token_secret = oauth_handler.request_token["oauth_token_secret"]
    oauth_sess = OAuthSession(
        oauth_token=oauth_token,
        oauth_token_secret=oauth_token_secret,
        user_id=current_user.id,
        created_at=datetime.now(),
    )
    db.session.add(oauth_sess)
    db.session.commit()

    return redirect(oauth_url, 302)


@app.route("/twitter/callback", methods=["GET"])
@login_required
def twitter_callback():
    '''
    GET serves callback endpoint for Twitter 3-legged auth.
        It obtains access token for the user and saves it in DB.
        cf. https://docs.tweepy.org/en/stable/authentication.html#legged-oauth
    '''
    denied = request.args.get("denied")
    if denied is not None:
        app.logger.info(
            f"Twitter OAuth denied: username={current_user.username}"
        )
        return redirect(url_for("home"))

    oauth_token = request.args.get("oauth_token")
    oauth_verifier = request.args.get("oauth_verifier")
    if oauth_token == "" or oauth_verifier == "":
        app.logger.error("OAuth parameters not found")
        return redirect(url_for("home"))

    oauth_sess = oauth_session_by_token(oauth_token)
    if oauth_sess is None:
        app.logger.error(f"no OAuth session found for token={oauth_token}")
        return redirect(url_for("home"))

    oauth_handler = tweepy.OAuth1UserHandler(
        app.config["TWITTER_API_KEY"],
        app.config["TWITTER_API_KEY_SECRET"],
        callback=app.config["TWITTER_CALLBACK_URL"],
    )
    oauth_handler.request_token = {
        "oauth_token": oauth_sess.oauth_token,
        "oauth_token_secret": oauth_sess.oauth_token_secret,
    }

    try:
        access_token, access_token_secret = (
            oauth_handler.get_access_token(oauth_verifier)
        )
    except tweepy.errors.TweepyException as e:
        app.logger.error(
            f"failed to get access token for {current_user.username}: {e}"
        )
        return redirect(url_for("home"))

    oauth_sess.access_token = access_token
    oauth_sess.access_token_secret = access_token_secret
    db.session.add(oauth_sess)
    db.session.commit()

    return redirect(url_for("home"))


@app.route("/favicon.ico")
def favicon():
    return url_for("static", filename="img/favicon.ico")


@app.route("/login", methods=["GET", "POST"])
def login():
    """
    GET requests serve Log-in page.
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
    """
    GET requests serve sign-up page.
    POST requests validate form & creates user.
    """
    form = SignupForm()
    if form.validate_on_submit():
        existing_user = PickrUser.query.filter_by(
            email=form.email.data,
        ).first()
        if existing_user is None:
            password_hash = generate_password_hash(
                form.password.data, method=PASSWORD_HASH_METHOD
            )

            try:
                # get the twitter id for this users username
                x_caller = X_Caller()
                user_twitter_id = x_caller.return_twitterid(form.name.data)
                # pull tweets from their timeline excluding their retweets
                tweets = x_caller.get_tweets_for_tone_matching(user_twitter_id)[:5000]
            except Exception:
                tweets = ''

            user = PickrUser(
                username=form.name.data,
                email=form.email.data,
                password=password_hash,
                created_at=datetime.now(),
                tweet_examples=tweets
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

@app.route("/posts_from_blog", methods=["GET", "POST"])
@login_required
def posts_from_blog():
    # send email
    form = BlogForm()
    if form.validate_on_submit():

        public_statements = "Here are your generated posts: \n\n\n\n" + generate_informative_tweets_from_long_content(form.blog_input.data)

        return render_template("posts_from_blog.html", title="Pickr - blog to social posts", form=form, name=public_statements)

    return render_template("posts_from_blog.html", title="Pickr - blog to social posts", form=form, name="*created content will appear here*")

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
            token = get_reset_token(existing_user.username, app.config["SECRET_KEY"])
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


@app.route("/set_password/<token>", methods=["GET", "POST"])
def set_password(token):
    form = SetPasswordForm()
    user = verify_reset_token(token, app.config["SECRET_KEY"])
    password = form.password.data
    app.logger.info(f'reset password - new password  {password}')
    if form.validate_on_submit():
        password = form.password.data
        password_hash = generate_password_hash(
            password, method=PASSWORD_HASH_METHOD
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
    GET creates a stripe checkout session for subscriptions.
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
    POST handles webhook events from stripe
    cf https://stripe.com/docs/webhooks
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


@app.route("/home", methods=["GET"])
@login_required
def home():
    app.logger.info("log users activity")
    log_user_activity(current_user, "home")
    app.logger.info("get auth session")
    oauth = oauth_session_by_user(current_user.id)
    if oauth is None or oauth.access_token is None:
        app.logger.info("auth session doesnt exist so rendering markup")
        msg = render_template_string('''
        <a href="{{ url_for("twitter_auth") }}">Sign in with Twitter</a>
        to schedule tweets.
        ''')
        flash(Markup(msg))
    app.logger.info("check if ysers account is valid")
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))
    # TODO: fix bad query patterns (N+1 select)

    app.logger.info("get users niches, trending topics and topics ids")
    niche_ids = [n.id for n in current_user.niches]
    topics = top_trending_modeled_topic_query(niche_ids).limit(3).all()
    topic_ids = [urlsafe_uuid.encode(t.id) for t in topics]

    app.logger.info("get users schedule")
    try:
        app.logger.info(f'user id: {current_user}')
        schedule = Schedule.query.filter_by(
            user_id=current_user.id,
        ).order_by(
            Schedule.created_at.desc()
        ).limit(1).one()
        app.logger.info(f'schedule date {schedule.created_at}, {schedule.id}')
    except Exception as e:
        app.logger.info(f"user doesnt have a schedule or couldnt be retrieved {e}")
        return render_template(
            "home.html",
            schedule_text="Your schedule is being created. Refresh inb 5 minutes",
            week_date=(dt.datetime.today() - dt.timedelta(days=dt.datetime.today().weekday() % 7)).strftime("%Y-%m-%d"),
            topics=topics,
            topic_ids=topic_ids
        )

    app.logger.info("get html of schedle")
    # schedule_frag = weekly_post()

    app.logger.info("exit home function")
    return render_template(
        "home.html",
        schedule_text=schedule.schedule_text,
        week_date=(dt.datetime.today() - dt.timedelta(days=dt.datetime.today().weekday() % 7)).strftime("%Y-%m-%d"),
        topics=topics,
        topic_ids=topic_ids
    )


@app.route("/weekly_post/<week_day>", methods=["GET"])
@login_required
def weekly_post(week_day: int = None):
    try:
        if week_day is None or int(week_day) == -1:
            week_day = datetime.now().isocalendar().weekday - 1
        else:
            week_day = int(week_day)
        # TODO: fix bad query patterns (N+1 select)
        schedule = Schedule.query.filter_by(
            user_id=current_user.id,
        ).order_by(
            Schedule.created_at.desc()
        ).limit(1).one()
        if schedule is None:
            return None
        # show posts in this "Schedule" that are for this weekday
        scheduled_posts = filter(
            lambda p: p.scheduled_day == week_day,
            schedule.scheduled_posts
        )
        # TODO: find a way to get the user's timezone here
        timezone = ZoneInfo("UTC")
        now = datetime.now(tz=timezone)

        post_html_fragments = []
        for post in scheduled_posts:
            default_dt = now.replace(hour=post.scheduled_hour, minute=0)
            post_html_fragments.append(
                render_post_html_from_id(
                    post.generated_post_id,
                    current_user.id,
                    default_time=default_dt.strftime(DATETIME_ISO_FMT),
                )
            )
        days_bool = ['"false"', '"false"', '"false"', '"false"', '"false"', '"false"', '"false"']
        class_sel = ['', '', '', '', '', '', '', ]
        class_sel[week_day] = 'class="selected"'
        # days_bool[week_day] = '"true"'
        post_html_fragment = "\n".join(post_html_fragments)
        schedule_html = f"""
            <div class="tab-list" role="tablist">
                <button hx-get="/weekly_post/0" hx-target="#tabs" role="tab" aria-selected={days_bool[0]} aria-controls="tab-content" {class_sel[0]}>Mon</button>
                <button hx-get="/weekly_post/1" hx-target="#tabs" role="tab" aria-selected={days_bool[1]} aria-controls="tab-content" {class_sel[1]}>Tue</button>
                <button hx-get="/weekly_post/2" hx-target="#tabs" role="tab" aria-selected={days_bool[2]} aria-controls="tab-content" {class_sel[2]}>Wed</button>
                <button hx-get="/weekly_post/3" hx-target="#tabs" role="tab" aria-selected={days_bool[2]} aria-controls="tab-content" {class_sel[3]}>Thur</button>
                <button hx-get="/weekly_post/4" hx-target="#tabs" role="tab" aria-selected={days_bool[4]} aria-controls="tab-content" {class_sel[4]}>Fri</button>
                <button hx-get="/weekly_post/5" hx-target="#tabs" role="tab" aria-selected={days_bool[5]} aria-controls="tab-content" {class_sel[5]}>Sat</button>
                <button hx-get="/weekly_post/6" hx-target="#tabs" role="tab" aria-selected={days_bool[6]} aria-controls="tab-content" {class_sel[6]}>Sun</button>
            </div>
            
            <div class="container cards" id="tab-content" role="tabpanel">
                {post_html_fragment}
            </div>
        """
    except Exception:
        return None
    return schedule_html


@app.route("/all_topics")
@login_required
def all_topics():
    log_user_activity(current_user, "all_topics")
    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    niche_ids = [n.id for n in current_user.niches]
    topics = []
    topic_ids = []
    try:

        for n in niche_ids:
            max_date = ModeledTopic.query.filter(
                ModeledTopic.niche_id.in_(niche_ids),
            ).order_by(
                ModeledTopic.date.desc()
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
        topics = sorted(topics, key=lambda t: t.size, reverse=True)
        topic_ids = [urlsafe_uuid.encode(t.id) for t in topics]
    except Exception as e:
        print(e)
        pass
    return render_template(
        "all_topics.html",
        title="Pickr - Topics & Generated Tweets",
        date=datetime.today().strftime("%Y-%m-%d"),
        topics=topics,
        topic_ids=topic_ids,
    )


@app.route("/topic/<topic_id>")
@login_required
def topic(topic_id):
    log_user_activity(current_user, f"topic_click:{topic_id} ")

    try:
        topic_id = urlsafe_uuid.decode(topic_id)
    except ValueError:
        abort(404)

    if not is_user_account_valid(current_user):
        return redirect(url_for("upgrade"))

    topic = ModeledTopic.query.get(topic_id)
    if topic is None:
        return abort(404)

    generated_posts = topic.generated_posts
    posts = (
        reddit_posts_for_topic_query(topic.id)
            .order_by(RedditPost.score)
            .limit(20)
            .all()
    )

    # generated posts HTML is rendered separately
    posts_html_fragment = "\n".join([
        render_post_html_from_id(p.id, current_user.id)
        for p in generated_posts
    ])

    return render_template(
        "topic.html",
        title="Pickr - Curated Tweets",
        topic=topic,
        posts=posts,
        generated_posts_fragment=posts_html_fragment
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
    marketing_choice, entrep_choice, pers_dev_choice = [("", "")], [("", "")], [("", "")] 
    for tt in all_topics:
        if tt.title == 'Marketing':
            marketing_choice = (tt.id, tt.title)
        elif tt.title == 'Entrepreneurship':
            entrep_choice =(tt.id, tt.title)
        elif tt.title == 'Personal Development':
            pers_dev_choice = (tt.id, tt.title)

    choices = [("", "")] + [(t.id, t.title) for t in all_topics]
    form.topic_1.choices = [marketing_choice] + choices
    form.topic_2.choices = [entrep_choice] + choices
    form.topic_3.choices = [pers_dev_choice] + choices

    if form.validate_on_submit():
        app.logger.info('Pressed submit button on niche selection page')
        print('Pressed submit button on niche selection page')
        topic_ids = [t.data for t in [form.topic_1, form.topic_2, form.topic_3]]
        try:
            ids = [UUID(tid) for tid in topic_ids if tid != ""]
        except ValueError:
            return abort(400)

        current_user.niches = list(filter(lambda t: t.id in ids, all_topics))

        # TODO: form.custom_niche.data needs to be sanitized/processed
        custom_niches = []
        if form.custom_niche.data != "":
            print("user has custom niches")
            custom_niche_names = [
                cn.strip().title() for cn in
                form.custom_niche.data.split(",")
            ]
            print('processing custom niches')
            for n in custom_niche_names:
                # Save niche and start task to generate GPT topics for it
                print('add custom niche')
                custom_niche = Niche(title=n, is_active=False, is_custom=True)
                current_user.niches.append(custom_niche)
                custom_niches.append(custom_niche)
                db.session.commit()

                print('Generate gpt topics for custom niche', custom_niche.title)
                #generate_niche_gpt_topics(custom_niche.id)
                generate_niche_gpt_topics.apply_async(
                    args=(custom_niche.id,)
                )
        db.session.commit()
        app.logger.info('Creating schedule')
        print('Creating schedule')
        create_schedule(current_user.id)
        log_user_activity(current_user, "completed_signup_step_2")
        return redirect(url_for("home"))
    # end POST

    return render_template(
        "picker.html",
        title="Pickr - Choose Your Niches",
        form=form,
        no_header=True,
        no_footer=True,
    )


@app.route("/schedule", methods=["GET"])
@login_required
def schedule():
    '''
    GET serves a page that shows user's scheduled and posted tweets.
    '''
    scheduled_posts = (
        GeneratedPost.query.join(ScheduledPost)
            .filter(GeneratedPost.id == ScheduledPost.generated_post_id)
            .filter(
            and_(ScheduledPost.user_id == current_user.id,
                 ~ScheduledPost.scheduled_for.is_(None),
                 ScheduledPost.posted_at.is_(None))
        )
            .order_by(ScheduledPost.scheduled_for.desc())
            .all()
    )

    tweeted_posts = (
        GeneratedPost.query.join(ScheduledPost).filter(GeneratedPost.id == ScheduledPost.generated_post_id)
            .filter(
            and_(ScheduledPost.user_id == current_user.id,
                 ~ScheduledPost.posted_at.is_(None))
        ).order_by(ScheduledPost.posted_at.desc())
            .limit(20)
            .all()
    )

    # TODO: load more posted tweets history

    scheduled_html_fragment = "\n".join([
        render_post_html_from_id(gp.id, current_user.id)
        for gp in scheduled_posts
    ])
    tweeted_html_fragment = "\n".join([
        render_post_html_from_id(gp.id, current_user.id)
        for gp in tweeted_posts
    ])

    return render_template(
        "schedule.html",
        scheduled_posts_fragment=scheduled_html_fragment,
        tweeted_posts_fragment=tweeted_html_fragment,
    )


def get_generated_post_or_abort(uuid: UUID):
    generated_post = GeneratedPost.query.get(uuid)
    if generated_post is None:
        return abort(404)
    return generated_post


def validate_generated_post_id(post_id: str) -> UUID:
    '''
    Validate URL encoded UUID and return decoded ID.
    Abort if invalid ID or generated post doesn't exist.
    '''
    try:
        decoded_id = urlsafe_uuid.decode(post_id)
    except ValueError:
        return abort(400)
    exists = (
            db.session.query(GeneratedPost.id)
            .filter_by(id=decoded_id)
            .first()
            is not None
    )
    if not exists:
        return abort(400)
    return decoded_id


###############################################################################
# HTMX endpoints


@app.route("/post/<post_id>/edit", methods=["GET"])
@login_required
def edit_post(post_id):
    '''
    GET returns an HTML fragment for editing the post.
    '''
    post_id = validate_generated_post_id(post_id)
    return render_post_html_from_id(
        post_id,
        current_user.id,
        template_name="edit_post.html"
    )


@app.route("/post/<post_id>", methods=["GET", "PUT"])
@login_required
def post(post_id):
    '''
    GET requests return HTML fragment for given post.
    PUT requests edit the post's text and return the edited HTML fragment.
    '''
    post_id = validate_generated_post_id(post_id)
    generated_post = get_generated_post_or_abort(post_id)

    if request.method == "GET":
        return render_post_html_from_id(generated_post.id, current_user.id)

    if request.method == "PUT":
        edit_text = request.form.get("text").strip()
        if len(edit_text) == 0 or len(edit_text) > MAX_TWEET_LEN \
                or edit_text == generated_post.text:
            return render_post_html_from_id(
                generated_post.id,
                current_user.id,
            )

        new_edit = PostEdit(
            text=edit_text,
            created_at=datetime.now(),
            user_id=current_user.id,
            generated_post_id=generated_post.id
        )
        db.session.add(new_edit)
        db.session.commit()
        return render_template(
            "post.html",
            post_text=edit_text,
            post_id=generated_post.id,
        )


@app.route("/post/<post_id>/tweet", methods=["GET"])
def twitter_intents(post_id):
    '''
    GET redirects to Twitter intents to tweet the given post
    '''
    post_id = validate_generated_post_id(post_id)
    generated_post = get_generated_post_or_abort(post_id)
    post = latest_post_edit(generated_post.id, current_user.id)
    post_text = generated_post.text if post is None else post.text

    params = urlencode({"text": post_text})
    return redirect(f"https://twitter.com/intent/tweet/?{params}", 302)


@app.route("/post/<post_id>/schedule", methods=["GET", "POST"])
def schedule_post(post_id):
    '''
    GET returns the schedule form fragment
    @params
        timezone: the timezone of the client. This is sent as
            a query parameter so POST schedule endpoint has the correct TZ.
        default_time: the ISO timestamp to show as the default time
            in the datetime input field.

    POST schedules the post to be tweeted and returns the
    original post HTML fragment
    @params
        datetime: the ISO string of the datetime to schedule post at.
        timezone: the timezone of the datetime.
    '''
    app.logger.info(post_id)
    generated_post_id = validate_generated_post_id(post_id)

    if request.method == "POST":
        oauth = oauth_session_by_user(current_user.id)
        if oauth is None or oauth.access_token is None:
            # TODO add a message to prompt for Twitter auth
            return render_post_html_from_id(generated_post_id, current_user.id)

        timezone_str = request.form.get("timezone")
        datetime_str = request.form.get("datetime")
        try:
            tz = ZoneInfo(timezone_str)
            schedule_dt = datetime.strptime(
                datetime_str, DATETIME_ISO_FMT
            ).astimezone(tz)
        except Exception as e:
            app.logger.error(f"error processing schedule form: {e}")
            abort(400)

        # schedule tweet
        # TODO: offload to celery so it's not blocking
        scheduled_post = ScheduledPost(
            user_id=current_user.id,
            generated_post_id=generated_post_id,
            scheduled_for=schedule_dt.astimezone(timezone.utc)
        )
        db.session.add(scheduled_post)
        db.session.commit()

        app.logger.info(
            f"Scheduled tweet for {schedule_dt}"
        )
        return render_post_html_from_id(generated_post_id, current_user.id)
    # end POST

    if request.method == "GET":
        tz_str = request.args.get("timezone")
        try:
            tz = ZoneInfo(tz_str)
        except Exception as e:
            app.logger.error(f"invalid timezone: {e}")
            tz = ZoneInfo("UTC")

        min_dt = datetime.now(tz=tz)
        max_dt = min_dt + timedelta(days=MAX_FUTURE_SCHEDULE_DAYS)

        default_dt_str = request.args.get("default_time")
        app.logger.info(default_dt_str)
        if default_dt_str is None:
            default_dt = min_dt + timedelta(days=1)
            default_dt_str = default_dt.strftime(DATETIME_ISO_FMT)

        return render_post_html_from_id(
            generated_post_id,
            current_user.id,
            template_name="schedule_post.html",
            timezone_value=str(tz),
            datetime_min=min_dt.strftime(DATETIME_ISO_FMT),
            datetime_max=max_dt.strftime(DATETIME_ISO_FMT),
            datetime_value=default_dt_str
        )
    # end GET


@app.route("/post/<post_id>/unschedule", methods=["POST"])
def unschedule_post(post_id):
    '''
    POST deletes the scheduled post for this post ID and
        returns the original post HTML fragment.
    '''
    post_id = validate_generated_post_id(post_id)
    generated_post = get_generated_post_or_abort(post_id)
    sched_post = get_scheduled_post(generated_post.id, current_user.id)
    if sched_post is not None:
        ScheduledPost.query.filter(
            ScheduledPost.id == sched_post.id
        ).delete()
        db.session.commit()
    return render_post_html_from_id(generated_post.id, current_user.id)

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404