"""Fail-closed local spending journal. No credentials or provider I/O here."""
import fcntl
import json
import math
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

RATE_DATE = date(2026, 10, 3)
# USD per million tokens: text input/cached/output, audio input/cached/output.
RATES = {
    "gpt-realtime-2.1-mini": (0.60, 0.06, 2.40, 10.00, 0.30, 20.00),
    "gpt-realtime-2.1": (4.00, 0.40, 24.00, 32.00, 0.40, 64.00),
}
# Conservative planning assumption, not a live FX quote. Includes 25% uplift
# for VAT/fees. The working limit leaves £0.15 below the user's £5 ceiling.
GBP_PER_USD_WITH_LOADING = Decimal("1.25")
SOFT_LIMIT = Decimal("4.85")
HARD_LIMIT = Decimal("5.00")


class BudgetStop(RuntimeError):
    pass


def response_bound(model, instruction_bytes, input_audio_seconds, previous_responses, output_cap=512):
    """Conservative UTF-8 text bound, uncached history, modality worst cases.

    Earlier generated tokens are counted in BOTH possible input modalities;
    output tokens are all priced at the more expensive modality. 128 envelope
    tokens per conversation item cover token overhead. Unknown pricing stops.
    """
    rate = tuple(Decimal(str(value)) for value in RATES[model])
    text = instruction_bytes + previous_responses * output_cap + 512
    audio = math.ceil(input_audio_seconds * 10) + previous_responses * output_cap + 512
    return (text * rate[0] + audio * rate[3] + output_cap * max(rate[2], rate[5])) / 1_000_000


def usage_cost(model, usage):
    """Use reported modality/cache details; refuse unexplained token counts."""
    rate = tuple(Decimal(str(value)) for value in RATES[model])
    try:
        incoming, outgoing = usage["input_token_details"], usage["output_token_details"]
        values = [incoming["text_tokens"], incoming["audio_tokens"], outgoing["text_tokens"], outgoing["audio_tokens"]]
        if any(type(v) is not int or v < 0 for v in values):
            raise ValueError()
        if incoming.get("image_tokens", 0) or outgoing.get("image_tokens", 0):
            raise ValueError()
        if sum(values[:2]) != usage["input_tokens"] or sum(values[2:]) != usage["output_tokens"]:
            raise ValueError()
        cached = incoming.get("cached_tokens_details", {})
        ct, ca = cached.get("text_tokens", 0), cached.get("audio_tokens", 0)
        if any(type(v) is not int or v < 0 for v in (ct, ca)) or ct > values[0] or ca > values[1]:
            raise ValueError()
        if incoming.get("cached_tokens", 0) != ct + ca:
            raise ValueError()
        total = ((values[0] - ct) * rate[0] + ct * rate[1] + values[2] * rate[2]
                 + (values[1] - ca) * rate[3] + ca * rate[4] + values[3] * rate[5])
        return Decimal(str(total)) / Decimal(1_000_000)
    except (KeyError, TypeError, ValueError):
        raise BudgetStop("Usage missing or unrecognised; stop before another paid request") from None


class Ledger:
    """One process at a time; reservations survive exceptions and restarts."""
    def __init__(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = path.open("a+")
        os.chmod(path, 0o600)
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.file.seek(0)
            text = self.file.read()
            self.data = json.loads(text) if text else {"version": 1, "entries": [], "uncertain": False}
            if self.data.get("version") != 1 or not isinstance(self.data["entries"], list):
                raise BudgetStop("Unrecognised budget journal")
            if type(self.data.get("uncertain")) is not bool:
                raise BudgetStop("Unrecognised budget journal")
            for entry in self.data["entries"]:
                amount = Decimal(entry["usd"])
                if (not amount.is_finite() or amount < 0 or
                        entry["state"] not in {"in_flight", "reported", "bound_exceeded"}):
                    raise BudgetStop("Invalid budget journal entry")
        except Exception:
            self.file.close()
            raise

    def save(self):
        self.file.seek(0)
        self.file.truncate()
        json.dump(self.data, self.file, indent=2)
        self.file.flush()
        os.fsync(self.file.fileno())

    @property
    def reserved_usd(self):
        return sum((Decimal(e["usd"]) for e in self.data["entries"]), Decimal(0))

    @property
    def planning_gbp(self):
        return self.reserved_usd * GBP_PER_USD_WITH_LOADING

    def reserve(self, label, usd):
        usd = Decimal(str(usd))
        if self.data["uncertain"] or any(e["state"] == "in_flight" for e in self.data["entries"]):
            raise BudgetStop("An earlier request has unresolved usage; reconcile before resuming")
        if not usd.is_finite() or usd <= 0:
            raise BudgetStop("Invalid reservation")
        if (self.reserved_usd + usd) * GBP_PER_USD_WITH_LOADING > SOFT_LIMIT:
            raise BudgetStop("Estimated spend would exceed the £4.85 working limit; stop for review")
        self.data["entries"].append({"label": label, "usd": str(usd), "state": "in_flight"})
        self.save()
        return len(self.data["entries"]) - 1

    def settle(self, index, usd):
        entry = self.data["entries"][index]
        cost = Decimal(str(usd))
        if entry["state"] != "in_flight" or not cost.is_finite() or cost < 0:
            raise BudgetStop("Invalid usage settlement")
        if cost > Decimal(entry["usd"]):
            entry.update(usd=str(cost), state="bound_exceeded")
            self.data["uncertain"] = True
            self.save()
            raise BudgetStop("Provider usage exceeded reservation; stop immediately")
        entry.update(usd=str(cost), state="reported")
        self.save()

    def mark_uncertain(self):
        self.data["uncertain"] = True
        self.save()

    def close(self):
        self.file.close()


def verify_rate_date(today=None):
    today = today or date.today()
    if abs((today - RATE_DATE).days) > 3:
        raise BudgetStop("Recheck official pricing before using this dated rate card")
