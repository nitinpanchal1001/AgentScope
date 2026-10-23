from fastapi import APIRouter, Request, Response, status

from agentscope_api.api.dependencies import CurrentUser, SessionDependency, SettingsDependency
from agentscope_api.core.exceptions import AuthenticationError
from agentscope_api.schemas.auth import AuthResponse, LoginRequest, RegisterRequest, UserResponse
from agentscope_api.services.auth import AuthService, AuthTokens

router = APIRouter(prefix="/auth", tags=["Authentication"])


def set_refresh_cookie(
    response: Response, tokens: AuthTokens, settings: SettingsDependency
) -> None:
    response.set_cookie(
        settings.refresh_cookie_name,
        tokens.refresh_token,
        max_age=settings.refresh_token_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.refresh_cookie_secure,
        samesite="lax",
        path="/api/v1/auth",
    )


def auth_response(user: UserResponse, tokens: AuthTokens) -> AuthResponse:
    return AuthResponse(
        access_token=tokens.access_token,
        expires_at=tokens.access_expires_at,
        user=user,
    )


@router.post("/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    user, tokens = await AuthService(session, settings).register(payload)
    set_refresh_cookie(response, tokens, settings)
    return auth_response(UserResponse.model_validate(user), tokens)


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    user, tokens = await AuthService(session, settings).login(payload)
    set_refresh_cookie(response, tokens, settings)
    return auth_response(UserResponse.model_validate(user), tokens)


@router.post("/refresh", response_model=AuthResponse)
async def refresh(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> AuthResponse:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    if refresh_token is None:
        raise AuthenticationError("Refresh token missing")
    user, tokens = await AuthService(session, settings).refresh(refresh_token)
    set_refresh_cookie(response, tokens, settings)
    return auth_response(UserResponse.model_validate(user), tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
    session: SessionDependency,
    settings: SettingsDependency,
) -> None:
    refresh_token = request.cookies.get(settings.refresh_cookie_name)
    await AuthService(session, settings).logout(refresh_token)
    response.delete_cookie(settings.refresh_cookie_name, path="/api/v1/auth")


@router.get("/me", response_model=UserResponse)
async def me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)
