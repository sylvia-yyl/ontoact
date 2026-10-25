"""OntoAct API: ontology queries, scenario studies, decision packages and apps."""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models  # noqa: F401  (registers every table on Base.metadata)
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.routers import ontologies
from app.routers.v2 import (decisions, logic_actions, logic_assets, object_query, object_sets, object_views,
                            ontology_queries, rule_runtime, scenario_studies, scenario_workbench, scenarios,
                            workshop_apps)
from app.services.v2 import mcp_server
from app.services.v2.scenario_execution import reconcile_interrupted_runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    from app.services.workspace_user import ensure_workspace_user
    with SessionLocal() as db:
        ensure_workspace_user(db)
    # Runs execute in this process, so any run still marked running belongs to a stopped process.
    reconcile_interrupted_runs()
    # The Ontology MCP endpoint (streamable HTTP) needs its session manager running for the app's lifetime.
    async with mcp_server.start().run():
        yield


app = FastAPI(title="OntoAct API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ontologies.router, prefix="/api/v1/ontologies", tags=["ontologies"])
for module, tag in ((object_query, "object-query"), (object_views, "object-views"), (object_sets, "object-sets"),
                    (logic_actions, "actions"), (logic_assets, "functions"), (scenarios, "scenarios"),
                    (scenario_workbench, "scenario-workspace"), (scenario_studies, "scenario-studies"),
                    (decisions, "decision-packages"), (rule_runtime, "rules"), (workshop_apps, "apps"),
                    (ontology_queries, "ontology-queries")):
    app.include_router(module.router, prefix="/api/v2/ontologies", tags=[tag])
app.mount("/api/v2/mcp", mcp_server.http_app)


@app.get("/api/health")
def health():
    from app.services.v2.graph.falkordb_service import FalkorDBService
    return {"status": "ok", "graph": "ok" if FalkorDBService().available else "unavailable"}
