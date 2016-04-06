import stripe
from identity import app

IN_GOOD_STANDING = "In Good Standing"
PAST_DUE = "Past Due"
DELINQUENT = "Delinquent"
NOT_ACTIVE = "Not Active"
NO_SUBSCRIPTION_PLAN = "No Subscription Plan"

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

def get_refresh_stripe_cache(t=None):

    stripe.api_version = '2013-02-13'
    stripe.api_key = app.config['STRIPE_TOKEN']
    member_array = []

    members = stripe.Customer.all(created={'gte':t})

    for member in members['data']:

        if (member.subscription):
            plan = member.subscription.plan.name
            status = member.subscription.status
        else:
            plan = NO_SUBSCRIPTION_PLAN
            status = NOT_ACTIVE

        member_array.append({"stripe_email":member.email,"stripe_id":member.id,"member_sub_plan":plan,"description":member.description,"created":member.created,"status":status})

    return member_array

def get_rebuild_stripe_cache():

    stripe.api_version = '2013-02-13'
    stripe.api_key = app.config['STRIPE_TOKEN']

    m = 0
    c = 50

    total_customer_count = stripe.Customer.all()['count']

    member_array = []

    while m <= total_customer_count:
        members = stripe.Customer.all(offset=m,count=c)
        for member in members['data']:

            if (member.subscription):
                status = member.subscription.status
                plan = member.subscription.plan.name
            else:
                status = NOT_ACTIVE
                plan = NO_SUBSCRIPTION_PLAN

            member_array.append({"stripe_email":member.email,"stripe_id":member.id,"member_sub_plan":plan,"description":member.description,"created":member.created,"status":status})

        m = m + c

    return member_array

def get_realtime_stripe_info(stripe_id=None):

    stripe_info = {'status':DELINQUENT,'plan':NO_SUBSCRIPTION_PLAN}

    stripe.api_version = '2013-02-13'
    stripe.api_key = app.config['STRIPE_TOKEN']

    member = stripe.Customer.retrieve(stripe_id)

    if member.subscription != None:
        stripe_info['status'] = member.subscription.status
        stripe_info['plan'] = member.subscription.plan.name

    return stripe_info
