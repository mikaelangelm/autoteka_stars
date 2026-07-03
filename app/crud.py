import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password, verify_password
from app.models import Download, Report, User

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"

PUBLISH_REWARD = 100
DOWNLOAD_COST = 10


class CrudError(Exception):
    pass


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def create_user(db: Session, email: str, password: str) -> User:
    if get_user_by_email(db, email):
        raise CrudError("Пользователь с таким email уже существует")
    user = User(email=email, password_hash=hash_password(password), stars=0)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User | None:
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        return None
    return user


def list_reports(db: Session, current_user: User | None = None) -> list[dict]:
    reports = db.scalars(select(Report).order_by(Report.created_at.desc())).all()
    downloaded_ids: set[int] = set()
    if current_user:
        downloaded_ids = set(
            db.scalars(
                select(Download.report_id).where(Download.user_id == current_user.id)
            ).all()
        )

    result = []
    for report in reports:
        owner = db.get(User, report.owner_id)
        result.append(
            {
                "id": report.id,
                "title": report.title,
                "owner_id": report.owner_id,
                "owner_email": owner.email if owner else "?",
                "created_at": report.created_at,
                "already_downloaded": report.id in downloaded_ids,
                "is_own": current_user is not None and report.owner_id == current_user.id,
            }
        )
    return result


def get_report(db: Session, report_id: int) -> Report | None:
    return db.get(Report, report_id)


def publish_report(db: Session, user: User, title: str, file: UploadFile) -> Report:
    if not title.strip():
        raise CrudError("Укажите название отчёта")

    content = file.file.read()
    if not content:
        raise CrudError("Файл пустой")

    if not content.startswith(b"%PDF"):
        raise CrudError("Отчёт должен быть PDF-файлом")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}.pdf"
    file_path = UPLOAD_DIR / stored_name
    file_path.write_bytes(content)

    report = Report(title=title.strip(), filename=stored_name, owner_id=user.id)
    user.stars += PUBLISH_REWARD
    db.add(report)
    db.commit()
    db.refresh(report)
    db.refresh(user)
    return report


def prepare_download(db: Session, user: User, report_id: int) -> tuple[Report, Path]:
    report = get_report(db, report_id)
    if report is None:
        raise CrudError("Отчёт не найден")

    if report.owner_id == user.id:
        file_path = UPLOAD_DIR / report.filename
        if not file_path.exists():
            raise CrudError("Файл отчёта не найден на диске")
        return report, file_path

    existing = db.scalar(
        select(Download).where(
            Download.user_id == user.id,
            Download.report_id == report_id,
        )
    )
    if existing:
        file_path = UPLOAD_DIR / report.filename
        if not file_path.exists():
            raise CrudError("Файл отчёта не найден на диске")
        return report, file_path

    if user.stars < DOWNLOAD_COST:
        raise CrudError(f"Нужно {DOWNLOAD_COST} звёздочек для скачивания")

    user.stars -= DOWNLOAD_COST
    db.add(Download(user_id=user.id, report_id=report.id))
    db.commit()
    db.refresh(user)

    file_path = UPLOAD_DIR / report.filename
    if not file_path.exists():
        raise CrudError("Файл отчёта не найден на диске")
    return report, file_path
