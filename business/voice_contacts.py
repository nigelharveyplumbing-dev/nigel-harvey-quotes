"""Contact confirmation helpers; never infer digits/letters from a town name."""
import re
from business.phone_numbers import normalise_uk_phone


def normalise_postcode(value):
    value = re.sub(r"\s+", "", value or "").upper()
    if not re.fullmatch(r"(?:GIR0AA|[A-PR-UWYZ][A-HK-Y]?\d[A-HJKPSTUW\d]?\d[ABD-HJLNP-UW-Z]{2})", value):
        return None
    return value[:-3] + " " + value[-3:]


def contact_question(facts, *, phone_uncertain=False, postcode_uncertain=False):
    phone, code = facts.get("callback_phone", ""), facts.get("postcode", "")
    if phone and (phone_uncertain or not normalise_uk_phone(phone)):
        if not normalise_uk_phone(phone):
            return "callback_phone", "Could you give the full callback number, slowly?"
        return "callback_phone", f"Is your callback number {phone}?"
    if code and (postcode_uncertain or not normalise_postcode(code)):
        if not normalise_postcode(code):
            return "postcode", "Could you give the full postcode, letters and digits separately?"
        return "postcode", f"Is the postcode {normalise_postcode(code)}?"
    return None


def corrected_phone(previous, final_digits):
    """Apply ONLY an explicitly annotated suffix correction to a full number."""
    full = normalise_uk_phone(previous)
    if not full or not re.fullmatch(r"\d{1,4}", final_digits):
        return None
    return normalise_uk_phone(full[:-len(final_digits)] + final_digits)
