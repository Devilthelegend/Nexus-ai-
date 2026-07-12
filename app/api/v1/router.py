"""Aggregate router for API v1.

Business routers (auth, workspaces, documents, conversations, agents) are
registered here in later phases. Health probes are mounted at the root in
``app.main`` so orchestrators can reach them without a version prefix.
"""

from fastapi import APIRouter

from app.api.v1 import agents, auth, conversations, documents, workspaces

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(workspaces.router)
api_router.include_router(documents.router)
api_router.include_router(conversations.router)
api_router.include_router(agents.router)
