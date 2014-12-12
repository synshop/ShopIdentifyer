import stripe

IN_GOOD_STANDING = "In Good Standing"
DELINQUENT = "Delinquent"

def get_stripe_cache(key=None):

    stripe.api_version = '2013-02-13'
    stripe.api_key = key

    m = 0
    c = 50

    total_customer_count = stripe.Customer.all()['count']

    member_array = []

    while m <= total_customer_count:
        members = stripe.Customer.all(offset=m,count=c)
        for member in members['data']:

            if (member.subscription):
                plan = member.subscription.plan.name
            else:
                plan = "No Subscription Plan"

            member_array.append({"stripe_email":member.email,"stripe_id":member.id,"member_sub_plan":plan})

        m = m + c

    return member_array

def get_payment_status(key=None,member_id=None):

    stripe.api_version = '2013-02-13'
    stripe.api_key = key

    count = stripe.Customer.retrieve(member_id).subscriptions.all()['count']

    if (count != 0):
        return IN_GOOD_STANDING
    else:
        return DELINQUENT
