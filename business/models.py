"""Request payload models with unchanged defaults."""

from pydantic import BaseModel, Field, model_validator, ConfigDict
from typing import Literal
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone


class AccountPriceSelection(BaseModel):
    """Frozen owner selection, separate from the legacy selected-public field."""
    model_config = ConfigDict(extra="forbid")
    supplier_sku: str = Field(pattern=r"^\d{6}$")
    name: str = Field(min_length=1, max_length=500)
    brand: str = Field(default="", max_length=500)
    mpn: str = Field(default="", max_length=500)
    gtin: str = ""
    pack_quantity: int = Field(gt=0, le=100000)
    selling_unit: Literal["each", "pack"]
    price: Decimal = Field(gt=0, lt=100000, allow_inf_nan=False)
    vat_basis: Literal["ex_vat"]
    vat_rate: Literal["0.20"]
    price_inc_vat: Decimal = Field(gt=0, lt=120000, allow_inf_nan=False)
    source_type: Literal["account_cached"]
    capture_source: Literal["city_app_owner_capture"]
    checked_at: str
    checked_precision: Literal["date", "time"] = "time"
    stock_note: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def consistent_capture(self):
        from business.account_pricing import timestamp
        from business.trade_comparison import valid_gtin
        if self.selling_unit == "each" and self.pack_quantity != 1:
            raise ValueError("Each means a selling quantity of one")
        if self.price.quantize(Decimal("0.01")) != self.price or (self.price * Decimal("1.20")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP) != self.price_inc_vat:
            raise ValueError("Account VAT normalization does not match the original price")
        if timestamp(self.checked_at) > datetime.now(timezone.utc):
            raise ValueError("Account capture cannot be dated in the future")
        if self.gtin and not valid_gtin(self.gtin):
            raise ValueError("Invalid account GTIN")
        return self

class MaterialItem(BaseModel):
    name: str = ""
    quantity: float = 1
    supplier: str = ""
    url: str = ""
    manual_price: float = 0
    selected_comparison_price: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    selected_account_price: AccountPriceSelection | None = None
    quote_charge_override: float | None = None
    material_type: str = "chargeable"
    charge_method: str = "full"
    quantity_source: str = "rule"
    learned_average_quantity: float | None = None
    learned_used_count: float | None = None

    @model_validator(mode="after")
    def bound_account_selection(self):
        selected = self.selected_account_price
        if selected and (self.selected_comparison_price is not None or self.supplier not in {"City Plumbing", "PTS"}
                         or self.name != selected.name or abs(self.manual_price - float(selected.price_inc_vat)) > 0.000001):
            raise ValueError("Account selection must match the selected City product and amount")
        if selected and self.url:
            from business.trade_comparison import supplier_for_url
            import re
            if supplier_for_url(self.url) != "City Plumbing" or not re.search(r"/" + selected.supplier_sku + r"/?$", self.url):
                raise ValueError("Account selection URL must match the City code")
        return self


class QuoteRequest(BaseModel):
    quote_type: str = "small"
    customer_name: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    job_description: str = ""
    labour_cost: float = 0
    include_callout_charge: bool = False
    callout_charge: float = 200
    include_travel_charge: bool = False
    travel_charge: float = 0
    include_materials_handling: bool = True
    materials_handling_percent: float = 25
    materials: list[MaterialItem] = Field(default_factory=list)
    tiling: bool = False
    wall_tiling_m2: float = 0
    floor_tiling_m2: float = 0
    wall_height: str = "half"
    customer_supplies_tiles: bool = False
    deposit_percent: float = 0
    lead_id: int | None = None
    source_category: str = ""
    work_type: str = ""
    additional_work_types: list[str] = Field(default_factory=list)
    customer_email: str = ""
    customer_id: int | None = None
    submission_key: str = ""




class AIQuoteDraftRequest(BaseModel):
    job_description: str = ""
    quote_type: str = "small"
    customer_name: str = ""
    customer_address: str = ""
    current_labour: float = 0
    current_materials: list[MaterialItem] = Field(default_factory=list)
    site_survey: dict = Field(default_factory=dict)


class InvoiceStatusRequest(BaseModel):
    status: str
    amount_paid: float = 0


class PaymentLinkUpdateRequest(BaseModel):
    payment_link: str = ""


class SendInvoiceEmailRequest(BaseModel):
    to_email: str
    message: str = ""


class LeadRequest(BaseModel):
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    job_type: str = "small"
    description: str = ""
    source: str = "website"
    postcode: str = ""
    urgency: str = ""
    preferred_contact: str = ""
    landing_page: str = ""
    referrer: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""
    source_category: str = ""
    work_type: str = ""
    additional_work_types: list[str] = Field(default_factory=list)
    submission_key: str = ""
    analytics_consent: bool = False


class LeadStatusRequest(BaseModel):
    status: str = "new"


class LeadClassificationRequest(BaseModel):
    source_category: str = ""
    work_type: str = ""
    additional_work_types: list[str] | None = None


class QuoteOutcomeRequest(BaseModel):
    status: str
    next_follow_up: str = ""
    loss_reason: str = ""
    loss_note: str = ""


class AppointmentRequest(BaseModel):
    lead_id: int
    job_id: int | None = None
    kind: str = "site_visit"
    status: str = "confirmed"
    starts_at: str
    ends_at: str
    provisional_follow_up: str = ""
    notes: str = ""


class JobRequest(BaseModel):
    operation_key: str = ""
    lead_id: int | None = None
    quote_id: int | None = None
    invoice_id: int | None = None
    title: str = ""
    status: str = "awaiting_schedule"
    notes: str = ""


class QuickAddPreviewRequest(BaseModel):
    message: str


class QuickAddConfirmRequest(BaseModel):
    idempotency_key: str
    name: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    description: str = ""
    source_category: str = ""
    work_type: str = ""
    additional_work_types: list[str] = Field(default_factory=list)
    contact_channel: str = "Unknown"
    record_kind: str = "unconfirmed"
    test_reference: str = ""
    customer_id: int | None = None
    visit_starts_at: str = ""
    visit_ends_at: str = ""
    visit_status: str = "confirmed"
    provisional_follow_up: str = ""


class InvoiceEditRequest(BaseModel):
    customer_name: str = ""
    customer_address: str = ""
    customer_phone: str = ""
    job: str = ""
    job_reference: str = ""
    labour: float = 0
    callout_charge: float = 0
    travel_charge: float = 0
    materials: float = 0
    due_date: str = ""
    payment_link: str = ""
    amount_paid: float = 0
    reminder_email: str = ""
    reminders_enabled: bool = False
