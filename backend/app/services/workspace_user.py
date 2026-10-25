"""The single built-in user every request acts as (OntoAct has no sign-in)."""
from sqlalchemy.orm import Session

from app.config import settings
from app.models.user import User


def ensure_workspace_user(db: Session) -> User:
    user = db.query(User).filter_by(username=settings.workspace_user).first()
    if user is None:
        user = User(username=settings.workspace_user, email=f"{settings.workspace_user}@ontoact.local", role="admin")
        db.add(user)
        db.commit()
    return user


def workspace_user(db: Session) -> User:
    return db.query(User).filter_by(username=settings.workspace_user).first() or ensure_workspace_user(db)
