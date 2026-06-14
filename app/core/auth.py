import os
from fastapi import Request, HTTPException, status
from fastapi.responses import RedirectResponse

# Single-user auth for demo — credentials from environment
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "changeme")


def authenticate(username: str, password: str) -> bool:
    return username == ADMIN_USERNAME and password == ADMIN_PASSWORD


def get_current_user(request: Request):
    """Dependency — returns username if logged in, raises 401 otherwise."""
    user = request.session.get("user")
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
    return user


def require_login(request: Request):
    """Dependency for page routes — redirects to /login if not authenticated."""
    user = request.session.get("user")
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    return user
