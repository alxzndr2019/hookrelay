from fastapi import FastAPI

from app.api import endpoints, health, whoami

app = FastAPI(
    title="HookRelay",
    version="0.1.0",
    description="Reliable multi-tenant webhook delivery service.",
)
app.include_router(health.router)
app.include_router(whoami.router)
app.include_router(endpoints.router)