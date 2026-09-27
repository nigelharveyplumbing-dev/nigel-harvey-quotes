"""Deterministic AI quote wording, confidence and customer-preview formatting."""

import re


def normalise_ai_job_text(value: str):
    value = (value or "").lower().strip()
    corrections = {
        "rmove": "remove",
        "remve": "remove",
        "shower and fix": "shower and fit",
        "showe ": "shower ",
        "fitt ": "fit ",
        "replce": "replace",
        "toilte": "toilet",
        "raditor": "radiator",
        "outisde": "outside",
    }
    for old, new in corrections.items():
        value = value.replace(old, new)
    value = re.sub(r"\s+", " ", value)
    return value



STANDARD_QUOTE_EXCLUSIONS = [
    "Substantial making good, plastering, tiling, flooring and decoration unless specifically included.",
    "Repairs to concealed or defective existing pipework discovered after work starts.",
    "Electrical or gas work unless specifically stated and completed by a suitably qualified person.",
]



def unique_short_items(items, limit=5):
    output, seen = [], set()
    for item in items or []:
        value = re.sub(r"\s+", " ", str(item or "")).strip(" •-\n\t")
        key = normalise_ai_job_text(value)
        if value and key not in seen:
            seen.add(key)
            output.append(value)
        if len(output) >= limit:
            break
    return output



def professional_assumptions_from_context(context: dict):
    assumptions = []
    jobs = (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []
    for job in jobs:
        display = job.get("display_name", "Job")
        responsibility = job.get("supply_responsibility", "unknown")
        if responsibility == "customer":
            removed = job.get("customer_supplied_items_removed", []) or []
            assumptions.append(f"{display}: customer supplies {', '.join(removed) if removed else 'the main item'}.")
        elif responsibility == "business":
            assumptions.append(f"{display}: Nigel Harvey Ltd supplies the main item.")
        summary = job.get("context_note_summary", {}) or {}
        if summary.get("access"):
            assumptions.append(f"{display}: access remains reasonably workable as described.")
        if summary.get("measurement"):
            assumptions.append(f"{display}: measurements and pipe routes remain provisional until checked on site.")

    if not jobs:
        smart = context.get("smart_job_kit", {}) or {}
        responsibility = smart.get("supply_responsibility", "unknown")
        removed = smart.get("customer_supplied_items_removed", []) or []
        if responsibility == "customer":
            assumptions.append(f"Customer supplies {', '.join(removed) if removed else 'the main item'}.")
        elif responsibility == "business":
            assumptions.append("Nigel Harvey Ltd supplies the main item.")

    assumptions.extend([
        "Existing isolation points and reusable connections are serviceable unless stated otherwise.",
        "Final compatibility is subject to checking the existing installation and supplied products.",
    ])
    return unique_short_items(assumptions, 6)



def professional_exclusions_from_context(context: dict):
    exclusions = list(STANDARD_QUOTE_EXCLUSIONS)
    note_types = set()
    for job in (context.get("multi_job_estimate", {}) or {}).get("classified_jobs", []) or []:
        for note in job.get("context_notes", []) or []:
            note_types.update(note.get("types", []) or [])
    if "additional_work" in note_types:
        exclusions[0] = (
            "Only making-good or additional work expressly described in the scope is included; "
            "other plastering, tiling, flooring and decoration are excluded."
        )
    return unique_short_items(exclusions, 5)



def calculate_estimator_confidence(draft: dict, context: dict, *, safe_float):
    score = 45
    positives, gaps = [], []
    multi = context.get("multi_job_estimate", {}) or {}
    jobs = multi.get("classified_jobs", []) or []
    smart = context.get("smart_job_kit", {}) or {}

    if multi.get("is_multi_job") and jobs:
        score += 12
        positives.append(f"{len(jobs)} physical jobs identified and separated.")
        if not multi.get("unclassified_segments"):
            score += 5
            positives.append("All description notes were attached or classified.")
        else:
            score -= 8
            gaps.append("Some description text could not be confidently attached.")
    elif smart.get("classification"):
        score += 14
        positives.append("A recognised smart job kit was selected.")
    else:
        score -= 12
        gaps.append("No exact smart job kit was identified.")

    materials = draft.get("materials", []) or []
    if materials:
        priced = sum(1 for x in materials if safe_float(x.get("manual_price", 0), 0) > 0)
        matched = sum(1 for x in materials if x.get("data_source") not in {"ai_general", "ai_gap_fill", ""})
        if matched == len(materials):
            score += 10
            positives.append("All materials came from approved or saved business data.")
        elif matched:
            score += 5
            positives.append(f"{matched} of {len(materials)} materials matched business data.")
        else:
            score -= 8
            gaps.append("Materials were not matched to saved business data.")
        if priced == len(materials):
            score += 8
            positives.append("All material prices are available.")
        elif priced:
            score += 3
            positives.append(f"{priced} of {len(materials)} material prices are available.")
        else:
            score -= 6
            gaps.append("Material prices are not yet available.")

    similar = sum(int(x.get("similar_quotes", 0) or 0) for x in jobs)
    if similar >= 3:
        score += 8
        positives.append(f"{similar} similar saved quote references were found.")
    elif similar:
        score += 4
        positives.append(f"{similar} similar saved quote reference(s) were found.")
    else:
        gaps.append("Little or no directly comparable quote history was found.")

    unknown_supply = sum(1 for x in jobs if x.get("supply_responsibility", "unknown") == "unknown")
    if jobs and unknown_supply == 0:
        score += 5
        positives.append("Supply responsibility was understood for each job.")
    elif unknown_supply:
        score -= min(unknown_supply * 3, 9)
        gaps.append("Supply responsibility still needs confirming for one or more jobs.")

    if len(draft.get("questions_to_confirm", []) or []) > 8:
        score -= 5
        gaps.append("Several details still need confirming.")

    score = max(20, min(98, int(round(score))))
    return {
        "score": score,
        "level": "high" if score >= 85 else "medium" if score >= 65 else "low",
        "positive_reasons": unique_short_items(positives, 5),
        "gaps": unique_short_items(gaps, 4),
    }



def build_professional_quote_mode(draft: dict, context: dict, *, calculate_estimator_confidence, professional_assumptions_from_context, professional_exclusions_from_context):
    if not isinstance(draft, dict):
        return draft

    full_risks = unique_short_items(draft.get("risk_notes", []), 20)
    full_questions = unique_short_items(draft.get("questions_to_confirm", []), 25)
    full_warnings = unique_short_items(draft.get("warnings", []), 20)

    evidence = []
    for item in (draft.get("materials", []) or [])[:25]:
        evidence.append({
            "name": item.get("name", ""),
            "source": (item.get("data_source") or "business data").replace("_", " "),
            "confidence": 92 if item.get("data_source") not in {"ai_general", "ai_gap_fill", ""} else 65,
            "used_count": int(item.get("learned_used_count", 0) or 0),
        })

    draft["professional_quote"] = {
        "confidence": calculate_estimator_confidence(draft, context),
        "assumptions": professional_assumptions_from_context(context),
        "exclusions": professional_exclusions_from_context(context),
        "questions": unique_short_items(full_questions, 5),
        "risk_notes": unique_short_items(full_risks, 4),
        "material_evidence": evidence,
    }
    draft["technical_detail"] = {
        "all_risk_notes": full_risks,
        "all_questions": full_questions,
        "all_warnings": full_warnings,
    }
    return draft



def calculate_quote_quality_breakdown(draft: dict, context: dict, *, safe_float):
    professional = draft.get("professional_quote", {}) or {}
    base_confidence = int((professional.get("confidence", {}) or {}).get("score", 0) or 0)

    materials = draft.get("materials", []) or []
    jobs = draft.get("job_breakdown", []) or []

    if materials:
        priced = sum(1 for item in materials if safe_float(item.get("manual_price", 0), 0) > 0)
        matched = sum(
            1 for item in materials
            if item.get("data_source") not in {"", "ai_general", "ai_gap_fill"}
        )
        material_score = round(((priced / len(materials)) * 45) + ((matched / len(materials)) * 55))
    else:
        material_score = 50

    if jobs:
        labour_confidences = []
        for job in jobs:
            level = (job.get("labour_confidence", {}) or {}).get("level", "low")
            labour_confidences.append({"high": 95, "medium": 78, "low": 55}.get(level, 55))
        labour_score = round(sum(labour_confidences) / len(labour_confidences))
    else:
        labour_score = max(50, min(98, base_confidence))

    understanding_score = max(45, min(98, base_confidence + 3))
    questions = len((professional.get("questions", []) or []))
    site_confirmation = min(100, max(5, questions * 12 + (100 - base_confidence) // 3))

    overall = round(
        material_score * 0.32 +
        labour_score * 0.28 +
        understanding_score * 0.30 +
        (100 - site_confirmation) * 0.10
    )

    stars = max(1, min(5, round(overall / 20)))

    return {
        "overall": overall,
        "materials": material_score,
        "labour": labour_score,
        "understanding": understanding_score,
        "site_confirmation": site_confirmation,
        "stars": stars,
    }



def classify_material_status(item: dict):
    used_for = item.get("used_for_job_names", []) or []
    if item.get("customer_supplied"):
        return "customer_supplied"
    if item.get("required"):
        return "required"
    return "optional"



def build_customer_preview_payload(draft: dict, *, safe_float):
    professional = draft.get("professional_quote", {}) or {}
    return {
        "scope_of_work": draft.get("scope_of_work", ""),
        "job_breakdown": [
            {
                "display_name": job.get("display_name", ""),
                "scope": job.get("scope", ""),
                "labour_suggestion": safe_float(job.get("labour_suggestion", 0), 0),
                "customer_supplied_items_removed": job.get("customer_supplied_items_removed", []),
            }
            for job in (draft.get("job_breakdown", []) or [])
        ],
        "materials": [
            {
                "name": item.get("name", ""),
                "quantity": safe_float(item.get("quantity", 1), 1),
                "supplier": item.get("supplier", ""),
                "manual_price": safe_float(item.get("manual_price", 0), 0),
                "status": classify_material_status(item),
            }
            for item in (draft.get("materials", []) or [])
        ],
        "assumptions": professional.get("assumptions", []),
        "exclusions": professional.get("exclusions", []),
        "labour_total": safe_float(draft.get("labour_suggestion", 0), 0),
    }
