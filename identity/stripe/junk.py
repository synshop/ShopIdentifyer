import stripe

def get_member_cache(key=None):

    stripe.api_version = '2013-02-13'
    stripe.api_key = key

    m = 0
    c = 50

    total_customer_count = stripe.Customer.all()['count']

    member_array = []

    while m <= total_customer_count:

        print "%s,%s" % (m, total_customer_count)

        members = stripe.Customer.all(offset=m,count=50)
        for member in members['data']:
            print member.email
            member_array.append({"stripe_email":member.email,"stripe_id":member.id})

        m = m + 50

        return member_array

def get_all_active_members(key=None):

    stripe.api_version = '2013-02-13'
    stripe.api_key = key

    m = 0
    c = 50
    x = 0

    # total_customer_count = _get_total_customer_count()
    total_customer_count = stripe.Customer.all()['count']

    while m <= total_customer_count:
        members = stripe.Customer.all(offset=m,count=50)
        for member in members['data']:
            if (member.subscription):

                print '{:<30} {:<30}'.format(member.email,member.subscription.plan.name)
                # print "%s\t\t%20s" % (member.email, member.subscription.plan.name)
                x = x + 1

        m = m + 50

    print
    print '-' * 20
    print "Total Members: %s" % (x)
    print '-' * 20

    return x

get_member_cache(key='i6nOnFG6yijh0MLViZkwBZ10nOt0r6sd')
# get_all_active_members(key='i6nOnFG6yijh0MLViZkwBZ10nOt0r6sd')
