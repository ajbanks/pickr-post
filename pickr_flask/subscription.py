"""Functions to work with stripe subscriptions."""
from datetime import datetime

import stripe
from sqlalchemy.orm.exc import NoResultFound

from .models import PickrUser, StripeSubscription, StripeSubscriptionStatus, db


unlimited_access_pickr_users = ['alexander.joseph9141@gmail.com', 'nathan111', 'testmail', 'pickr_social', 'pickrsocial', 'testuser555']


def is_user_stripe_subscription_active(pickr_user):
    try:
        stripe_subscription = StripeSubscriptionStatus(
            get_stripe_subscription_status(pickr_user.id))
        if stripe_subscription != StripeSubscriptionStatus.active \
        and stripe_subscription != StripeSubscriptionStatus.trialing:
            print('stripe sub is not valid')
            return False
        else:
            print('stripe sub is valid')
            return True
    except Exception as e:
        print('couldnt find striper subscirption', e)
        return False

def is_user_account_valid(pickr_user):
    "check if a user is allowed to use pickr features"
    if pickr_user.username in unlimited_access_pickr_users:
        return True
    
    print('checking if users account is valid')
    valid = True
    if is_users_trial_invalid(pickr_user) and not is_user_stripe_subscription_active(pickr_user):
        valid = False

    return valid


def is_users_trial_invalid(pickr_user, n_trial_days=14):
    """Check if a users account is older than trial period"""
    trial_over = False
    delta = datetime.today() - pickr_user.created_at
    
    if delta.days >= n_trial_days:
        trial_over = True
    print('is trial over?', trial_over, pickr_user.created_at, delta)
    return trial_over


def get_stripe_subscription_status(user_id):
    stripe_subscription = StripeSubscription.query.filter_by(
            user_id=user_id,
        ).first()
    print('stripe_subscription', stripe_subscription, user_id)
    if stripe_subscription is None:
        print('subscription is None')
        return StripeSubscriptionStatus.canceled
    print('stripe_subscription.stripe_subscription_id', stripe_subscription.stripe_subscription_id)
    retrieve_sub = stripe.Subscription.retrieve(
        stripe_subscription.stripe_subscription_id)
    status = retrieve_sub.status
    return status


def handle_checkout_completed(event):
    data = event["data"]["object"]
    print('handle_checkout_completed')

    retrieve_sub = stripe.Subscription.retrieve(data['subscription'])
    sub_status = StripeSubscriptionStatus(retrieve_sub.status)

    # the subscription isn't confirmed yet
    stripeSub = StripeSubscription(
        user_id=data["metadata"]["user_id"],
        stripe_customer_id=data["customer"],
        stripe_subscription_id=data["subscription"],
        stripe_invoice_id=data["invoice"],
        status=sub_status,
    )

    db.session.add(stripeSub)
    db.session.commit()


def handle_subscription_created(event):
    """Handle stripe customer.subscription.created event."""
    data = event["data"]["object"]
    stripeSub = StripeSubscription(
        user_id=data["metadata"]["user_id"],
        stripe_customer_id=data["customer"],
        stripe_subscription_id=data["id"],
        stripe_invoice_id=data["latest_invoice"],
        status=data["status"],
    )

    db.session.add(stripeSub)
    db.session.commit()

    try:
        sub = StripeSubscription.query.filter_by(
            stripe_subscription_id=data["subscription"],
        ).one()
    except NoResultFound:
        # shouldn't happen
        return

    sub.expires_at = datetime.utcfromtimestamp(data["current_period_end"])
    sub.status = StripeSubscriptionStatus[data["status"]]
    db.session.commit()


def handle_subscription_deleted(event):
    """Handle stripe customer.subscription.deleted event."""
    # TODO

    return


def handle_subscription_updated(event):
    """Handle stripe customer.subscription.updated event."""
    data = event["data"]["object"]
    try:
        sub = StripeSubscription.query.filter_by(
            stripe_subscription_id=data["subscription"],
        ).one()
    except NoResultFound:
        # ...
        return

    sub.status = StripeSubscriptionStatus[data["status"]]
    sub.expires_at = datetime.utcfromtimestamp(data["current_period_end"]),

    db.session.commit()


def cancel_subscription(user: PickrUser):
    sub = StripeSubscription.query.filter_by(
        user_id=user.id,
    ).filter_by(
        status=StripeSubscriptionStatus.active,
    ).first()

    if not sub:
        return

    stripe.Subscription.cancel(sub.id)
