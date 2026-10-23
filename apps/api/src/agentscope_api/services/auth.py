from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from agentscope_api.core.config import Settings
from agentscope_api.core.database_errors import is_unique_violation
from agentscope_api.core.exceptions import AuthenticationError, ConflictError
from agentscope_api.core.security import (
    create_access_token,
    generate_opaque_token,
    hash_password,
    keyed_hash,
    verify_password,
)
from agentscope_api.models import RefreshToken, User
from agentscope_api.models.base import utc_now
from agentscope_api.repositories.auth import AuthRepository
from agentscope_api.schemas.auth import LoginRequest, RegisterRequest


class AuthTokens:
    def __init__(self, access_token: str, access_expires_at: datetime, refresh_token: str) -> None:
        self.access_token = access_token
        self.access_expires_at = access_expires_at
        self.refresh_token = refresh_token


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings
        self.repository = AuthRepository(session)

    async def register(self, request: RegisterRequest) -> tuple[User, AuthTokens]:
        email = request.email.lower()
        try:
            async with self.session.begin():
                if await self.repository.get_user_by_email(email):
                    raise ConflictError("An account with this email already exists")
                user = User(
                    email=email,
                    password_hash=hash_password(request.password),
                    display_name=request.display_name.strip(),
                    is_active=True,
                )
                self.repository.add_user(user)
                await self.session.flush()
                tokens, _ = await self._issue_tokens(user.id, family_id=uuid4())
        except IntegrityError as error:
            await self.session.rollback()
            if not is_unique_violation(error):
                raise
            raise ConflictError("An account with this email already exists") from error
        return user, tokens

    async def login(self, request: LoginRequest) -> tuple[User, AuthTokens]:
        async with self.session.begin():
            user = await self.repository.get_user_by_email(request.email.lower())
            if user is None or not verify_password(request.password, user.password_hash):
                raise AuthenticationError("Invalid email or password")
            if not user.is_active:
                raise AuthenticationError("Account is disabled")
            tokens, _ = await self._issue_tokens(user.id, family_id=uuid4())
        return user, tokens

    async def refresh(self, raw_token: str) -> tuple[User, AuthTokens]:
        token_hash = keyed_hash(raw_token, self.settings.token_hash_secret)
        invalid_message: str | None = None
        result: tuple[User, AuthTokens] | None = None
        async with self.session.begin():
            current = await self.repository.get_refresh_token_for_update(token_hash)
            if current is None:
                raise AuthenticationError("Invalid refresh token")
            now = utc_now()
            if current.revoked_at is not None:
                await self.repository.revoke_family(current.family_id)
                invalid_message = "Refresh token reuse detected"
            expires_at = current.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=now.tzinfo)
            if invalid_message is None and expires_at <= now:
                current.revoked_at = now
                invalid_message = "Refresh token expired"
            if invalid_message is None:
                user = await self.repository.get_user(current.user_id)
                if user is None or not user.is_active:
                    invalid_message = "Authentication required"
                else:
                    current.revoked_at = now
                    tokens, replacement_id = await self._issue_tokens(
                        user.id,
                        family_id=current.family_id,
                        parent_token_id=current.id,
                    )
                    current.replaced_by_id = replacement_id
                    result = (user, tokens)
        if invalid_message is not None or result is None:
            raise AuthenticationError(invalid_message or "Authentication required")
        return result

    async def logout(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        token_hash = keyed_hash(raw_token, self.settings.token_hash_secret)
        async with self.session.begin():
            token = await self.repository.get_refresh_token_for_update(token_hash)
            if token and token.revoked_at is None:
                token.revoked_at = utc_now()

    async def _issue_tokens(
        self,
        user_id: UUID,
        *,
        family_id: UUID,
        parent_token_id: UUID | None = None,
    ) -> tuple[AuthTokens, UUID]:
        raw_refresh = generate_opaque_token()
        now = utc_now()
        refresh = RefreshToken(
            user_id=user_id,
            family_id=family_id,
            parent_token_id=parent_token_id,
            token_hash=keyed_hash(raw_refresh, self.settings.token_hash_secret),
            created_at=now,
            expires_at=now + timedelta(days=self.settings.refresh_token_days),
            revoked_at=None,
            replaced_by_id=None,
        )
        self.repository.add_refresh_token(refresh)
        await self.session.flush()
        access, expires_at = create_access_token(user_id, self.settings)
        tokens = AuthTokens(access, expires_at, raw_refresh)
        return tokens, refresh.id
