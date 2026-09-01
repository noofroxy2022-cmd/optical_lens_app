"""
التطبيق الرئيسي - FastAPI
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import companies, lens_models, prescriptions, pdf_import, uploads


app = FastAPI(
    title="Optical Lens Matcher API - Final",
    description="API نهائي لمطابقة العدسات البصرية",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(companies.router)
app.include_router(lens_models.router)
app.include_router(prescriptions.router)
app.include_router(pdf_import.router)
app.include_router(uploads.router)


@app.get("/")
def root():
    return {
        "message": "Optical Lens Matcher API - Final Version",
        "version": "3.0.0",
        "features": [
            "Transposition (CYL ±)",
            "Aspherical Recommendation",
            "Index Recommendation (1.50-1.74)",
            "Stock vs RX vs BOTH",
            "PDF Hybrid Parser",
            "Preview & Confirm Workflow",
            "Dynamic Company Management",
            "Google Vision OCR",
        ],
        "docs": "/docs",
    }


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "3.0.0"}
