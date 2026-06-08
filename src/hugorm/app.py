from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import httpx
from aiortc import RTCPeerConnection, RTCSessionDescription
from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field

from .logging_setup import configure_logging

configure_logging()

from . import api_tokens as api_token_util
from . import billing
from .asr.faster_whisper import FasterWhisperBackend
from .auth.deps import AuthContext, active_tenant, auth_context, current_user, require_role
from .auth.jwt import JWTVerifier
from .config import Settings
from .db.postgres import Database, SessionRow
from .diarization.pyannote import PyannoteDiarizer
from .documents.service import DocumentService
from .extraction.agent import ExtractionAgent
from .graph.resolver import GraphResolver
from .graph.store import Entity
from .llm.agent import RefinementAgent
from .llm.model import make_llm_model
from .pipeline.session import SessionConfig, SessionSnapshot
from .quota import get_limits
from .storage.base import ObjectStorage
from .storage.local import LocalObjectStorage
from .storage.supabase import SupabaseObjectStorage
from .transport.webrtc import WebRTCAudioSink

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"


class Offer(BaseModel):
    sdp: str
    type: str


class CreateTenantIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=60, pattern=r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class InviteIn(BaseModel):
    email: EmailStr
    role: str = Field("member", pattern=r"^(owner|admin|member)$")


class CreateTokenIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class VerifyCheckoutIn(BaseModel):
    session_id: str


class ClientErrorIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    stack: str | None = Field(default=None, max_length=20_000)
    url: str | None = Field(default=None, max_length=2_000)
    user_agent: str | None = Field(default=None, max_length=500)
    context: dict = Field(default_factory=dict)


def _build_storage(settings: Settings) -> ObjectStorage:
    if settings.storage_backend == "local":
        return LocalObjectStorage(settings.storage_local_root)
    key = settings.storage_service_key
    if not key:
        logger.warning(
            "HUGORM_STORAGE_SERVICE_KEY not set — Supabase Storage uploads will fail."
        )
        key = ""
    return SupabaseObjectStorage(
        base_url=settings.storage_url,
        service_key=key,
        bucket=settings.storage_bucket,
    )


def _spawn_background(app: FastAPI, coro) -> asyncio.Task:
    tasks: set[asyncio.Task] = app.state.background_tasks
    task = asyncio.create_task(coro)
    tasks.add(task)
    task.add_done_callback(tasks.discard)
    return task


def _slugify(value: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return s or "workspace"


async def _ensure_default_workspace(db: Database, ctx: AuthContext):
    existing = await db.list_user_tenants(ctx.user_id)
    if existing:
        return existing
    base_name = (ctx.email or "workspace").split("@")[0] or "workspace"
    slug = f"{_slugify(base_name)}-{ctx.user_id[:8]}"
    name = f"{base_name}'s workspace"
    try:
        t = await db.create_tenant_with_owner(name=name, slug=slug, user_id=ctx.user_id)
    except Exception:
        logger.exception("auto-workspace creation failed for %s", ctx.user_id)
        return existing
    return [t]


async def _enforce_owned_workspace_quota(db: Database, ctx: AuthContext) -> None:
    """Free users get one owned workspace. Upgrade any workspace to Pro to lift this."""
    owned = [t for t in await db.list_user_tenants(ctx.user_id) if t.role == "owner"]
    any_pro = any(t.plan == "pro" for t in owned)
    from .quota import FREE, PRO
    limit = PRO.workspaces_per_user if any_pro else FREE.workspaces_per_user
    if len(owned) >= limit:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="workspace quota reached — upgrade an existing workspace to create more",
        )


async def _enforce_transcription_quota(db: Database, tenant_id: UUID) -> None:
    usage = await db.get_tenant_usage(tenant_id)
    limits = get_limits(usage.plan)
    if usage.transcription_seconds >= limits.transcription_seconds_per_month:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="transcription quota exceeded — upgrade to continue",
        )


async def _enforce_document_quota(db: Database, tenant_id: UUID) -> None:
    usage = await db.get_tenant_usage(tenant_id)
    limits = get_limits(usage.plan)
    if usage.documents >= limits.documents_per_month:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            detail="document upload quota exceeded — upgrade to continue",
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    state: dict = {"pcs": set()}

    if not settings.supabase_jwt_secret:
        raise RuntimeError(
            "HUGORM_SUPABASE_JWT_SECRET is required. "
            "Run `uv run python deploy/gen_secrets.py > deploy/.env` and copy JWT_SECRET into .env."
        )
    if not settings.database_url:
        raise RuntimeError(
            "HUGORM_DATABASE_URL is required "
            "(e.g. postgres://postgres:<password>@localhost:54322/postgres)."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.background_tasks = set()

        logger.info("connecting to Postgres")
        db = Database(settings.database_url)
        await db.connect()
        app.state.db = db

        app.state.jwt_verifier = JWTVerifier(
            settings.supabase_jwt_secret, audience=settings.supabase_jwt_audience
        )
        app.state.settings = settings

        logger.info("loading ASR: %s (beam=%d)", settings.asr_model, settings.asr_beam_size)
        state["asr"] = FasterWhisperBackend(
            model_size=settings.asr_model,
            device=settings.device,
            compute_type=settings.compute_type,
            beam_size=settings.asr_beam_size,
        )
        if settings.hf_token:
            logger.info("loading diarization: %s", settings.diarization_model)
            state["diarizer"] = PyannoteDiarizer(
                model=settings.diarization_model,
                hf_token=settings.hf_token,
                device=settings.device,
            )
        else:
            logger.warning("HUGORM_HF_TOKEN not set — diarization disabled")
            state["diarizer"] = None

        resolver = GraphResolver(settings.data_dir) if settings.refinement_enabled else None
        agent: RefinementAgent | None = None
        extraction_agent: ExtractionAgent | None = None
        if settings.refinement_enabled:
            try:
                model = make_llm_model(settings)
                agent = RefinementAgent(model)
                extraction_agent = ExtractionAgent(model)
                logger.info("LLM enabled (model=%s)", settings.llm_model)
            except Exception:
                logger.exception("LLM init failed — refinement/extraction disabled")
        state["resolver"] = resolver
        state["agent"] = agent
        state["extraction_agent"] = extraction_agent

        storage = _build_storage(settings)
        try:
            await storage.ensure_ready()
            logger.info("storage backend '%s' ready", settings.storage_backend)
        except Exception:
            logger.exception(
                "storage backend '%s' failed to initialise", settings.storage_backend
            )
        state["storage"] = storage
        if resolver is not None:
            state["documents"] = DocumentService(
                db=db, storage=storage, resolver=resolver,
                agent=extraction_agent,
                spawn_task=lambda coro: _spawn_background(app, coro),
            )
        else:
            state["documents"] = None

        try:
            yield
        finally:
            for pc in list(state["pcs"]):
                await pc.close()
            state["pcs"].clear()
            tasks = app.state.background_tasks
            if tasks:
                logger.info("waiting for %d background tasks", len(tasks))
                await asyncio.gather(*tasks, return_exceptions=True)
            await db.close()

    app = FastAPI(lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    request_logger = logging.getLogger("hugorm.request")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            request_logger.exception(
                "%s %s -> 500 (%.0fms)", request.method, request.url.path, duration_ms
            )
            raise
        duration_ms = (time.perf_counter() - start) * 1000
        code = response.status_code
        level = logging.INFO
        if code >= 500:
            level = logging.ERROR
        elif code >= 400:
            level = logging.WARNING
        request_logger.log(
            level, "%s %s -> %d (%.0fms)", request.method, request.url.path, code, duration_ms
        )
        return response

    if STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # ---------- basics ----------

    @app.get("/")
    async def root():
        index = STATIC_DIR / "index.html"
        if not index.is_file():
            return JSONResponse({"error": "static/index.html not found"}, status_code=404)
        return FileResponse(index)

    @app.get("/healthz")
    async def healthz():
        return {
            "status": "ok",
            "diarization": state.get("diarizer") is not None,
            "refinement": state.get("agent") is not None,
            "documents": state.get("documents") is not None,
            "billing": bool(settings.stripe_secret_key and settings.stripe_price_id),
        }

    # ---------- me / tenants ----------

    @app.get("/me")
    async def me(ctx: AuthContext = Depends(current_user)):
        return {"id": ctx.user_id, "email": ctx.email, "role": ctx.role, "auth_source": ctx.source}

    @app.get("/me/tenants")
    async def my_tenants(ctx: AuthContext = Depends(current_user)):
        db: Database = app.state.db
        summaries = await db.list_user_tenants(ctx.user_id)
        if not summaries and ctx.source == "jwt":
            summaries = await _ensure_default_workspace(db, ctx)
        return [
            {"id": str(s.id), "name": s.name, "slug": s.slug, "role": s.role, "plan": s.plan}
            for s in summaries
        ]

    @app.post("/tenants", status_code=201)
    async def create_tenant(
        body: CreateTenantIn,
        ctx: AuthContext = Depends(current_user),
    ):
        db: Database = app.state.db
        if ctx.source != "jwt":
            raise HTTPException(403, "API tokens cannot create workspaces")
        await _enforce_owned_workspace_quota(db, ctx)
        try:
            t = await db.create_tenant_with_owner(body.name, body.slug, ctx.user_id)
        except Exception as e:  # noqa: BLE001
            if "tenants_slug_key" in str(e):
                raise HTTPException(409, "slug already taken") from e
            raise
        return {"id": str(t.id), "name": t.name, "slug": t.slug, "role": t.role, "plan": t.plan}

    @app.get("/tenants/{tenant_id}/usage")
    async def tenant_usage(
        tenant_id: UUID,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tid = auth
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        usage = await app.state.db.get_tenant_usage(tid)
        return usage.to_dict()

    # ---------- members / invitations ----------

    @app.get("/tenants/{tenant_id}/members")
    async def list_members(
        tenant_id: UUID,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tid = auth
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        rows = await app.state.db.list_members(tid)
        return [
            {
                "user_id": str(r.user_id),
                "email": r.email,
                "role": r.role,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    @app.delete("/tenants/{tenant_id}/members/{user_id}", status_code=204)
    async def remove_member(
        tenant_id: UUID,
        user_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner", "admin"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        if str(user_id) == ctx.user_id:
            raise HTTPException(400, "cannot remove yourself; transfer ownership first")
        members = await app.state.db.list_members(tid)
        target = next((m for m in members if m.user_id == user_id), None)
        if target is None:
            raise HTTPException(404, "member not found")
        if target.role == "owner":
            raise HTTPException(400, "cannot remove an owner")
        await app.state.db.remove_member(tid, str(user_id))
        return Response(status_code=204)

    @app.get("/tenants/{tenant_id}/invitations")
    async def list_invites(
        tenant_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner", "admin"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        rows = await app.state.db.list_invitations(tid)
        return [
            {
                "id": str(r.id),
                "email": r.email,
                "role": r.role,
                "token": r.token,
                "invite_url": f"{settings.frontend_url}/accept?token={r.token}",
                "expires_at": r.expires_at.isoformat(),
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    @app.post("/tenants/{tenant_id}/invitations", status_code=201)
    async def create_invite(
        tenant_id: UUID,
        body: InviteIn,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner", "admin"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        token = secrets.token_urlsafe(24)
        expires = datetime.now(timezone.utc) + timedelta(days=settings.invitation_expires_days)
        inv = await app.state.db.create_invitation(
            tenant_id=tid,
            email=str(body.email),
            role=body.role,
            invited_by=UUID(ctx.user_id),
            token=token,
            expires_at=expires,
        )
        return {
            "id": str(inv.id),
            "email": inv.email,
            "role": inv.role,
            "token": inv.token,
            "invite_url": f"{settings.frontend_url}/accept?token={inv.token}",
            "expires_at": inv.expires_at.isoformat(),
        }

    @app.delete("/tenants/{tenant_id}/invitations/{invitation_id}", status_code=204)
    async def delete_invite(
        tenant_id: UUID,
        invitation_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner", "admin"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        await app.state.db.delete_invitation(invitation_id, tid)
        return Response(status_code=204)

    @app.get("/invitations/{token}")
    async def preview_invite(token: str):
        inv = await app.state.db.get_invitation_by_token(token)
        if inv is None or inv.accepted_at is not None:
            raise HTTPException(404, "invitation not found or already accepted")
        if inv.expires_at < datetime.now(timezone.utc):
            raise HTTPException(410, "invitation expired")
        tenant = await app.state.db.get_tenant(inv.tenant_id)
        return {
            "email": inv.email,
            "role": inv.role,
            "tenant_name": tenant.name if tenant else "—",
            "expires_at": inv.expires_at.isoformat(),
        }

    @app.post("/invitations/{token}/accept")
    async def accept_invite(
        token: str, ctx: AuthContext = Depends(current_user),
    ):
        if ctx.source != "jwt" or not ctx.email:
            raise HTTPException(403, "sign in with an email account to accept invitations")
        inv = await app.state.db.get_invitation_by_token(token)
        if inv is None or inv.accepted_at is not None:
            raise HTTPException(404, "invitation not found or already accepted")
        if inv.expires_at < datetime.now(timezone.utc):
            raise HTTPException(410, "invitation expired")
        if inv.email.lower() != ctx.email.lower():
            raise HTTPException(403, "invitation was issued to a different email")
        await app.state.db.accept_invitation(inv, ctx.user_id)
        tenant = await app.state.db.get_tenant(inv.tenant_id)
        return {
            "tenant_id": str(inv.tenant_id),
            "tenant_name": tenant.name if tenant else None,
            "role": inv.role,
        }

    # ---------- API tokens ----------

    @app.get("/tenants/{tenant_id}/api_tokens")
    async def list_tokens(
        tenant_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _ctx, tid = await require_role(auth, request, {"owner", "admin", "member"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        rows = await app.state.db.list_api_tokens(tid)
        return [
            {
                "id": str(r.id),
                "name": r.name,
                "prefix": r.prefix,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ]

    @app.post("/tenants/{tenant_id}/api_tokens", status_code=201)
    async def create_token(
        tenant_id: UUID,
        body: CreateTokenIn,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner", "admin", "member"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        if ctx.source != "jwt":
            raise HTTPException(403, "API tokens cannot mint other tokens")
        plaintext, prefix, token_hash = api_token_util.generate()
        row = await app.state.db.create_api_token(
            tenant_id=tid,
            user_id=UUID(ctx.user_id),
            name=body.name,
            prefix=prefix,
            token_hash=token_hash,
        )
        return {
            "id": str(row.id),
            "name": row.name,
            "prefix": row.prefix,
            "token": plaintext,  # shown ONCE
            "created_at": row.created_at.isoformat(),
        }

    @app.delete("/tenants/{tenant_id}/api_tokens/{token_id}", status_code=204)
    async def revoke_token(
        tenant_id: UUID,
        token_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _ctx, tid = await require_role(auth, request, {"owner", "admin", "member"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        await app.state.db.revoke_api_token(token_id, tid)
        return Response(status_code=204)

    # ---------- billing ----------

    @app.post("/tenants/{tenant_id}/billing/checkout")
    async def billing_checkout(
        tenant_id: UUID,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        try:
            url = billing.create_checkout_url(settings, str(tid), ctx.email)
        except billing.BillingDisabled as e:
            raise HTTPException(503, str(e)) from e
        return {"url": url}

    @app.post("/tenants/{tenant_id}/billing/verify")
    async def billing_verify(
        tenant_id: UUID,
        body: VerifyCheckoutIn,
        request: Request,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tid = await require_role(auth, request, {"owner"})
        if tid != tenant_id:
            raise HTTPException(403, "tenant id mismatch")
        try:
            result = billing.verify_checkout(settings, body.session_id)
        except billing.BillingDisabled as e:
            raise HTTPException(400, str(e)) from e
        if result.tenant_id != str(tid):
            raise HTTPException(403, "checkout session was for a different tenant")
        await app.state.db.set_tenant_plan(
            tid, "pro",
            stripe_customer_id=result.customer_id,
            stripe_subscription_id=result.subscription_id,
        )
        return {"plan": "pro"}

    # ---------- sessions ----------

    @app.get("/sessions")
    async def list_sessions(
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tenant_id = auth
        rows = await app.state.db.list_sessions(tenant_id)
        return [
            {
                "id": str(r["id"]),
                "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                "ended_at": r["ended_at"].isoformat() if r["ended_at"] else None,
                "language": r["language"],
                "raw_word_count": r["raw_word_count"],
                "refined_turn_count": r["refined_turn_count"],
            }
            for r in rows
        ]

    @app.get("/sessions/{session_id}")
    async def get_session(
        session_id: UUID,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tenant_id = auth
        row = await app.state.db.get_session(session_id, tenant_id)
        if row is None:
            raise HTTPException(404, "session not found")
        return {
            "id": str(row["id"]),
            "started_at": row["started_at"].isoformat() if row["started_at"] else None,
            "ended_at": row["ended_at"].isoformat() if row["ended_at"] else None,
            "language": row["language"],
            "raw_words": json.loads(row["raw_words"]) if isinstance(row["raw_words"], str) else row["raw_words"],
            "refined_turns": json.loads(row["refined_turns"]) if isinstance(row["refined_turns"], str) else row["refined_turns"],
        }

    # ---------- graph ----------

    @app.get("/graph/entities")
    async def list_entities(
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tenant_id = auth
        resolver: GraphResolver | None = state.get("resolver")
        if resolver is None:
            return []
        store = await resolver.tenant_store(str(tenant_id))
        entities = await asyncio.to_thread(store.all_entities)
        return [
            {
                "id": e.id, "name": e.name, "type": e.type,
                "aliases": e.aliases, "description": e.description,
            }
            for e in entities
        ]

    # ---------- documents ----------

    @app.post("/documents")
    async def upload_document(
        file: UploadFile,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        ctx, tenant_id = auth
        svc: DocumentService | None = state.get("documents")
        if svc is None:
            raise HTTPException(503, "document service disabled")
        await _enforce_document_quota(app.state.db, tenant_id)
        data = await file.read()
        if not data:
            raise HTTPException(400, "empty upload")
        record = await svc.upload(
            tenant_id=tenant_id,
            user_id=ctx.user_id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            data=data,
        )
        return {
            "id": str(record.id),
            "filename": record.filename,
            "status": record.status,
            "size_bytes": record.size_bytes,
        }

    @app.get("/documents")
    async def list_documents(
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
    ):
        _, tenant_id = auth
        svc: DocumentService | None = state.get("documents")
        if svc is None:
            raise HTTPException(503, "document service disabled")
        rows = await svc.list_for_tenant(tenant_id)
        return [
            {
                "id": str(r.id), "filename": r.filename,
                "content_type": r.content_type, "size_bytes": r.size_bytes,
                "status": r.status, "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    # ---------- WebRTC offer ----------

    @app.post("/offer")
    async def offer(
        offer: Offer,
        auth: tuple[AuthContext, UUID] = Depends(active_tenant),
        lang: str | None = None,
        speakers: int | None = None,
    ) -> JSONResponse:
        ctx, tenant_id = auth
        await _enforce_transcription_quota(app.state.db, tenant_id)
        pc = RTCPeerConnection()
        state["pcs"].add(pc)

        resolver: GraphResolver | None = state.get("resolver")
        fetch_entities = None
        if resolver is not None:
            tenant_str = str(tenant_id)

            async def fetch_entities():  # noqa: D401
                return await resolver.fetch_entities(tenant_str, ctx.user_id)

        extraction_agent: ExtractionAgent | None = state.get("extraction_agent")

        async def on_session_end(snapshot: SessionSnapshot) -> None:
            try:
                await app.state.db.insert_session(
                    SessionRow(
                        id=UUID(snapshot.session_id),
                        tenant_id=tenant_id,
                        user_id=UUID(ctx.user_id),
                        started_at=snapshot.started_at,
                        ended_at=snapshot.ended_at,
                        language=snapshot.language,
                        raw_words=[w.model_dump() for w in snapshot.words],
                        refined_turns=[t.model_dump() for t in snapshot.refined_turns],
                        meta={},
                    )
                )
            except Exception:
                logger.exception("session persistence failed for %s", snapshot.session_id)
            if resolver is not None and extraction_agent is not None:
                _spawn_background(
                    app,
                    _extract_from_transcript(
                        db=app.state.db, tenant_id=tenant_id,
                        snapshot=snapshot, resolver=resolver,
                        agent=extraction_agent,
                    ),
                )

        WebRTCAudioSink(
            pc=pc,
            asr=state["asr"],
            diarizer=state.get("diarizer"),
            agent=state.get("agent"),
            fetch_entities=fetch_entities,
            on_session_end=on_session_end,
            session_config=SessionConfig(
                language=lang or settings.default_language,
                window_s=settings.window_s,
                overlap_s=settings.overlap_s,
                diarization_interval_s=settings.diarization_interval_s,
                diarization_window_s=settings.diarization_window_s,
                finalize_lag_s=settings.finalize_lag_s,
                num_speakers=speakers if speakers is not None else settings.num_speakers,
                min_speakers=settings.min_speakers,
                max_speakers=settings.max_speakers,
            ),
        )

        @pc.on("connectionstatechange")
        async def _on_state() -> None:
            if pc.connectionState in ("failed", "closed"):
                state["pcs"].discard(pc)

        await pc.setRemoteDescription(RTCSessionDescription(sdp=offer.sdp, type=offer.type))
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        return JSONResponse(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        )

    # ---------- client error reporting ----------

    client_logger = logging.getLogger("hugorm.client")

    @app.post("/client-errors", status_code=204)
    async def log_client_error(body: ClientErrorIn, request: Request):
        origin = request.headers.get("referer") or body.url or "?"
        ua = body.user_agent or request.headers.get("user-agent") or "?"
        client_logger.error(
            "[client] %s | url=%s | ua=%s | ctx=%s\n%s",
            body.message,
            origin,
            ua,
            body.context,
            body.stack or "(no stack)",
        )
        return Response(status_code=204)

    # ---------- /auth/v1/* proxy ----------

    @app.api_route(
        "/auth/v1/{path:path}",
        methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    )
    async def auth_proxy(path: str, request: Request) -> Response:
        url = f"{settings.gotrue_url.rstrip('/')}/{path}"
        upstream_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in {"host", "content-length", "connection"}
        }
        body = await request.body()
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.request(
                request.method, url,
                headers=upstream_headers,
                params=dict(request.query_params),
                content=body,
            )
        safe_headers = {
            k: v for k, v in resp.headers.items()
            if k.lower() not in {"content-length", "transfer-encoding", "connection"}
        }
        return Response(
            content=resp.content, status_code=resp.status_code, headers=safe_headers
        )

    return app


async def _extract_from_transcript(
    db: Database,
    tenant_id: UUID,
    snapshot: SessionSnapshot,
    resolver: GraphResolver,
    agent: ExtractionAgent,
) -> None:
    text = _snapshot_text(snapshot)
    if not text.strip():
        return
    store = await resolver.tenant_store(str(tenant_id))
    existing = await asyncio.to_thread(store.all_entities)
    try:
        result = await agent.extract(text, existing)
    except Exception:
        logger.exception("post-transcript extraction failed for %s", snapshot.session_id)
        return
    for proposed in result.entities:
        store.upsert_entity(
            Entity(
                id=proposed.id, name=proposed.name, type=proposed.type,
                aliases=list(proposed.aliases), description=proposed.description,
            )
        )
        try:
            await db.record_entity_source(
                tenant_id=tenant_id, entity_id=proposed.id,
                source_type="transcript", source_ref=UUID(snapshot.session_id),
                needs_enrichment=proposed.needs_enrichment,
            )
        except Exception:
            logger.exception("failed to record entity source for %s", proposed.id)
    logger.info(
        "post-transcript extraction for %s: %d entities", snapshot.session_id, len(result.entities)
    )


def _snapshot_text(snapshot: SessionSnapshot) -> str:
    if snapshot.refined_turns:
        return "\n".join(
            f"{t.speaker or 'SPEAKER_?'}: {t.text}" for t in snapshot.refined_turns
        )
    return " ".join(w.text for w in snapshot.words)


app = create_app()
