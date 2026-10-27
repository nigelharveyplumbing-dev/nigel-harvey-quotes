"""Strict legacy snapshot compatibility for reviewed manual WhatsApp additions.

Remove only known, single-occurrence UI additions when comparing against
pre-WhatsApp frozen assets. All other bytes remain protected by those tests.
"""


def strip_manual_whatsapp_js(text: str) -> str:
    markers = (
        '    contact_channel: document.getElementById("quote_contact_channel")?.value || "Unknown",',
        '  document.getElementById("quote_contact_channel").value = requestData.contact_channel || "Unknown";',
        'onclick="revenueOpenOrigin(',
        "  document.getElementById('quote_contact_channel').value = lead.contact_channel || 'Unknown';",
        '  document.getElementById("quote_contact_channel").value = "Unknown";',
    )
    for marker in markers:
        matches = [line for line in text.splitlines(keepends=True) if marker in line]
        if len(matches) != 1:
            raise AssertionError("Expected exactly one reviewed WhatsApp addition: " + marker)
        line = matches[0]
        if marker == 'onclick="revenueOpenOrigin(':
            if not line.strip().startswith('$' + '{q.origin_id ? ') or 'Correct enquiry source</button>' not in line:
                raise AssertionError('Unexpected saved-quote correction shortcut')
        elif line.strip() != marker.strip():
            raise AssertionError('Reviewed WhatsApp line has changed: ' + marker)
        text = text.replace(line, '', 1)
    return text


def strip_manual_whatsapp_markup(text: str) -> str:
    text = strip_manual_whatsapp_js(text)
    replacements = (
        ('<label for="quote_source">How did the customer find you? (if known)</label>',
         '<label for="quote_source">Lead source (optional)</label>'),
        ('<label>How did they find you?</label><select id="quickSource">',
         '<label>Lead source</label><select id="quickSource">'),
        ('''      <label for="quote_contact_channel">How did they first contact you?</label>
      <select id="quote_contact_channel"><option>Unknown</option><option>WhatsApp</option><option>Phone</option><option>Email</option><option>Website form</option><option>Directory message</option><option>In person</option><option>Other</option></select>
      <p class="small">For a quote linked to an existing enquiry, its original contact channel is inherited. To correct an existing saved enquiry or quote, use Source &amp; revenue and give a reason.</p>
''', ''),
    )
    for old, new in replacements:
        if text.count(old) != 1:
            raise AssertionError("Expected exactly one reviewed WhatsApp template change: " + old[:80])
        text = text.replace(old, new, 1)
    return text
