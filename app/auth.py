import bcrypt
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.models import User

SESSION_USER_KEY = "user_id"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain_password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(plain_password.encode(), password_hash.encode())


def login_user(request: Request, user: User) -> None:
    request.session[SESSION_USER_KEY] = user.id


def logout_user(request: Request) -> None:
    request.session.pop(SESSION_USER_KEY, None)


def get_current_user(request: Request, db: Session) -> User | None:
    user_id = request.session.get(SESSION_USER_KEY)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user is None:
        raise PermissionError("Not authenticated")
    return user
