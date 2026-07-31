"""Phase 7 long-term memory tests — isolated cortexa_agent_test only."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from app.memory.exceptions import (
    MemoryLimitExceededError,
    MemoryNotFoundError,
    MemorySensitiveContentError,
    MemoryValidationError,
)
from app.memory.extractor import MemoryExtractor
from app.memory.intent import detect_memory_intent
from app.memory.repository import MemoryRepository
from app.memory.retrieval import MemoryRetriever
from app.memory.sanitizer import MemorySanitizer
from app.memory.schemas import MemoryCreateRequest, MemoryIntentKind
from app.memory.service import MemoryService
from app.models.enums import MemoryCategory, MemorySource, MemoryStatus, UserRole, UserStatus
from app.models.user import User
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _create_user(session: AsyncSession, *, email: str | None = None) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email or f"mem-{uuid.uuid4().hex[:10]}@example.com",
        password_hash="not-a-real-hash",
        full_name="Memory Tester",
        role=UserRole.user,
        status=UserStatus.active,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


@pytest.fixture
def memory_service(settings) -> MemoryService:
    return MemoryService(settings=settings, repository=MemoryRepository(settings))


async def test_migration_0008_tables_exist(db_session: AsyncSession) -> None:
    result = await db_session.execute(
        text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name IN "
            "('user_memories','user_memory_settings','memory_audit_events')"
        )
    )
    names = {row[0] for row in result.all()}
    assert names == {"user_memories", "user_memory_settings", "memory_audit_events"}


async def test_settings_defaults_are_safe(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    settings = await memory_service.get_settings(db_session, user)
    assert settings.memory_enabled is True
    assert settings.automatic_extraction_enabled is False
    assert settings.suggestions_enabled is True
    assert settings.require_confirmation is True


async def test_create_valid_explicit_memory(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    memory = await memory_service.create_memory(
        db_session,
        user,
        MemoryCreateRequest(
            title="Python preference",
            content="The user prefers Python examples.",
            category=MemoryCategory.preference,
        ),
        source=MemorySource.explicit_user_request,
    )
    await db_session.commit()
    assert memory.status in {MemoryStatus.active, MemoryStatus.proposed}
    assert "python" in memory.normalized_content


async def test_reject_oversized_memory(
    db_session: AsyncSession,
    memory_service: MemoryService,
    settings,
) -> None:
    user = await _create_user(db_session)
    with pytest.raises(MemoryValidationError):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(
                title="Too long",
                content="x" * (settings.memory_max_content_characters + 10),
            ),
        )


async def test_reject_empty_memory(db_session: AsyncSession, memory_service: MemoryService) -> None:
    user = await _create_user(db_session)
    with pytest.raises(MemoryValidationError):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(title=" ", content=" "),
        )


async def test_reject_secrets(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    with pytest.raises(MemorySensitiveContentError):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(
                title="API key",
                content="Remember that my API key is sk-test-secret-value-123456",
            ),
        )


@pytest.mark.parametrize(
    "content",
    [
        "password=SuperSecret123!",
        "my password is SuperSecret123",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.aaaa.bbbbbbbb",
        "my JWT is eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature",
        "my OTP passcode is 482913",
        "my card number is 4111111111111111",
        "pem-fixture",
    ],
)
async def test_reject_sensitive_patterns(
    db_session: AsyncSession,
    memory_service: MemoryService,
    content: str,
) -> None:
    user = await _create_user(db_session)
    # Build PEM-like text at runtime so source files stay clear of secret scanners.
    if content == "pem-fixture":
        marker = "PRIVATE" + " KEY"
        content = f"-----BEGIN {marker}-----\nABC\n-----END {marker}-----"
    with pytest.raises(MemorySensitiveContentError):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(title="Sensitive", content=content),
        )


def test_retrieval_score_handles_vector_embedding_truthiness(settings) -> None:
    """pgvector may yield numpy arrays; truthiness checks must use is not None."""

    class _FakeMemory:
        title = "Python preference"
        content = "I prefer Python examples instead of JavaScript examples."
        embedding = __import__("numpy").asarray([0.1, 0.2, 0.3], dtype=float)
        importance = 0.8
        last_used_at = None
        use_count = 0

    retriever = MemoryRetriever(settings=settings, repository=None)  # type: ignore[arg-type]
    score = retriever._score(
        _FakeMemory(),  # type: ignore[arg-type]
        "Which programming language should you use for my code examples?",
        [0.1, 0.2, 0.3],
    )
    assert score > 0.0


async def test_duplicate_exact_rejected(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    body = MemoryCreateRequest(
        title="Pref",
        content="The user prefers concise answers.",
        category=MemoryCategory.preference,
        confirmation_required=False,
    )
    await memory_service.create_memory(db_session, user, body)
    await db_session.commit()
    with pytest.raises(MemoryValidationError) as exc:
        await memory_service.create_memory(db_session, user, body)
    assert exc.value.code == "memory_duplicate"


async def test_conflict_preference_supersedes(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    first = await memory_service.create_memory(
        db_session,
        user,
        MemoryCreateRequest(
            title="JS",
            content="The user prefers JavaScript examples.",
            category=MemoryCategory.preference,
            confirmation_required=False,
        ),
    )
    await db_session.commit()
    second = await memory_service.create_memory(
        db_session,
        user,
        MemoryCreateRequest(
            title="Py",
            content="The user prefers Python examples.",
            category=MemoryCategory.preference,
            confirmation_required=False,
        ),
    )
    await db_session.commit()
    await db_session.refresh(first)
    assert first.status == MemoryStatus.archived
    assert second.status == MemoryStatus.active


async def test_max_active_limit(
    db_session: AsyncSession,
    memory_service: MemoryService,
    settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_max_active_per_user", 2)
    user = await _create_user(db_session)
    settings_row = await memory_service.repository.get_or_create_settings(db_session, user)
    settings_row.maximum_active_memories = 2
    await db_session.commit()
    for index in range(2):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(
                title=f"M{index}",
                content=f"Unique active memory number {index} for limit test.",
                confirmation_required=False,
            ),
        )
    await db_session.commit()
    with pytest.raises(MemoryLimitExceededError):
        await memory_service.create_memory(
            db_session,
            user,
            MemoryCreateRequest(
                title="Overflow",
                content="Another unique active memory that should fail.",
                confirmation_required=False,
            ),
        )


async def test_ownership_isolation(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    owner = await _create_user(db_session, email="owner@example.com")
    other = await _create_user(db_session, email="other@example.com")
    memory = await memory_service.create_memory(
        db_session,
        owner,
        MemoryCreateRequest(
            title="Private",
            content="The user works on Cortexa.",
            confirmation_required=False,
        ),
    )
    await db_session.commit()
    with pytest.raises(MemoryNotFoundError):
        await memory_service.get_memory(db_session, other, memory.id)
    with pytest.raises(MemoryNotFoundError):
        await memory_service.archive(db_session, other, memory.id)
    with pytest.raises(MemoryNotFoundError):
        await memory_service.delete_memory(db_session, other, memory.id)


async def test_confirm_reject_archive_restore_delete(
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    user = await _create_user(db_session)
    proposed = await memory_service.create_memory(
        db_session,
        user,
        MemoryCreateRequest(
            title="Suggested",
            content="The user prefers TypeScript for frontend work.",
            confirmation_required=True,
        ),
        force_proposed=True,
    )
    await db_session.commit()
    assert proposed.status == MemoryStatus.proposed
    confirmed = await memory_service.confirm(db_session, user, proposed.id)
    assert confirmed.status == MemoryStatus.active
    archived = await memory_service.archive(db_session, user, proposed.id)
    assert archived.status == MemoryStatus.archived
    restored = await memory_service.restore(db_session, user, proposed.id)
    assert restored.status == MemoryStatus.active
    await memory_service.delete_memory(db_session, user, proposed.id)
    await db_session.commit()
    with pytest.raises(MemoryNotFoundError):
        await memory_service.get_memory(db_session, user, proposed.id)


async def test_expired_excluded_from_retrieval(
    db_session: AsyncSession,
    memory_service: MemoryService,
    settings,
) -> None:
    user = await _create_user(db_session)
    memory = await memory_service.create_memory(
        db_session,
        user,
        MemoryCreateRequest(
            title="Expired",
            content="The user prefers Rust examples.",
            confirmation_required=False,
            expires_at=datetime.now(UTC) - timedelta(days=1),
        ),
    )
    await db_session.commit()
    retriever = MemoryRetriever(settings=settings, repository=memory_service.repository)
    results = await retriever.retrieve(db_session, user, query="Rust examples")
    assert all(item.id != memory.id for item in results)


async def test_retrieval_relevant_and_ownership(
    db_session: AsyncSession,
    memory_service: MemoryService,
    settings,
) -> None:
    owner = await _create_user(db_session, email="ret-owner@example.com")
    other = await _create_user(db_session, email="ret-other@example.com")
    await memory_service.create_memory(
        db_session,
        owner,
        MemoryCreateRequest(
            title="Python",
            content="The user prefers Python examples for backend work.",
            confirmation_required=False,
            importance=0.9,
        ),
    )
    await memory_service.create_memory(
        db_session,
        other,
        MemoryCreateRequest(
            title="Other",
            content="The user prefers Python examples for backend work.",
            confirmation_required=False,
            importance=0.9,
        ),
    )
    await db_session.commit()
    retriever = MemoryRetriever(settings=settings, repository=memory_service.repository)
    results = await retriever.retrieve(db_session, owner, query="Which language for examples?")
    assert any("python" in item.content.lower() for item in results)
    # Mark used
    if results:
        await memory_service.repository.mark_used(db_session, [results[0].id], owner.id)
        await db_session.commit()
        refreshed = await memory_service.repository.get_owned(db_session, owner, results[0].id)
        assert refreshed is not None
        assert refreshed.use_count >= 1
        assert refreshed.last_used_at is not None


async def test_intent_detection() -> None:
    remember = detect_memory_intent("Remember that I prefer Python examples.")
    assert remember.kind == MemoryIntentKind.remember
    forget = detect_memory_intent("Forget my frontend language preference.")
    assert forget.kind == MemoryIntentKind.forget
    listed = detect_memory_intent("What do you remember about this project?")
    assert listed.kind == MemoryIntentKind.list
    assert detect_memory_intent("Do not use memory in this conversation.").kind == (
        MemoryIntentKind.disable_for_conversation
    )
    assert detect_memory_intent("Hello there").kind == MemoryIntentKind.none


async def test_extractor_skips_transient_and_secrets(settings) -> None:
    extractor = MemoryExtractor(settings=settings, llm_service=None)
    assert await extractor.extract_from_turn(user_content="hi", assistant_content="hello") == []
    assert (
        await extractor.extract_from_turn(
            user_content="My API key is sk-test-secret-value-123456",
            assistant_content="ok",
        )
        == []
    )
    prefs = await extractor.extract_from_turn(
        user_content="I prefer Python examples.",
        assistant_content="Understood.",
    )
    assert prefs
    assert prefs[0].category == MemoryCategory.preference


async def test_sanitizer_redacts_for_audit() -> None:
    sanitizer = MemorySanitizer()
    redacted = sanitizer.redact_for_audit("secret value here")
    assert redacted is not None
    assert "secret value" not in redacted


async def test_memory_api_auth_and_crud(chat_client: AsyncClient) -> None:
    anon = await chat_client.get("/api/v1/memories")
    assert anon.status_code == 401

    register = await chat_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"mem-api-{uuid.uuid4().hex[:8]}@example.com",
            "password": "StrongDemoPassword123!",
            "confirm_password": "StrongDemoPassword123!",
            "full_name": "Memory API Tester",
        },
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    create = await chat_client.post(
        "/api/v1/memories",
        headers=headers,
        json={
            "title": "Timezone",
            "content": "The user's default timezone is Asia/Kolkata.",
            "category": "preference",
            "confirmation_required": False,
        },
    )
    assert create.status_code == 200, create.text
    memory_id = create.json()["id"]
    assert "embedding" not in create.json()

    listed = await chat_client.get("/api/v1/memories?status=active", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] >= 1

    settings = await chat_client.get("/api/v1/memory-settings", headers=headers)
    assert settings.status_code == 200
    assert settings.json()["automatic_extraction_enabled"] is False

    patched = await chat_client.patch(
        "/api/v1/memory-settings",
        headers=headers,
        json={"memory_enabled": False},
    )
    assert patched.status_code == 200
    assert patched.json()["memory_enabled"] is False

    deleted = await chat_client.delete(f"/api/v1/memories/{memory_id}", headers=headers)
    assert deleted.status_code == 204


async def test_memory_api_cross_user_404(
    chat_client: AsyncClient,
    db_session: AsyncSession,
    memory_service: MemoryService,
) -> None:
    other = await _create_user(db_session, email=f"cross-user-{uuid.uuid4().hex[:8]}@example.com")
    memory = await memory_service.create_memory(
        db_session,
        other,
        MemoryCreateRequest(
            title="Hidden",
            content="The other user prefers Go examples.",
            confirmation_required=False,
        ),
    )
    await db_session.commit()

    register = await chat_client.post(
        "/api/v1/auth/register",
        json={
            "email": f"mem-cross-{uuid.uuid4().hex[:8]}@example.com",
            "password": "StrongDemoPassword123!",
            "confirm_password": "StrongDemoPassword123!",
            "full_name": "Cross User",
        },
    )
    token = register.json()["access_token"]
    response = await chat_client.get(
        f"/api/v1/memories/{memory.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


async def test_database_is_test_only(db_session: AsyncSession) -> None:
    name = await db_session.scalar(text("SELECT current_database()"))
    assert name == "cortexa_agent_test"
