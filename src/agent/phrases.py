"""The few lines that are deliberately fixed. Everything else is said by the LLM.

Each one is required by the assignment brief or by safety: the recording notice, the
after-hours notice, the emergency direction, the generic verification failure, the
arrival instructions, the after-hours closing and the staff-handoff notice.
"""

OPENING = (
    "Thank you for calling Sunrise Family Clinic. This call may be recorded for quality purposes."
)
OPEN_GREETING = "How can I help you today?"
CLOSED_GREETING = (
    "Our office is closed right now. We're open Monday through Friday, 9 AM to 5 PM "
    "Eastern Time. If this is an emergency, please hang up and call 911. "
    "I can take a message for our team."
)
EMERGENCY = (
    "This sounds like it could be an emergency. Please hang up and call 911 right now, "
    "or go to the nearest emergency room."
)
VERIFICATION_FAILED = "I'm sorry, I couldn't verify those details."
ARRIVAL_INSTRUCTIONS = (
    "Please arrive 15 minutes early and bring a photo ID and your insurance card. "
    "You'll receive a confirmation by email."
)
STAFF_HANDOFF = (
    "I'll transfer you to a member of our clinic staff now. "
    "In this demo, I've recorded the transfer request, and our team will follow up with you."
)


def after_hours_closing(first_name: str) -> str:
    return (
        f"Thank you, {first_name}. Your message has been recorded, and our team will get back "
        "to you on the next business day. If this is an emergency, please hang up and call 911. "
        "Have a good night."
    )
