from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from app.core.config import get_settings
from app.core.auth import authenticate, require_login
from app.api import all_routers
import os

settings = get_settings()

app = FastAPI(title=settings.app_name, docs_url="/api/docs")

# Session middleware — required for login state
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key)

# Static files and templates
app.mount("/static", StaticFiles(directory="app/frontend/static"), name="static")
templates = Jinja2Templates(directory="app/frontend/templates")

# Register all API routers
for router in all_routers:
    app.include_router(router)


# --- AUTH ROUTES ---

@app.get("/login")
def login_page(request: Request):
    if request.session.get("user"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("auth/login.html", {"request": request})


@app.post("/login")
async def login(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    if authenticate(username, password):
        request.session["user"] = username
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        "auth/login.html",
        {"request": request, "error": "Invalid credentials"},
        status_code=401
    )


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


# --- PAGE ROUTES ---

@app.get("/")
def index(request: Request, user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("dashboard/index.html", {"request": request, "user": user})


@app.get("/config/brands")
def config_brands(request: Request, user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("config/brands.html", {"request": request, "user": user})


@app.get("/config/products")
def config_products(request: Request, user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("config/products.html", {"request": request, "user": user})


@app.get("/config/keywords")
def config_keywords(request: Request, user=Depends(require_login)):
    if isinstance(user, RedirectResponse):
        return user
    return templates.TemplateResponse("config/keywords.html", {"request": request, "user": user})
