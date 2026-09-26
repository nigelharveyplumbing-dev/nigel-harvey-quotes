"""Request payload models with unchanged defaults."""

from pydantic import BaseModel, Field

class MaterialItem(BaseModel):
    name: str = ""
    quantity: float = 1
    supplier: str = ""
    url: str = ""
    manual_price: float = 0
    quote_charge_override: float | None = None
    material_type: str = "chargeable"
    charge_method: str = "full"
    quantity_source: str = "rule"
    learned_average_quantity: float | None = None
    learned_used_count: float | None = None


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


class LeadStatusRequest(BaseModel):
    status: str = "new"


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


