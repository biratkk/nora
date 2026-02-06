"""ACP HTTP Server — FastAPI-based ACP v0.2.0 compliant server.

Exposes Nora as an ACP agent via REST endpoints. Start with `nora acp`.

Endpoints:
    GET  /ping                     Health check
    GET  /agents                   List agents
    GET  /agents/{name}            Get agent manifest
    POST /runs                     Create a new run
    GET  /runs/{run_id}            Get run status
    GET  /runs/{run_id}/events     List run events (SSE)
    POST /runs/{run_id}            Resume an awaiting run
    POST /runs/{run_id}/cancel     Cancel a run
    GET  /sessions/{session_id}    Get session
"""

import asyncio
import json
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from nora.acp.models.agent_manifest import AgentManifest, get_nora_manifest
from nora.acp.models.error import AcpError, ErrorCode
from nora.acp.models.message import AcpMessage
from nora.acp.models.run import Run, RunCreateRequest, RunEvent, RunMode, RunResumeRequest, RunStatus
from nora.acp.models.session import Session
from nora.acp.runner import AcpRunner
from nora.repositories.run_repository import RunRepository
from nora.repositories.session_repository import SessionRepository


def create_app(profile: Optional[str] = None) -> FastAPI:
    """Create the ACP FastAPI application."""
    app = FastAPI(
        title="Nora ACP Server",
        description="ACP v0.2.0 compliant server exposing Nora as an AI coding assistant",
        version="0.2.0",
    )

    session_repo = SessionRepository()
    run_repo = RunRepository()
    runner = AcpRunner(
        session_repo=session_repo,
        run_repo=run_repo,
        profile=profile,
    )
    manifest = get_nora_manifest()

    # In-memory run cache for async runs
    _runs: dict[UUID, Run] = {}
    _run_events: dict[UUID, list[RunEvent]] = {}

    # --- Endpoints ---

    @app.get("/ping")
    async def ping() -> dict:
        return {}

    @app.get("/agents")
    async def list_agents(limit: int = 100, offset: int = 0) -> dict:
        agents = [manifest]
        return {"agents": [a.model_dump() for a in agents[offset : offset + limit]]}

    @app.get("/agents/{name}")
    async def get_agent(name: str) -> dict:
        if name != manifest.name:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Agent '{name}' not found",
                ).model_dump(),
            )
        return manifest.model_dump()

    @app.post("/runs")
    async def create_run(request: RunCreateRequest):
        # Validate agent name
        if request.agent_name != manifest.name:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Agent '{request.agent_name}' not found",
                ).model_dump(),
            )

        # Get or create session
        session: Session
        if request.session_id:
            loaded = session_repo.load(request.session_id)
            if loaded is None:
                raise HTTPException(
                    status_code=404,
                    detail=AcpError(
                        code=ErrorCode.NOT_FOUND,
                        message=f"Session '{request.session_id}' not found",
                    ).model_dump(),
                )
            session = loaded
        else:
            session = Session.create()
            session_repo.save(session)

        # Create the run
        run = Run.create(
            agent_name=request.agent_name,
            input_messages=request.input,
            session_id=session.id,
        )

        if request.mode == RunMode.SYNC:
            # Synchronous — block until complete
            completed_run = await runner.execute_sync(run, session)
            return completed_run.model_dump()

        elif request.mode == RunMode.STREAM:
            # Streaming — return SSE
            async def event_generator():
                async for event in runner.execute_stream(run, session):
                    yield {
                        "event": event.type.value,
                        "data": json.dumps(event.model_dump(), default=str),
                    }

            return EventSourceResponse(event_generator())

        else:
            # Async — return immediately, process in background
            _runs[run.run_id] = run
            _run_events[run.run_id] = []

            async def background_execute():
                async for event in runner.execute_stream(run, session):
                    _run_events.setdefault(run.run_id, []).append(event)

            asyncio.create_task(background_execute())
            return JSONResponse(status_code=202, content=run.model_dump(mode="json"))

    @app.get("/runs/{run_id}")
    async def get_run(run_id: UUID) -> dict:
        # Check in-memory first (for async runs)
        if run_id in _runs:
            return _runs[run_id].model_dump(mode="json")

        # Search across all sessions on disk
        for session in session_repo.list_all():
            run = run_repo.load(session.id, run_id)
            if run:
                return run.model_dump(mode="json")

        raise HTTPException(
            status_code=404,
            detail=AcpError(
                code=ErrorCode.NOT_FOUND,
                message=f"Run '{run_id}' not found",
            ).model_dump(),
        )

    @app.get("/runs/{run_id}/events")
    async def list_run_events(run_id: UUID) -> dict:
        events = _run_events.get(run_id, [])
        return {"events": [e.model_dump(mode="json") for e in events]}

    @app.post("/runs/{run_id}")
    async def resume_run(run_id: UUID, request: RunResumeRequest) -> dict:
        # For now, return not implemented
        raise HTTPException(
            status_code=501,
            detail=AcpError(
                code=ErrorCode.SERVER_ERROR,
                message="Run resume not yet implemented",
            ).model_dump(),
        )

    @app.post("/runs/{run_id}/cancel")
    async def cancel_run(run_id: UUID):
        # Try to cancel active run
        runner.cancel_run(run_id)

        # Update in-memory run if exists
        if run_id in _runs:
            _runs[run_id].request_cancel()
            return JSONResponse(
                status_code=202,
                content=_runs[run_id].model_dump(mode="json"),
            )

        raise HTTPException(
            status_code=404,
            detail=AcpError(
                code=ErrorCode.NOT_FOUND,
                message=f"Run '{run_id}' not found or not active",
            ).model_dump(),
        )

    @app.get("/sessions/{session_id}")
    async def get_session(session_id: UUID) -> dict:
        session = session_repo.load(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Session '{session_id}' not found",
                ).model_dump(),
            )
        return session.model_dump(mode="json")

    return app
