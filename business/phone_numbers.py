"""Conservative UK number matching, retaining the original display value."""
import re


def normalise_uk_phone(value):
    import phonenumbers
    value = (value or "").strip()
    if not value or not re.fullmatch(r"[+0-9 ()\-\.]+", value):
        return None
    if "+" in value and not re.fullmatch(r"\+[^+]+", value):
        return None
    # Accept the common international UK spelling +44 (0) ... .
    value = re.sub(r"^(\+44|0044)\s*\(0\)", r"\1", value)
    try:
        number = phonenumbers.parse(value, "GB")
    except phonenumbers.NumberParseException:
        return None
    # Possible length, not allocation/reachability: Ofcom fictional numbers
    # deliberately are not marked valid by libphonenumber.
    if number.country_code != 44 or number.extension or phonenumbers.is_possible_number_with_reason(number) != phonenumbers.ValidationResult.IS_POSSIBLE:
        return None
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
