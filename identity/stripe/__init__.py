import stripe, time
from identity import app

PAYMENT_SUCCEEDED = "succeeded"
ACTIVE_SUBSCRIPTION = "active"
PAUSED_MEMBERSHIP = "Paused Membership"
FREE_MEMBERSHIP = "Free Membership"

# Liability waiver details the signup flow writes to the Stripe customer's metadata.
# Stored under the same names in stripe_cache and members
WAIVER_FIELDS = (
    "waiver_auth0_sub",
    "waiver_dob",
    "waiver_esign_consent",
    "waiver_sha256",
    "waiver_signed_at",
    "waiver_signed_ip",
    "waiver_signed_name",
    "waiver_user_agent",
    "waiver_version",
)

stripe.api_version = app.config['STRIPE_VERSION']
stripe.api_key = app.config['STRIPE_TOKEN']

def m_inspect_user(email=None):

    c = stripe.Customer.search(query='email: "' + email + '"', limit=1)['data'][0]
    print(c)


def get_customer_attributes(subscription):

    # User Model
    user = {
        "stripe_id": None,
        "stripe_created_on": None,
        "stripe_email": None,
        "stripe_full_name": None,
        "stripe_last_payment_status": None,
        "stripe_subscription_id": None,
        "stripe_subscription_description": None,
        "stripe_subscription_status": None,
        "stripe_subscription_created_on": None,
        "stripe_discord_username": None,
        "stripe_coupon_description": None
    }

    customer = stripe.Customer.retrieve(subscription.customer)

    user["stripe_id"] = customer.id
    user["stripe_email"] = customer.email.lower()
    user["stripe_created_on"] = customer.created
    user["stripe_full_name"] = customer.name
    user["stripe_subscription_status"] = subscription.status
    user["stripe_subscription_created_on"] = subscription.created
    user["stripe_subscription_id"] = subscription.id
    
    metadata = customer["metadata"] or {}
    user["stripe_discord_username"] = metadata.get("discord_id", "")

    for field in WAIVER_FIELDS:
        user[field] = metadata.get(field)

    if customer["discount"]:
        user["stripe_coupon_description"] = customer["discount"]["coupon"]["name"]

    # Determine if member is in good standing 
    for last_payment_intent in stripe.PaymentIntent.list(customer=subscription.customer, limit=1):
        user["stripe_last_payment_status"] = last_payment_intent.status

    sub_array = []
    subs = stripe.Subscription.retrieve(subscription.id, expand=['items.data.plan.product'])
    for s in subs['items']['data']:
        # Prices without a nickname fall back to the product name, then the price id
        product = s.plan.product
        product_name = None if isinstance(product, str) else getattr(product, 'name', None)
        sub_array.append(s.plan.nickname or product_name or s.plan.id)
    
    subs_string = ' + '.join(sub_array)
    user["stripe_subscription_description"] = subs_string

    return user

# When a customer has more than one subscription, the cache keeps the one with the
# best status (earliest in this list), then the most recently created
SUBSCRIPTION_STATUS_PREFERENCE = ("active", "trialing", "past_due", "unpaid", "incomplete", "paused")

def _subscription_rank(subscription):
    status = subscription.status
    status_rank = SUBSCRIPTION_STATUS_PREFERENCE.index(status) \
        if status in SUBSCRIPTION_STATUS_PREFERENCE else len(SUBSCRIPTION_STATUS_PREFERENCE)
    return (status_rank, -subscription.created)

def get_stripe_customers(incremental=False):

    # stripe_cache holds one row per customer, so pick one subscription for each
    by_customer = {}
    for subscription in stripe.Subscription.list().auto_paging_iter():
        current = by_customer.get(subscription.customer)
        if current is None:
            by_customer[subscription.customer] = subscription
            continue

        keep, drop = sorted((current, subscription), key=_subscription_rank)
        app.logger.warning("customer %s has more than one subscription, keeping %s (%s) over %s (%s)",
                           subscription.customer, keep.id, keep.status, drop.id, drop.status)
        by_customer[subscription.customer] = keep

    return [get_customer_attributes(s) for s in by_customer.values()]

def get_realtime_stripe_info(subscription_id=None):
    
    subscription = stripe.Subscription.retrieve(subscription_id)

    return get_customer_attributes(subscription)

def member_is_in_good_standing(subscription_id=None):

    member_stripe_info = get_realtime_stripe_info(subscription_id)
    payment_status = member_stripe_info['stripe_last_payment_status']
    subscription_status = member_stripe_info['stripe_subscription_status']
    stripe_subscription_description = member_stripe_info['stripe_subscription_description']

    if stripe_subscription_description == FREE_MEMBERSHIP:
        return True
    
    if payment_status == PAYMENT_SUCCEEDED and \
        subscription_status == ACTIVE_SUBSCRIPTION and \
        stripe_subscription_description != PAUSED_MEMBERSHIP:
        return True
    else:
        return False
