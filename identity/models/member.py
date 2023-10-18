from dataclasses import dataclass

@dataclass
class Member():
    stripe_id: str
    full_name: str
    discord_username: str
    email: str
    subscription_id: str
    subscription_description: str
    subscription_status: str
    last_payment_status: str
    member_status: str
    is_vetted: str
    locker_num: str
    led_color: str
    mobile: str
    emergency_contact_name: str
    emergency_contact_mobile: str
    is_admin: str
    rfid_tokens: list

