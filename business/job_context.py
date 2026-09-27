"""Deterministic job-context parsing and material aggregation rules."""

import re


CONTEXT_NOTE_PATTERNS = {
    "customer_supply": [
        r"\bcustomer (?:is )?supplying\b",
        r"\bcustomer supplied\b",
        r"\bcustomer to supply\b",
        r"\bclient (?:is )?supplying\b",
        r"\bclient supplied\b",
        r"\bsupplied by customer\b",
        r"\bsupplied by client\b",
    ],
    "business_supply": [
        r"\bnigel (?:is )?supplying\b",
        r"\bnigel harvey ltd (?:is )?supplying\b",
        r"\bwe (?:are )?supplying\b",
        r"\bsupply and fit\b",
        r"\bcontractor supplying\b",
    ],
    "access": [
        r"\baccess\b",
        r"\bawkward\b",
        r"\brestricted\b",
        r"\btight space\b",
        r"\bunder (?:the )?(?:sink|basin|bath)\b",
        r"\bbehind (?:the )?(?:toilet|basin|unit)\b",
    ],
    "existing_condition": [
        r"\bexisting\b",
        r"\bleaking\b",
        r"\bseized\b",
        r"\bold\b",
        r"\bdamaged\b",
        r"\bcorroded\b",
        r"\bnot working\b",
        r"\bfailed\b",
    ],
    "additional_work": [
        r"\bmake good\b",
        r"\btil(?:e|ing)\b",
        r"\bplaster\b",
        r"\bdecorate\b",
        r"\bpaint\b",
        r"\bboxing\b",
        r"\brun new pipework\b",
        r"\bmove pipework\b",
        r"\balter pipework\b",
        r"\bremove and refit\b",
        r"\bdispose\b",
    ],
    "measurement": [
        r"\b\d+(?:\.\d+)?\s*(?:mm|cm|m|metre|metres)\b",
        r"\bpipe run\b",
        r"\bcentres?\b",
        r"\bheight\b",
        r"\bwidth\b",
        r"\bdepth\b",
    ],
}



CUSTOMER_SUPPLY_PATTERNS = [
    r"\bcustomer (?:is )?supplying\b",
    r"\bcustomer supplied\b",
    r"\bcustomer to supply\b",
    r"\bclient (?:is )?supplying\b",
    r"\bclient supplied\b",
    r"\bclient to supply\b",
    r"\bowner (?:is )?supplying\b",
    r"\bowner supplied\b",
    r"\bsupplied by customer\b",
    r"\bsupplied by client\b",
]



BUSINESS_SUPPLY_PATTERNS = [
    r"\bnigel (?:is )?supplying\b",
    r"\bnigel harvey ltd (?:is )?supplying\b",
    r"\bwe (?:are )?supplying\b",
    r"\bsupply and fit\b",
    r"\bcontractor supplying\b",
]



MAIN_ITEM_BY_JOB_TYPE = {
    "outside_tap": ["outside tap kit", "outside tap", "hose union bib tap"],
    "tap_replacement": ["replacement tap", "kitchen tap", "basin tap", "mixer tap"],
    "toilet_replacement": ["replacement toilet", "toilet", "wc"],
    "shower_replacement": ["replacement shower unit", "replacement shower", "shower"],
    "radiator_replacement": ["radiator"],
    "trv_replacement": ["trv valve", "thermostatic radiator valve"],
    "basin_waste": ["basin waste"],
    "kitchen_sink_waste": ["kitchen sink waste kit", "sink waste kit"],
}



def classify_context_note(sentence: str, *, normalise_ai_job_text):
    text = normalise_ai_job_text(sentence)
    matched = []
    for note_type, patterns in CONTEXT_NOTE_PATTERNS.items():
        if any(re.search(pattern, text, flags=re.I) for pattern in patterns):
            matched.append(note_type)
    return matched



def sentence_starts_new_job(sentence: str, *, normalise_ai_job_text, classify_smart_job):
    text = normalise_ai_job_text(sentence)
    classification = classify_smart_job(sentence)
    if not classification:
        return False

    # A supply-only or condition-only statement is contextual, not a new job.
    action_words = re.findall(
        r"\b(?:replace|fit|install|repair|change|remove|supply and fit|move|relocate|renew)\b",
        text,
        flags=re.I
    )
    supply_note = any(
        re.search(pattern, text, flags=re.I)
        for pattern in CUSTOMER_SUPPLY_PATTERNS + BUSINESS_SUPPLY_PATTERNS
    )
    if supply_note and not action_words:
        return False

    return bool(action_words)



def attach_context_to_job(job_record: dict, sentence: str, *, classify_context_note):
    note_types = classify_context_note(sentence)
    job_record.setdefault("context_notes", []).append({
        "text": sentence.strip(),
        "types": note_types,
    })

    if "customer_supply" in note_types:
        job_record["supply_responsibility"] = "customer"
    elif "business_supply" in note_types:
        job_record["supply_responsibility"] = "business"

    return job_record



def parse_context_aware_jobs(job_text: str, *, sentence_starts_new_job, classify_smart_job, detect_supply_responsibility, attach_context_to_job, normalise_ai_job_text):
    original = (job_text or "").strip()
    if not original:
        return {
            "jobs": [],
            "unattached_notes": [],
        }

    # Preserve line order, then split obvious sentence boundaries.
    raw_lines = re.split(r"[\n\r]+", original)
    sentences = []
    for line in raw_lines:
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"(?<=[.;!?])\s+", line)
        for part in parts:
            part = part.strip(" .;,-")
            if part:
                sentences.append(part)

    jobs = []
    unattached = []
    current = None

    for sentence in sentences:
        if sentence_starts_new_job(sentence):
            classification = classify_smart_job(sentence)
            current = {
                "job_text": sentence,
                "job_type": classification.get("job_type"),
                "display_name": classification.get("display_name"),
                "classification_score": classification.get("classification_score"),
                "context_notes": [],
                "supply_responsibility": detect_supply_responsibility(
                    sentence,
                    classification.get("job_type")
                ),
            }
            jobs.append(current)
            continue

        # Context note belongs to the most recent job where possible.
        if current is not None:
            attach_context_to_job(current, sentence)
        else:
            unattached.append(sentence)

    # Merge accidental consecutive duplicates of the same physical job.
    merged = []
    for job in jobs:
        if (
            merged
            and merged[-1].get("job_type") == job.get("job_type")
            and normalise_ai_job_text(merged[-1].get("job_text", "")) == normalise_ai_job_text(job.get("job_text", ""))
        ):
            merged[-1]["context_notes"].extend(job.get("context_notes", []))
            if job.get("supply_responsibility") != "unknown":
                merged[-1]["supply_responsibility"] = job.get("supply_responsibility")
            continue
        merged.append(job)

    return {
        "jobs": merged[:10],
        "unattached_notes": unattached,
    }



def context_notes_as_text(job_record: dict):
    return " ".join(
        note.get("text", "")
        for note in job_record.get("context_notes", [])
        if note.get("text")
    ).strip()



def context_note_summary(job_record: dict):
    groups = {}
    for note in job_record.get("context_notes", []):
        for note_type in note.get("types", []):
            groups.setdefault(note_type, []).append(note.get("text", ""))
    return groups



def split_multi_job_description(job_text: str, *, parse_context_aware_jobs):
    parsed = parse_context_aware_jobs(job_text)
    return [
        job.get("job_text", "")
        for job in parsed.get("jobs", [])
        if job.get("job_text")
    ]



def detect_supply_responsibility(job_text: str, job_type: str, *, normalise_ai_job_text):
    text = normalise_ai_job_text(job_text)

    customer_supplied = any(re.search(pattern, text, flags=re.I) for pattern in CUSTOMER_SUPPLY_PATTERNS)
    business_supplied = any(re.search(pattern, text, flags=re.I) for pattern in BUSINESS_SUPPLY_PATTERNS)

    if customer_supplied and not business_supplied:
        return "customer"
    if business_supplied and not customer_supplied:
        return "business"
    if customer_supplied and business_supplied:
        return "mixed"
    return "unknown"



def is_main_supply_item(material_name: str, job_type: str, *, canonical_material_name):
    canonical = canonical_material_name(material_name)
    for candidate in MAIN_ITEM_BY_JOB_TYPE.get(job_type, []):
        candidate_can = canonical_material_name(candidate)
        if canonical == candidate_can or candidate_can in canonical or canonical in candidate_can:
            return True
    return False



def apply_supply_responsibility_to_materials(materials: list, job_type: str, responsibility: str, *, is_main_supply_item):
    rows = []
    removed = []

    for material in materials or []:
        row = dict(material)
        main_item = is_main_supply_item(row.get("name", ""), job_type)

        if responsibility == "customer" and main_item:
            removed.append(row)
            continue

        if responsibility == "business" and main_item:
            row["required"] = True
            row["reason"] = (
                row.get("reason", "") +
                " Nigel Harvey Ltd is supplying this main item."
            ).strip()

        if responsibility == "unknown" and main_item:
            row["required"] = False

        rows.append(row)

    return rows, removed



def merge_multi_job_materials(job_records: list, *, canonical_material_name, safe_float):
    merged = {}

    fractional_consumables = {
        canonical_material_name("PTFE tape"),
        canonical_material_name("Sanitary silicone"),
        canonical_material_name("Central heating inhibitor"),
    }

    for job_record in job_records:
        job_number = job_record.get("job_number")
        job_name = job_record.get("display_name", "")
        for material in job_record.get("materials", []) or []:
            row = dict(material)
            key = canonical_material_name(row.get("name", ""))
            if not key:
                continue

            quantity = safe_float(row.get("quantity", 1), 1)
            if key not in merged:
                row["used_for_jobs"] = [job_number]
                row["used_for_job_names"] = [job_name]
                merged[key] = row
                continue

            existing = merged[key]
            existing_qty = safe_float(existing.get("quantity", 1), 1)

            # Consumable fractions accumulate; identical reusable fittings also
            # accumulate because each separate job may need its own item.
            existing["quantity"] = round(existing_qty + quantity, 2)
            existing["required"] = bool(existing.get("required") or row.get("required"))

            if job_number not in existing.get("used_for_jobs", []):
                existing.setdefault("used_for_jobs", []).append(job_number)
            if job_name and job_name not in existing.get("used_for_job_names", []):
                existing.setdefault("used_for_job_names", []).append(job_name)

            if not existing.get("url") and row.get("url"):
                existing["url"] = row.get("url")
            if not existing.get("supplier") and row.get("supplier"):
                existing["supplier"] = row.get("supplier")
            if safe_float(existing.get("manual_price", 0), 0) <= 0:
                existing["manual_price"] = safe_float(row.get("manual_price", 0), 0)

    rows = list(merged.values())
    rows.sort(
        key=lambda item: (
            1 if item.get("required") else 0,
            len(item.get("used_for_jobs", [])),
            item.get("name", "")
        ),
        reverse=True
    )
    return rows



def merge_multi_job_materials_with_summary(job_records: list, *, merge_multi_job_materials):
    before_count = sum(len(record.get("materials", []) or []) for record in job_records)
    merged = merge_multi_job_materials(job_records)
    after_count = len(merged)

    return merged, {
        "materials_before_merge": before_count,
        "unique_materials_after_merge": after_count,
        "duplicates_merged": max(0, before_count - after_count),
    }



def labour_confidence_for_job(record: dict):
    similar = int(record.get("similar_quotes", 0) or 0)
    source = record.get("labour_source", "")

    if source == "labour_history" and similar >= 3:
        return {
            "level": "high",
            "message": f"Based on {similar} similar saved quotes."
        }
    if source == "labour_history" and similar >= 1:
        return {
            "level": "medium",
            "message": f"Based on {similar} similar saved quote(s)."
        }
    if source == "smart_job_range":
        return {
            "level": "medium",
            "message": "Based on the approved labour range for this job type."
        }
    return {
        "level": "low",
        "message": "Requires manual labour review."
    }
