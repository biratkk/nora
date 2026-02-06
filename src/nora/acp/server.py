"""ACP HTTP Server — FastAPI-based ACP v0.2.0 compliant server.

Exposes Nora as an ACP agent via REST endpoints. Start with `nora acp`.

Endpoints:
    GET  /ping                        Health check
    GET  /agents                      List agents
    GET  /agents/{name}               Get agent manifest
    POST /runs                        Create a new run
    GET  /runs/{run_id}               Get run status
    GET  /runs/{run_id}/events        List run events (SSE)
    POST /runs/{run_id}               Resume an awaiting run
    POST /runs/{run_id}/cancel        Cancel a run
    GET  /sessions                    List all sessions
    POST /sessions                    Create a new session
    GET  /sessions/{session_id}       Get session
    GET  /sessions/{session_id}/runs  List runs for a session
"""

import asyncio
import json
from typing import Optional, Union
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from nora.acp.models.agent_manifest import AgentManifest, get_nora_manifest
from nora.acp.models.error import AcpError, ErrorCode
from nora.acp.models.responses import (
    ListAgentsResponse,
    ListRunEventsResponse,
    ListSessionRunsResponse,
    ListSessionsResponse,
    PingResponse,
    SessionCreateRequest,
)
from nora.acp.models.run import Run, RunCreateRequest, RunEvent, RunMode, RunResumeRequest
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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
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

    @app.get(
        "/ping",
        response_model=PingResponse,
        summary="Health check",
        description="Returns an empty object to confirm the server is running.",
        tags=["Health"],
    )
    async def ping() -> PingResponse:
        return PingResponse()

    @app.get(
        "/agents",
        response_model=ListAgentsResponse,
        summary="List available agents",
        description="Returns a paginated list of agents hosted by this server.",
        tags=["Agents"],
    )
    async def list_agents(
        limit: int = Query(default=100, ge=1, le=1000, description="Maximum number of agents to return"),
        offset: int = Query(default=0, ge=0, description="Number of agents to skip"),
    ) -> ListAgentsResponse:
        agents = [manifest]
        return ListAgentsResponse(agents=agents[offset : offset + limit])

    @app.get(
        "/agents/{name}",
        response_model=AgentManifest,
        summary="Get agent manifest",
        description="Returns the full manifest for a specific agent, including capabilities and metadata.",
        tags=["Agents"],
    )
    async def get_agent(name: str) -> AgentManifest:
        if name != manifest.name:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Agent '{name}' not found",
                ).model_dump(),
            )
        return manifest

    @app.post(
        "/runs",
        response_model=Run,
        summary="Create a new run",
        description=(
            "Submit input messages to an agent for processing. "
            "Supports three execution modes:\n\n"
            "- **sync** — blocks until the run completes and returns the full Run.\n"
            "- **stream** — returns a Server-Sent Events stream of RunEvents.\n"
            "- **async** — returns immediately with a 202 and the Run in 'created' state; "
            "poll GET /runs/{run_id} for updates."
        ),
        responses={
            200: {"description": "Completed run (sync mode)", "model": Run},
            202: {"description": "Accepted (async mode)", "model": Run},
        },
        tags=["Runs"],
    )
    async def create_run(request: RunCreateRequest) -> Union[Run, JSONResponse, EventSourceResponse]:
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
            agent_mode=request.agent_mode,
        )

        if request.mode == RunMode.SYNC:
            # Synchronous — block until complete
            completed_run = await runner.execute_sync(run, session)
            return completed_run

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

    @app.get(
        "/runs/{run_id}",
        response_model=Run,
        summary="Get run status",
        description="Returns the current state of a run, including status, input, output, and errors.",
        tags=["Runs"],
    )
    async def get_run(run_id: UUID) -> Run:
        # Check in-memory first (for async runs)
        if run_id in _runs:
            return _runs[run_id]

        # Search across all sessions on disk
        for session in session_repo.list_all():
            run = run_repo.load(session.id, run_id)
            if run:
                return run

        raise HTTPException(
            status_code=404,
            detail=AcpError(
                code=ErrorCode.NOT_FOUND,
                message=f"Run '{run_id}' not found",
            ).model_dump(),
        )

    @app.get(
        "/runs/{run_id}/events",
        response_model=ListRunEventsResponse,
        summary="List run events",
        description="Returns all events emitted during an async run. Only available for runs started in async mode.",
        tags=["Runs"],
    )
    async def list_run_events(run_id: UUID) -> ListRunEventsResponse:
        events = _run_events.get(run_id, [])
        return ListRunEventsResponse(events=events)

    @app.post(
        "/runs/{run_id}",
        response_model=Run,
        summary="Resume an awaiting run",
        description="Provide client input to resume a run that is in the 'awaiting' state.",
        tags=["Runs"],
    )
    async def resume_run(run_id: UUID, request: RunResumeRequest) -> Run:
        # For now, return not implemented
        raise HTTPException(
            status_code=501,
            detail=AcpError(
                code=ErrorCode.SERVER_ERROR,
                message="Run resume not yet implemented",
            ).model_dump(),
        )

    @app.post(
        "/runs/{run_id}/cancel",
        response_model=Run,
        summary="Cancel a run",
        description=(
            "Request cancellation of an active run. Returns 202 with the run in 'cancelling' state. "
            "The run will transition to 'cancelled' once processing stops."
        ),
        responses={202: {"description": "Cancellation accepted", "model": Run}},
        tags=["Runs"],
    )
    async def cancel_run(run_id: UUID) -> JSONResponse:
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

    @app.get(
        "/sessions",
        response_model=ListSessionsResponse,
        summary="List all sessions",
        description="Returns all sessions, including metadata such as name, mode, and timestamps.",
        tags=["Sessions"],
    )
    async def list_sessions() -> ListSessionsResponse:
        return ListSessionsResponse(sessions=session_repo.list_all())

    @app.post(
        "/sessions",
        response_model=Session,
        status_code=201,
        summary="Create a new session",
        description="Create a new conversation session with an optional name and mode.",
        tags=["Sessions"],
    )
    async def create_session(request: SessionCreateRequest = SessionCreateRequest()) -> Session:
        session = Session.create()
        if request.name:
            session.metadata.name = request.name
        session_repo.save(session)
        return session

    @app.get(
        "/sessions/{session_id}",
        response_model=Session,
        summary="Get session details",
        description="Returns a session by ID, including its metadata.",
        tags=["Sessions"],
    )
    async def get_session(session_id: UUID) -> Session:
        session = session_repo.load(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Session '{session_id}' not found",
                ).model_dump(),
            )
        return session

    @app.get(
        "/sessions/{session_id}/runs",
        response_model=ListSessionRunsResponse,
        summary="List runs for a session",
        description="Returns all runs belonging to a session, ordered by creation time.",
        tags=["Sessions"],
    )
    async def list_session_runs(session_id: UUID) -> ListSessionRunsResponse:
        session = session_repo.load(session_id)
        if session is None:
            raise HTTPException(
                status_code=404,
                detail=AcpError(
                    code=ErrorCode.NOT_FOUND,
                    message=f"Session '{session_id}' not found",
                ).model_dump(),
            )
        return ListSessionRunsResponse(runs=run_repo.list_for_session(session_id))

    return app
