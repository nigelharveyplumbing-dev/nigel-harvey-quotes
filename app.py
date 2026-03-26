from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class QuoteRequest(BaseModel):
    job_description: str
    labour_cost: float = 0
    materials_cost: float = 0

@app.get("/")
def home():
    return {"message": "Nigel Harvey Quotes API running"}

@app.post("/quote")
def create_quote(data: QuoteRequest):
    materials_with_margin = round(data.materials_cost * 1.25, 2)
    total = data.labour_cost + materials_with_margin

    return {
        "job": data.job_description,
        "labour": data.labour_cost,
        "materials_estimated": data.materials_cost,
        "materials_with_margin": materials_with_margin,
        "total_price": total
    }
