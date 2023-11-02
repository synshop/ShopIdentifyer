from dataclasses import dataclass, field

@dataclass
class RFIDToken():
    eb_id: int
    eb_status: str = "ACTIVE"
    stripe_id: str = ""
    rfid_token_hex: str = ""
    status: str = "UNASSIGNED"
    comment: str = "PRIMARY"
    created_on: str = ""
    changed_on: str = ""

@dataclass
class Member():
    stripe_id: str
    full_name: str
    discord_username: str = ""
    email: str = ""
    subscription_id: str = ""
    subscription_description: str = ""
    subscription_status: str = ""
    last_payment_status: str = ""
    member_status: str = "ACTIVE"
    is_vetted: str = "NOT_VETTED"
    locker_num: str = ""
    led_color: str = ""
    mobile: str = ""
    emergency_contact_name: str = ""
    emergency_contact_mobile: str = ""
    is_admin: str = ""
    rfid_tokens: list[RFIDToken] = field(default_factory=RFIDToken)

