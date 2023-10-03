import stripe, time
from identity import app

PAYMENT_SUCCEEDED = "succeeded"
ACTIVE_SUBSCRIPTION = "active"
PAUSE_MEMBERSHIP = "Pause Membership"

STRIPE_VERSION = "2022-08-01"

def inspect_user(email=None):
    stripe.api_version = STRIPE_VERSION
    stripe.api_key = app.config['STRIPE_TOKEN']
    c = stripe.Customer.search(query='email: "' + email + '"', limit=1)['data'][0]

    subs = stripe.Subscription.retrieve("sub_12asGcCEk4tLAE")
    for s in subs['items']['data']:
        print(s.plan.nickname)

    return True

    x = stripe.Subscription.list(customer=c.id, limit=3)
    for s in x['data'][0]['items']:
        print(s.plan.nickname)

        # print(s.plan.nickname)

def _get_customer_attributes(subscription):

    # User Model
    user = {
        "stripe_id": None,
        "stripe_created_on": None,
        "stripe_email": None,
        "stripe_description": None,
        "stripe_last_payment_status": None,
        "stripe_subscription_id": None,
        "stripe_subscription_product": None,
        "stripe_subscription_status": None,
        "stripe_subscription_created_on": None,
        "stripe_discord_id": None
    }

    customer = stripe.Customer.retrieve(subscription.customer)

    user["stripe_id"] = customer.id
    user["stripe_email"] = customer.email.lower()
    user["stripe_created_on"] = customer.created
    user["stripe_description"] = customer.name
    user["stripe_subscription_status"] = subscription.status
    user["stripe_subscription_created_on"] = subscription.created
    user["stripe_subscription_id"] = subscription.id
    
    if customer["metadata"]:
        user["stripe_discord_id"] = customer["metadata"]["discord_id"]
    else:
        user["stripe_discord_id"] = ""

    # Determine if member is in good standing 
    for last_payment_intent in stripe.PaymentIntent.list(customer=subscription.customer, limit=1):
        user["stripe_last_payment_status"] = last_payment_intent.status

    sub_array = []
    subs = stripe.Subscription.retrieve(subscription.id)
    for s in subs['items']['data']:
        sub_array.append(s.plan.nickname)
    
    subs_string = ' + '.join(sub_array)
    user["stripe_subscription_product"] = subs_string

    return user

def get_stripe_customers(incremental=False):

    stripe.api_version = STRIPE_VERSION
    stripe.api_key = app.config['STRIPE_TOKEN']

    member_array = []

    if (incremental == False):
        subscriptions = stripe.Subscription.list()
    else:
        i = app.config['STRIPE_CACHE_REFRESH_REACHBACK_MIN'] * 60
        t = int(time.time()) - i
        subscriptions = stripe.Subscription.list(created={'gte':t})

    for subscription in subscriptions.auto_paging_iter():
        member = _get_customer_attributes(subscription)
        member_array.append(member)

    return member_array

def get_realtime_stripe_info(subscription_id=None):

    stripe.api_version = STRIPE_VERSION
    stripe.api_key = app.config['STRIPE_TOKEN']
    
    subscription = stripe.Subscription.retrieve(subscription_id)

    return _get_customer_attributes(subscription)

def member_is_in_good_standing(subscription_id=None):
    member_stripe_info = get_realtime_stripe_info(subscription_id)
    payment_status = member_stripe_info['stripe_last_payment_status']
    subscription_status = member_stripe_info['stripe_subscription_status']
    subscription_product = member_stripe_info['stripe_subscription_product']

    if payment_status == PAYMENT_SUCCEEDED and \
        subscription_status == ACTIVE_SUBSCRIPTION and \
        subscription_product != PAUSE_MEMBERSHIP:
        return True
    else:
        return False
