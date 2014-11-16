class Member(object):

    def __init__(self):
        self._badge_serial = None
        self._badge_status = None
        self._full_name = None
        self._nick_name = None
        self._drupal_name = None
        self._primary_email = None
        self._stripe_email = None
        self._meetup_email = None
        self._mobile = None
        self._emergency_contact_name = None
        self._emergency_contact_mobile = None
        self._is_vetted = None
        self._liability_wavier = None
        self._vetted_membership_form = None
        self._badge_photo = None

    @property
    def badge_serial(self):
        return self._badge_serial

    @badge_serial.setter
    def badge_serial(self,value):
        self._badge_serial = value

    @property
    def badge_status(self):
        return self._badge_status

    @badge_status.setter
    def badge_status(self,value):
        self._badge_status = value

    @property
    def full_name(self):
        return self._full_name

    @full_name.setter
    def full_name(self,value):
        self._full_name = value

    @property
    def nick_name(self):
        return self._nick_name

    @nick_name.setter
    def nick_name(self,value):
        self._nick_name = value

    @property
    def drupal_name(self):
        return self._drupal_name

    @drupal_name.setter
    def drupal_name(self,value):
        self._drupal_name = value

    @property
    def primary_email(self):
        return self._primary_email

    @primary_email.setter
    def primary_email(self,value):
        self._primary_email = value

    @property
    def stripe_email(self):
        return self._stripe_email

    @stripe_email.setter
    def stripe_email(self,value):
        self._stripe_email = value

    @property
    def meetup_email(self):
        return self._meetup_email

    @meetup_email.setter
    def meetup_email(self,value):
        self._meetup_email = value

    @property
    def mobile(self):
        return self._mobile

    @mobile.setter
    def mobile(self,value):
        self._mobile = value

    @property
    def emergency_contact_name(self):
        return self._emergency_contact_name

    @emergency_contact_name.setter
    def emergency_contact_name(self,value):
        self._emergency_contact_name = value

    @property
    def emergency_contact_mobile(self):
        return self._emergency_contact_mobile

    @emergency_contact_mobile.setter
    def emergency_contact_mobile(self,value):
        self._emergency_contact_mobile = value

    @property
    def is_vetted(self):
        return self._is_vetted

    @is_vetted.setter
    def is_vetted(self,value):
        self._is_vetted = value

    @property
    def liability_wavier(self):
        return self._liability_wavier

    @liability_wavier.setter
    def liability_wavier(self,value):
        self._liability_wavier = value

    @property
    def vetted_membership_form(self):
        return self._vetted_membership_form

    @vetted_membership_form.setter
    def vetted_membership_form(self,value):
        self._vetted_membership_form = value

    @property
    def badge_photo(self):
        return self._badge_photo

    @badge_photo.setter
    def badge_photo(self,value):
        self._badge_photo = value

    def save(self):
        pass

    def update(self):
        pass
