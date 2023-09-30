import stripe, time
from identity import app

PAYMENT_SUCCEEDED = "succeeded"
ACTIVE_SUBSCRIPTION = "active"
PAUSE_MEMBERSHIP = "Pause Membership"

STRIPE_VERSION = "2022-08-01"

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
        "stripe_subscription_created_on": None
    }

    customer = stripe.Customer.retrieve(subscription.customer)

    user["stripe_id"] = customer.id
    user["stripe_email"] = customer.email.lower()
    user["stripe_created_on"] = customer.created
    user["stripe_description"] = customer.name
    user["stripe_subscription_status"] = subscription.status
    user["stripe_subscription_created_on"] = subscription.created
    user["stripe_subscription_id"] = subscription.id

    # Determine if member is in good standing 
    for last_payment_intent in stripe.PaymentIntent.list(customer=subscription.customer, limit=1):
        user["stripe_last_payment_status"] = last_payment_intent.status

    for x in iter(subscription.items()):
        if x[0] == "items":
            product = x[1].data[0].plan.product
            user["stripe_subscription_product"] = stripe.Product.retrieve(product).name

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
