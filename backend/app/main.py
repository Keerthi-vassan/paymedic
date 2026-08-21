from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import audit, config_rules, metrics, payments, pipeline

app = FastAPI(title="Revenue Recovery Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(payments.router)
app.include_router(pipeline.router)
app.include_router(audit.router)
app.include_router(metrics.router)
app.include_router(config_rules.router)


@app.get("/health")
def health():
    return {"status": "ok"}
