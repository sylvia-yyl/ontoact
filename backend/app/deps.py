from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.user import User
from app.services.workspace_user import workspace_user

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(db: Session = Depends(get_db)) -> User:
    """OntoAct has no sign-in: every request acts as the built-in workspace user.

    It is still a real row, so ``created_by``, audit events and object policies
    work unchanged.
    """
    return workspace_user(db)

def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return current_user

def require_editor(current_user: User = Depends(get_current_user)) -> User:
    """Write access: admin or editor role."""
    if current_user.role not in ("admin", "editor"):
        raise HTTPException(status_code=403, detail="Editor role required")
    return current_user
