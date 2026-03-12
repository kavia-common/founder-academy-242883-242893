from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, StringConstraints
from typing_extensions import Annotated

#
# App metadata / tags
#

openapi_tags = [
    {"name": "System", "description": "Health checks and system metadata."},
    {"name": "Auth", "description": "Email/password auth and access tokens."},
    {"name": "Users", "description": "User profiles and settings."},
    {"name": "Curriculum", "description": "Roadmaps, modules, and lessons."},
    {
        "name": "Sessions",
        "description": "Simulations/coaching sessions including conversational turns.",
    },
    {"name": "Progress", "description": "Progress tracking across curriculum and sessions."},
    {"name": "Gamification", "description": "XP, levels, badges and leaderboards."},
]

app = FastAPI(
    title="FouGuide Backend API",
    description=(
        "REST API for FouGuide (Founder's Guide) - an AI-powered gamified founder LMS. "
        "This service provides auth, user profiles, curriculum/roadmap, sessions/simulations "
        "with conversational turns, progress tracking, and gamification primitives.\n\n"
        "Note: This implementation uses an in-memory store suitable for early integration "
        "and frontend development. Data will reset on process restart."
    ),
    version="0.2.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Frontend dev convenience; tighten for production deployments.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#
# Error handling
#


class ApiErrorCode(str, Enum):
    """Stable error codes for frontend handling."""

    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(BaseModel):
    """Standard error envelope."""

    code: ApiErrorCode = Field(..., description="Stable error code.")
    message: str = Field(..., description="Human-readable error message.")
    details: Optional[Dict[str, Any]] = Field(
        default=None, description="Optional structured error details."
    )
    request_id: str = Field(..., description="Request correlation ID.")


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    """Attach a request id to every response and store it in request.state."""
    request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
    request.state.request_id = request_id
    response: Response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    return response


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Convert FastAPI HTTPException into the standard ApiError format."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    # Preserve structured payload if provided.
    details: Optional[Dict[str, Any]] = None
    message = "Request failed"
    code = ApiErrorCode.INTERNAL_ERROR

    if isinstance(exc.detail, dict):
        message = str(exc.detail.get("message") or message)
        details = exc.detail.get("details")
        code = ApiErrorCode(str(exc.detail.get("code") or code))
    elif isinstance(exc.detail, str):
        message = exc.detail

    # Best-effort map common status codes to stable codes.
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = ApiErrorCode.UNAUTHORIZED
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = ApiErrorCode.FORBIDDEN
    elif exc.status_code == status.HTTP_404_NOT_FOUND:
        code = ApiErrorCode.NOT_FOUND
    elif exc.status_code == status.HTTP_409_CONFLICT:
        code = ApiErrorCode.CONFLICT
    elif exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
        code = ApiErrorCode.VALIDATION_ERROR

    payload = ApiError(code=code, message=message, details=details, request_id=request_id)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler to keep responses consistent."""
    request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
    payload = ApiError(
        code=ApiErrorCode.INTERNAL_ERROR,
        message="Internal server error",
        details={"exception": exc.__class__.__name__},
        request_id=request_id,
    )
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload.model_dump())


#
# In-memory store (prototype)
#


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class _Store:
    """In-memory database for prototype usage."""

    def __init__(self) -> None:
        self.users: Dict[str, Dict[str, Any]] = {}
        self.tokens: Dict[str, str] = {}  # token -> user_id
        self.curricula: Dict[str, Dict[str, Any]] = {}
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.progress: Dict[str, Dict[str, Any]] = {}  # user_id -> progress document
        self.badges: Dict[str, Dict[str, Any]] = {}
        self.user_badges: Dict[str, List[str]] = {}  # user_id -> badge_ids


STORE = _Store()


def _seed_data() -> None:
    """Seed minimal curriculum and badges for immediate frontend use."""
    if STORE.curricula:
        return

    roadmap_id = "roadmap-foundations"
    STORE.curricula[roadmap_id] = {
        "id": roadmap_id,
        "title": "Founder Foundations",
        "description": "Core roadmap from idea to validation to early traction.",
        "modules": [
            {
                "id": "module-idea",
                "title": "Idea & Problem",
                "description": "Problem discovery and hypothesis building.",
                "lessons": [
                    {
                        "id": "lesson-problem-interviews",
                        "title": "Customer discovery interviews",
                        "description": "Learn how to run problem interviews.",
                        "estimated_minutes": 20,
                    }
                ],
            },
            {
                "id": "module-mvp",
                "title": "MVP & Validation",
                "description": "Build the smallest test and measure learning.",
                "lessons": [
                    {
                        "id": "lesson-mvp-scope",
                        "title": "Scoping an MVP",
                        "description": "Define MVP scope and success metrics.",
                        "estimated_minutes": 15,
                    }
                ],
            },
        ],
    }

    badges = [
        {
            "id": "badge-first-session",
            "name": "First Simulation",
            "description": "Completed your first simulation session.",
            "icon": "spark",
        },
        {
            "id": "badge-100-xp",
            "name": "XP 100",
            "description": "Earned 100 XP.",
            "icon": "bolt",
        },
    ]
    for b in badges:
        STORE.badges[b["id"]] = b


_seed_data()


#
# Auth / user models
#

PasswordStr = Annotated[
    str,
    StringConstraints(min_length=8, max_length=128, strip_whitespace=True),
]
DisplayNameStr = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, strip_whitespace=True),
]


class AuthRegisterRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address.")
    password: PasswordStr = Field(..., description="User password (min 8 chars).")
    display_name: DisplayNameStr = Field(..., description="Name shown in the app.")


class AuthLoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address.")
    password: PasswordStr = Field(..., description="User password.")


class AuthTokenResponse(BaseModel):
    access_token: str = Field(..., description="Bearer token for Authorization header.")
    token_type: Literal["bearer"] = Field("bearer", description="Token type.")
    user_id: str = Field(..., description="Authenticated user id.")


class UserProfile(BaseModel):
    id: str = Field(..., description="User id.")
    email: EmailStr = Field(..., description="User email.")
    display_name: str = Field(..., description="User display name.")
    created_at: datetime = Field(..., description="UTC timestamp of creation.")
    bio: Optional[str] = Field(default=None, description="Short founder bio.")
    goal: Optional[str] = Field(default=None, description="Primary learning goal.")
    locale: str = Field(default="en", description="IETF locale code.")
    xp: int = Field(default=0, ge=0, description="Total accumulated XP.")
    level: int = Field(default=1, ge=1, description="Computed user level.")


class UserProfileUpdate(BaseModel):
    display_name: Optional[DisplayNameStr] = Field(default=None, description="New display name.")
    bio: Optional[str] = Field(default=None, max_length=280, description="Short bio (<= 280 chars).")
    goal: Optional[str] = Field(default=None, max_length=280, description="Learning goal (<= 280 chars).")
    locale: Optional[str] = Field(default=None, description="IETF locale code.")


def _compute_level(xp: int) -> int:
    """Simple leveling curve: level increases every 100 XP."""
    return max(1, xp // 100 + 1)


def _hash_password(password: str) -> str:
    """
    Very light hashing placeholder.

    IMPORTANT: This is not production-grade. Replace with passlib/bcrypt/argon2
    when persistence/auth hardening is required.
    """
    return f"devhash:{password[::-1]}"


def _verify_password(password: str, password_hash: str) -> bool:
    return _hash_password(password) == password_hash


def _issue_token(user_id: str) -> str:
    token = f"fg_{uuid.uuid4().hex}"
    STORE.tokens[token] = user_id
    return token


def _require_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """
    Resolve Bearer token to user record.

    We intentionally keep auth very simple for frontend integration:
    Authorization: Bearer <access_token>
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    token = authorization.split(" ", 1)[1].strip()
    user_id = STORE.tokens.get(token)
    if not user_id or user_id not in STORE.users:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    return STORE.users[user_id]


#
# Curriculum / roadmap models
#


class CurriculumLesson(BaseModel):
    id: str = Field(..., description="Lesson id.")
    title: str = Field(..., description="Lesson title.")
    description: str = Field(..., description="Lesson description.")
    estimated_minutes: int = Field(..., ge=1, le=180, description="Estimated completion time.")


class CurriculumModule(BaseModel):
    id: str = Field(..., description="Module id.")
    title: str = Field(..., description="Module title.")
    description: str = Field(..., description="Module description.")
    lessons: List[CurriculumLesson] = Field(default_factory=list, description="Module lessons.")


class Roadmap(BaseModel):
    id: str = Field(..., description="Roadmap id.")
    title: str = Field(..., description="Roadmap title.")
    description: str = Field(..., description="Roadmap description.")
    modules: List[CurriculumModule] = Field(default_factory=list, description="Roadmap modules.")


#
# Sessions / turns models
#


class SessionType(str, Enum):
    simulation = "simulation"
    coaching = "coaching"


class TurnRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class SessionTurn(BaseModel):
    id: str = Field(..., description="Turn id.")
    created_at: datetime = Field(..., description="UTC timestamp when the turn was created.")
    role: TurnRole = Field(..., description="Role of the message.")
    content: str = Field(..., min_length=1, max_length=8000, description="Turn content.")


class Session(BaseModel):
    id: str = Field(..., description="Session id.")
    user_id: str = Field(..., description="Owner user id.")
    type: SessionType = Field(..., description="Session type.")
    title: str = Field(..., description="Short session title.")
    scenario: Optional[str] = Field(default=None, description="Scenario prompt/summary.")
    created_at: datetime = Field(..., description="UTC creation timestamp.")
    ended_at: Optional[datetime] = Field(default=None, description="UTC end timestamp.")
    turns: List[SessionTurn] = Field(default_factory=list, description="Conversation turns.")
    status: Literal["active", "ended"] = Field(default="active", description="Session status.")


class SessionCreateRequest(BaseModel):
    type: SessionType = Field(..., description="Session type.")
    title: str = Field(..., min_length=1, max_length=80, description="Session title.")
    scenario: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Scenario description used by the AI simulation.",
    )


class SessionAddTurnRequest(BaseModel):
    role: TurnRole = Field(..., description="Role of the turn.")
    content: str = Field(..., min_length=1, max_length=8000, description="Turn content.")


class SessionEndResponse(BaseModel):
    session: Session = Field(..., description="Ended session.")
    xp_awarded: int = Field(..., ge=0, description="XP awarded for ending this session.")
    badges_awarded: List[str] = Field(default_factory=list, description="Badge ids newly awarded.")


#
# Progress / gamification models
#


class LessonProgressStatus(str, Enum):
    not_started = "not_started"
    in_progress = "in_progress"
    completed = "completed"


class LessonProgress(BaseModel):
    lesson_id: str = Field(..., description="Lesson id.")
    status: LessonProgressStatus = Field(..., description="Progress status.")
    updated_at: datetime = Field(..., description="UTC last update time.")


class ProgressSnapshot(BaseModel):
    user_id: str = Field(..., description="User id.")
    roadmap_id: str = Field(..., description="Roadmap id.")
    lessons: List[LessonProgress] = Field(default_factory=list, description="Per-lesson progress.")
    updated_at: datetime = Field(..., description="UTC last update time.")


class ProgressUpdateRequest(BaseModel):
    roadmap_id: str = Field(..., description="Roadmap id.")
    lesson_id: str = Field(..., description="Lesson id.")
    status: LessonProgressStatus = Field(..., description="New status.")


class Badge(BaseModel):
    id: str = Field(..., description="Badge id.")
    name: str = Field(..., description="Badge name.")
    description: str = Field(..., description="Badge description.")
    icon: str = Field(..., description="Badge icon key for the UI.")


class AwardXpRequest(BaseModel):
    amount: int = Field(..., ge=1, le=1000, description="XP to award.")
    reason: Optional[str] = Field(default=None, max_length=200, description="Reason for audit/UI.")


class AwardXpResponse(BaseModel):
    user: UserProfile = Field(..., description="Updated user profile.")
    xp_awarded: int = Field(..., ge=0, description="XP awarded.")
    level_up: bool = Field(..., description="Whether the user leveled up.")
    new_badges: List[str] = Field(default_factory=list, description="Badge ids newly awarded.")


class LeaderboardEntry(BaseModel):
    user_id: str = Field(..., description="User id.")
    display_name: str = Field(..., description="Display name.")
    xp: int = Field(..., ge=0, description="Total XP.")
    level: int = Field(..., ge=1, description="Level.")


#
# Helper: awarding XP / badges
#


def _ensure_progress_doc(user_id: str) -> Dict[str, Any]:
    if user_id not in STORE.progress:
        # Default to the seeded roadmap
        roadmap_id = next(iter(STORE.curricula.keys()))
        STORE.progress[user_id] = {
            "user_id": user_id,
            "roadmap_id": roadmap_id,
            "lessons": {},  # lesson_id -> {status, updated_at}
            "updated_at": _utc_now(),
        }
    return STORE.progress[user_id]


def _award_badge_if_missing(user_id: str, badge_id: str) -> bool:
    owned = STORE.user_badges.setdefault(user_id, [])
    if badge_id in owned:
        return False
    if badge_id not in STORE.badges:
        return False
    owned.append(badge_id)
    return True


def _award_xp(user: Dict[str, Any], amount: int) -> Dict[str, Any]:
    user["xp"] = int(user.get("xp", 0)) + amount
    user["level"] = _compute_level(int(user["xp"]))
    return user


def _user_to_profile(user: Dict[str, Any]) -> UserProfile:
    return UserProfile(
        id=user["id"],
        email=user["email"],
        display_name=user["display_name"],
        created_at=user["created_at"],
        bio=user.get("bio"),
        goal=user.get("goal"),
        locale=user.get("locale", "en"),
        xp=int(user.get("xp", 0)),
        level=int(user.get("level", 1)),
    )


#
# Routes
#


@app.get(
    "/",
    tags=["System"],
    summary="Health check",
    description="Basic health check endpoint.",
    operation_id="health_check",
)
# PUBLIC_INTERFACE
def health_check():
    """Health check. Returns a simple payload indicating service availability."""
    return {"message": "Healthy", "service": "fouguide_backend", "ts": int(time.time())}


@app.get(
    "/docs/websocket",
    tags=["System"],
    summary="WebSocket usage (not implemented)",
    description=(
        "FouGuide's first iteration uses REST-only endpoints. "
        "This route exists to clarify that real-time WebSocket streaming is not yet implemented."
    ),
    operation_id="docs_websocket_usage",
)
# PUBLIC_INTERFACE
def docs_websocket_usage():
    """Documentation helper endpoint about WebSocket usage."""
    return {
        "websocket_supported": False,
        "note": "This backend currently exposes REST endpoints only.",
    }


#
# Auth
#


@app.post(
    "/auth/register",
    tags=["Auth"],
    summary="Register a new user",
    description="Create a new user account and return an access token.",
    response_model=AuthTokenResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="auth_register",
)
# PUBLIC_INTERFACE
def auth_register(payload: AuthRegisterRequest):
    """Register endpoint."""
    # uniqueness by email
    for u in STORE.users.values():
        if u["email"].lower() == payload.email.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user_id = str(uuid.uuid4())
    user = {
        "id": user_id,
        "email": payload.email,
        "password_hash": _hash_password(payload.password),
        "display_name": payload.display_name,
        "created_at": _utc_now(),
        "bio": None,
        "goal": None,
        "locale": "en",
        "xp": 0,
        "level": 1,
    }
    STORE.users[user_id] = user
    _ensure_progress_doc(user_id)

    token = _issue_token(user_id)
    return AuthTokenResponse(access_token=token, user_id=user_id)


@app.post(
    "/auth/login",
    tags=["Auth"],
    summary="Login",
    description="Validate credentials and return an access token.",
    response_model=AuthTokenResponse,
    operation_id="auth_login",
)
# PUBLIC_INTERFACE
def auth_login(payload: AuthLoginRequest):
    """Login endpoint."""
    user = next((u for u in STORE.users.values() if u["email"].lower() == payload.email.lower()), None)
    if not user or not _verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = _issue_token(user["id"])
    return AuthTokenResponse(access_token=token, user_id=user["id"])


@app.post(
    "/auth/logout",
    tags=["Auth"],
    summary="Logout",
    description="Invalidate the current access token.",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="auth_logout",
)
# PUBLIC_INTERFACE
def auth_logout(authorization: Optional[str] = Header(default=None)):
    """Logout endpoint. Removes the token from the in-memory store."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    token = authorization.split(" ", 1)[1].strip()
    STORE.tokens.pop(token, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


#
# Users
#


@app.get(
    "/users/me",
    tags=["Users"],
    summary="Get current user's profile",
    description="Returns the authenticated user's profile.",
    response_model=UserProfile,
    operation_id="users_me_get",
)
# PUBLIC_INTERFACE
def users_me_get(user: Dict[str, Any] = Depends(_require_user)):
    """Get current user's profile."""
    return _user_to_profile(user)


@app.patch(
    "/users/me",
    tags=["Users"],
    summary="Update current user's profile",
    description="Partially update the authenticated user's profile.",
    response_model=UserProfile,
    operation_id="users_me_patch",
)
# PUBLIC_INTERFACE
def users_me_patch(payload: UserProfileUpdate, user: Dict[str, Any] = Depends(_require_user)):
    """Update current user's profile."""
    if payload.display_name is not None:
        user["display_name"] = payload.display_name
    if payload.bio is not None:
        user["bio"] = payload.bio
    if payload.goal is not None:
        user["goal"] = payload.goal
    if payload.locale is not None:
        user["locale"] = payload.locale

    return _user_to_profile(user)


#
# Curriculum
#


@app.get(
    "/curriculum/roadmaps",
    tags=["Curriculum"],
    summary="List available roadmaps",
    description="Returns all roadmaps available to the user.",
    response_model=List[Roadmap],
    operation_id="curriculum_roadmaps_list",
)
# PUBLIC_INTERFACE
def curriculum_roadmaps_list():
    """List roadmaps."""
    return [Roadmap.model_validate(r) for r in STORE.curricula.values()]


@app.get(
    "/curriculum/roadmaps/{roadmap_id}",
    tags=["Curriculum"],
    summary="Get roadmap details",
    description="Returns a single roadmap by id.",
    response_model=Roadmap,
    operation_id="curriculum_roadmap_get",
)
# PUBLIC_INTERFACE
def curriculum_roadmap_get(roadmap_id: str):
    """Get roadmap by id."""
    roadmap = STORE.curricula.get(roadmap_id)
    if not roadmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
    return Roadmap.model_validate(roadmap)


#
# Sessions
#


@app.post(
    "/sessions",
    tags=["Sessions"],
    summary="Create a new session",
    description="Creates a new simulation/coaching session.",
    response_model=Session,
    status_code=status.HTTP_201_CREATED,
    operation_id="sessions_create",
)
# PUBLIC_INTERFACE
def sessions_create(payload: SessionCreateRequest, user: Dict[str, Any] = Depends(_require_user)):
    """Create a new session for the current user."""
    session_id = str(uuid.uuid4())
    sess = {
        "id": session_id,
        "user_id": user["id"],
        "type": payload.type,
        "title": payload.title,
        "scenario": payload.scenario,
        "created_at": _utc_now(),
        "ended_at": None,
        "turns": [],
        "status": "active",
    }
    STORE.sessions[session_id] = sess

    # Add initial system turn if scenario provided (helps frontend render).
    if payload.scenario:
        sess["turns"].append(
            {
                "id": str(uuid.uuid4()),
                "created_at": _utc_now(),
                "role": TurnRole.system,
                "content": f"Scenario: {payload.scenario}",
            }
        )

    return Session.model_validate(sess)


@app.get(
    "/sessions",
    tags=["Sessions"],
    summary="List sessions",
    description="List sessions for the authenticated user.",
    response_model=List[Session],
    operation_id="sessions_list",
)
# PUBLIC_INTERFACE
def sessions_list(user: Dict[str, Any] = Depends(_require_user)):
    """List sessions for current user."""
    sessions = [s for s in STORE.sessions.values() if s["user_id"] == user["id"]]
    sessions.sort(key=lambda s: s["created_at"], reverse=True)
    return [Session.model_validate(s) for s in sessions]


@app.get(
    "/sessions/{session_id}",
    tags=["Sessions"],
    summary="Get session",
    description="Get a specific session (must belong to the authenticated user).",
    response_model=Session,
    operation_id="sessions_get",
)
# PUBLIC_INTERFACE
def sessions_get(session_id: str, user: Dict[str, Any] = Depends(_require_user)):
    """Get session details."""
    sess = STORE.sessions.get(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    return Session.model_validate(sess)


@app.post(
    "/sessions/{session_id}/turns",
    tags=["Sessions"],
    summary="Add a conversational turn",
    description="Append a conversational turn to a session. The session must be active.",
    response_model=SessionTurn,
    operation_id="sessions_add_turn",
)
# PUBLIC_INTERFACE
def sessions_add_turn(
    session_id: str,
    payload: SessionAddTurnRequest,
    user: Dict[str, Any] = Depends(_require_user),
):
    """Add a turn to a session."""
    sess = STORE.sessions.get(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess["status"] != "active":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session has already ended")

    turn = {
        "id": str(uuid.uuid4()),
        "created_at": _utc_now(),
        "role": payload.role,
        "content": payload.content,
    }
    sess["turns"].append(turn)

    return SessionTurn.model_validate(turn)


@app.post(
    "/sessions/{session_id}/end",
    tags=["Sessions"],
    summary="End a session",
    description="Ends the session and awards XP + potential badges.",
    response_model=SessionEndResponse,
    operation_id="sessions_end",
)
# PUBLIC_INTERFACE
def sessions_end(session_id: str, user: Dict[str, Any] = Depends(_require_user)):
    """End a session and apply gamification rewards."""
    sess = STORE.sessions.get(session_id)
    if not sess or sess["user_id"] != user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    if sess["status"] != "active":
        # idempotent
        return SessionEndResponse(session=Session.model_validate(sess), xp_awarded=0, badges_awarded=[])

    sess["status"] = "ended"
    sess["ended_at"] = _utc_now()

    # Reward: 20 XP baseline, +1 XP per user turn (capped)
    user_turns = sum(1 for t in sess["turns"] if t["role"] == TurnRole.user)
    xp_awarded = min(50, 20 + user_turns)

    _award_xp(user, xp_awarded)
    new_badges: List[str] = []

    # Badge: first session completed
    user_sessions_ended = [
        s for s in STORE.sessions.values() if s["user_id"] == user["id"] and s["status"] == "ended"
    ]
    if len(user_sessions_ended) == 1:
        if _award_badge_if_missing(user["id"], "badge-first-session"):
            new_badges.append("badge-first-session")

    # Badge: XP 100
    if int(user["xp"]) >= 100:
        if _award_badge_if_missing(user["id"], "badge-100-xp"):
            new_badges.append("badge-100-xp")

    # Keep progress doc updated (touch updated_at) to reflect activity
    prog = _ensure_progress_doc(user["id"])
    prog["updated_at"] = _utc_now()

    return SessionEndResponse(
        session=Session.model_validate(sess),
        xp_awarded=xp_awarded,
        badges_awarded=new_badges,
    )


#
# Progress
#


@app.get(
    "/progress",
    tags=["Progress"],
    summary="Get progress snapshot",
    description="Returns progress snapshot for the authenticated user.",
    response_model=ProgressSnapshot,
    operation_id="progress_get",
)
# PUBLIC_INTERFACE
def progress_get(user: Dict[str, Any] = Depends(_require_user)):
    """Get current user's progress snapshot."""
    prog = _ensure_progress_doc(user["id"])
    lessons = []
    for lesson_id, lp in prog["lessons"].items():
        lessons.append(
            LessonProgress(
                lesson_id=lesson_id,
                status=lp["status"],
                updated_at=lp["updated_at"],
            )
        )
    return ProgressSnapshot(
        user_id=prog["user_id"],
        roadmap_id=prog["roadmap_id"],
        lessons=lessons,
        updated_at=prog["updated_at"],
    )


@app.post(
    "/progress",
    tags=["Progress"],
    summary="Update lesson progress",
    description="Update progress for a lesson; can be used for checklist completion in the UI.",
    response_model=ProgressSnapshot,
    operation_id="progress_update",
)
# PUBLIC_INTERFACE
def progress_update(payload: ProgressUpdateRequest, user: Dict[str, Any] = Depends(_require_user)):
    """Update the user's progress for a lesson."""
    roadmap = STORE.curricula.get(payload.roadmap_id)
    if not roadmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")

    # Validate lesson exists within roadmap.
    lesson_ids = {l["id"] for m in roadmap.get("modules", []) for l in m.get("lessons", [])}
    if payload.lesson_id not in lesson_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lesson not found in roadmap")

    prog = _ensure_progress_doc(user["id"])
    prog["roadmap_id"] = payload.roadmap_id
    prog["lessons"][payload.lesson_id] = {
        "status": payload.status,
        "updated_at": _utc_now(),
    }
    prog["updated_at"] = _utc_now()

    # Optional XP reward for completion transitions
    xp_awarded = 0
    if payload.status == LessonProgressStatus.completed:
        xp_awarded = 10
        _award_xp(user, xp_awarded)
        # Potential badge award checks happen via explicit gamification endpoints

    return progress_get(user=user)


#
# Gamification
#


@app.get(
    "/gamification/badges",
    tags=["Gamification"],
    summary="List badges",
    description="Returns the global badge catalog.",
    response_model=List[Badge],
    operation_id="gamification_badges_list",
)
# PUBLIC_INTERFACE
def gamification_badges_list():
    """List all available badges."""
    return [Badge.model_validate(b) for b in STORE.badges.values()]


@app.get(
    "/gamification/me/badges",
    tags=["Gamification"],
    summary="List my badges",
    description="Returns badges currently owned by the authenticated user.",
    response_model=List[Badge],
    operation_id="gamification_my_badges",
)
# PUBLIC_INTERFACE
def gamification_my_badges(user: Dict[str, Any] = Depends(_require_user)):
    """List user's earned badges."""
    owned_ids = STORE.user_badges.get(user["id"], [])
    return [Badge.model_validate(STORE.badges[b_id]) for b_id in owned_ids if b_id in STORE.badges]


@app.post(
    "/gamification/me/xp",
    tags=["Gamification"],
    summary="Award XP",
    description="Award XP to the authenticated user (for explicit actions).",
    response_model=AwardXpResponse,
    operation_id="gamification_award_xp",
)
# PUBLIC_INTERFACE
def gamification_award_xp(payload: AwardXpRequest, user: Dict[str, Any] = Depends(_require_user)):
    """Award XP to current user."""
    prior_level = int(user.get("level", 1))
    _award_xp(user, payload.amount)
    level_up = int(user.get("level", 1)) > prior_level

    new_badges: List[str] = []
    if int(user["xp"]) >= 100:
        if _award_badge_if_missing(user["id"], "badge-100-xp"):
            new_badges.append("badge-100-xp")

    return AwardXpResponse(
        user=_user_to_profile(user),
        xp_awarded=payload.amount,
        level_up=level_up,
        new_badges=new_badges,
    )


@app.get(
    "/gamification/leaderboard",
    tags=["Gamification"],
    summary="Leaderboard",
    description="Simple global XP leaderboard.",
    response_model=List[LeaderboardEntry],
    operation_id="gamification_leaderboard",
)
# PUBLIC_INTERFACE
def gamification_leaderboard(limit: int = 20):
    """Get leaderboard."""
    limit = max(1, min(100, int(limit)))
    users = list(STORE.users.values())
    users.sort(key=lambda u: int(u.get("xp", 0)), reverse=True)
    return [
        LeaderboardEntry(
            user_id=u["id"],
            display_name=u["display_name"],
            xp=int(u.get("xp", 0)),
            level=int(u.get("level", 1)),
        )
        for u in users[:limit]
    ]


#
# Config diagnostics (optional)
#


@app.get(
    "/system/config",
    tags=["System"],
    summary="Runtime config (sanitized)",
    description="Returns a sanitized view of runtime configuration flags for debugging.",
    operation_id="system_config_get",
)
# PUBLIC_INTERFACE
def system_config_get():
    """Return relevant env flags (sanitized)."""
    return {
        "EXPO_PUBLIC_PORT": os.getenv("EXPO_PUBLIC_PORT"),
        "EXPO_PUBLIC_TRUST_PROXY": os.getenv("EXPO_PUBLIC_TRUST_PROXY"),
        "EXPO_PUBLIC_LOG_LEVEL": os.getenv("EXPO_PUBLIC_LOG_LEVEL"),
        "EXPO_PUBLIC_HEALTHCHECK_PATH": os.getenv("EXPO_PUBLIC_HEALTHCHECK_PATH"),
        "EXPO_PUBLIC_FEATURE_FLAGS": os.getenv("EXPO_PUBLIC_FEATURE_FLAGS"),
        "EXPO_PUBLIC_EXPERIMENTS_ENABLED": os.getenv("EXPO_PUBLIC_EXPERIMENTS_ENABLED"),
    }
