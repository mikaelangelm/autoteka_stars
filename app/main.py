import os
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from app import crud
from app.auth import get_current_user, login_user, logout_user
from app.crud import CrudError
from app.database import get_db, init_db
from app.models import User

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-in-production")

app = FastAPI(title="Автотека Stars")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)


@app.on_event("startup")
def on_startup() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _redirect_login() -> RedirectResponse:
    return RedirectResponse(url="/login", status_code=303)


@app.get("/register", response_class=HTMLResponse)
def register_form(request: Request):
    return templates.TemplateResponse(
        request, "register.html", {"user": None, "error": None, "message": None}
    )


@app.post("/register")
def register(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user = crud.create_user(db, email=email.strip().lower(), password=password)
    except CrudError as exc:
        return templates.TemplateResponse(
            request,
            "register.html",
            {"user": None, "error": str(exc), "message": None, "email": email},
            status_code=400,
        )
    login_user(request, user)
    return RedirectResponse(url="/", status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse(
        request, "login.html", {"user": None, "error": None, "message": None}
    )


@app.post("/login")
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = crud.authenticate_user(db, email=email.strip().lower(), password=password)
    if user is None:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"user": None, "error": "Неверный email или пароль", "message": None, "email": email},
            status_code=400,
        )
    login_user(request, user)
    return RedirectResponse(url="/", status_code=303)


@app.post("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return _redirect_login()
    reports = crud.list_reports(db, user)
    message = request.query_params.get("message")
    error = request.query_params.get("error")
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user, "reports": reports, "error": error, "message": message},
    )


@app.post("/reports/publish")
def publish_report(
    request: Request,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if user is None:
        return _redirect_login()
    try:
        crud.publish_report(db, user, title, file)
    except CrudError as exc:
        reports = crud.list_reports(db, user)
        return templates.TemplateResponse(
            request,
            "dashboard.html",
            {"user": user, "reports": reports, "error": str(exc), "message": None},
            status_code=400,
        )
    return RedirectResponse(url="/?message=Отчёт опубликован! +100 ⭐", status_code=303)


@app.get("/reports/{report_id}", response_class=HTMLResponse)
def report_detail(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return _redirect_login()
    report = crud.get_report(db, report_id)
    if report is None:
        return RedirectResponse(url="/?error=Отчёт не найден", status_code=303)
    owner = db.get(User, report.owner_id)
    reports = crud.list_reports(db, user)
    info = next((r for r in reports if r["id"] == report_id), None)
    return templates.TemplateResponse(
        request,
        "report_detail.html",
        {
            "user": user,
            "report": report,
            "owner_email": owner.email if owner else "?",
            "is_own": info["is_own"] if info else False,
            "already_downloaded": info["already_downloaded"] if info else False,
            "error": None,
            "message": None,
        },
    )


@app.get("/reports/{report_id}/download")
def download_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user is None:
        return _redirect_login()
    try:
        report, file_path = crud.prepare_download(db, user, report_id)
    except CrudError as exc:
        return RedirectResponse(url=f"/?error={exc}", status_code=303)
    return FileResponse(
        path=file_path,
        filename=f"{report.title}.pdf",
        media_type="application/pdf",
    )
