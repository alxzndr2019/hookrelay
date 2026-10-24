from fastapi import FastAPI

from app.api import health

app = FastAPI(
    title="HookRelay",
    version="0.1.0",
    description="Reliable multi-tenant webhook delivery service.",
)
app.include_router(health.router)