import stripe, time
from identity import app

PAYMENT_SUCCEEDED = "succeeded"
ACTIVE_SUBSCRIPTION = "active"
PAUSED_MEMBERSHIP = "Paused Membership"

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
    
    if customer["metadata"]:
        user["stripe_discord_username"] = customer["metadata"]["discord_id"]
    else:
        user["stripe_discord_username"] = ""

    if customer["discount"]:
        user["stripe_coupon_description"] = customer["discount"]["coupon"]["name"]

    # Determine if member is in good standing 
    for last_payment_intent in stripe.PaymentIntent.list(customer=subscription.customer, limit=1):
        user["stripe_last_payment_status"] = last_payment_intent.status

    sub_array = []
    subs = stripe.Subscription.retrieve(subscription.id)
    for s in subs['items']['data']:
        sub_array.append(s.plan.nickname)
    
    subs_string = ' + '.join(sub_array)
    user["stripe_subscription_description"] = subs_string

    return user

def get_stripe_customers(incremental=False):
    member_array = []
    subscriptions = stripe.Subscription.list()

    for subscription in subscriptions.auto_paging_iter():
        member_array.append(get_customer_attributes(subscription))

    return member_array

def get_realtime_stripe_info(subscription_id=None):
    
    subscription = stripe.Subscription.retrieve(subscription_id)

    return get_customer_attributes(subscription)

def member_is_in_good_standing(subscription_id=None):
    member_stripe_info = get_realtime_stripe_info(subscription_id)
    payment_status = member_stripe_info['stripe_last_payment_status']
    subscription_status = member_stripe_info['stripe_subscription_status']
    stripe_subscription_description = member_stripe_info['stripe_subscription_description']

    if payment_status == PAYMENT_SUCCEEDED and \
        subscription_status == ACTIVE_SUBSCRIPTION and \
        stripe_subscription_description != PAUSED_MEMBERSHIP:
        return True
    else:
        return False
