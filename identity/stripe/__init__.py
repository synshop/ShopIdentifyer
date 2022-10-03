import stripe, time
from identity import app

IN_GOOD_STANDING = "In Good Standing"
PAST_DUE = "Past Due"
DELINQUENT = "Delinquent"
NOT_ACTIVE = "Not Active"
NO_SUBSCRIPTION_PLAN = "No Subscription Plan"

STRIPE_VERSION = "2022-08-01"

# Delinquent email template
D_EMAIL_TEMPLATE = """

<!DOCTYPE html>
<html>

<body>
<img src="https://synshop.org/sites/default/files/logo290.png">
<h2>Oops, it looks like your membership payments are failing.</h2>

<p>We'll still let you in the door, but please correct this as soon as possible.</p>

<p>You can modify / adjust your payment type by going here: <a href="#">https://synshop.org/user/%s/</a></p>

<p>Also, if you have any questions, please reply back to this email and we will do our best to help you.</p>

</body>
</html>

"""

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
    user["stripe_description"] = customer.description
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




    
