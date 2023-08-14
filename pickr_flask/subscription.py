"""Functions to work with stripe subscriptions."""
from datetime import datetime, timedelta

import stripe
from sqlalchemy.orm.exc import NoResultFound

from .models import PickrUser, StripeSubscription, StripeSubscriptionStatus, db


def has_free_trial(user: PickrUser):
    return user.created_at + timedelta(days=7) <= datetime.now()


def has_active_sub(user: PickrUser):
    return user.stripe_subscriptions


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
