"""Request dependencies: database session, the signed-in user, roles and client separation."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select

from .db import utcnow
from .models import AuthSession, Client, ClientAccess, User
from .security import token_digest

NOT_FOUND = "Not found."


def get_db(request: Request):
    db = request.app.state.Session()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db=Depends(get_db)) -> User:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(401, "Sign in first.", headers={"WWW-Authenticate": "Bearer"})
    session = db.execute(select(AuthSession).where(AuthSession.token_hash == token_digest(token.strip()))
                         ).scalar_one_or_none()
    if session is None or session.revoked or session.expires_at <= utcnow():
        raise HTTPException(401, "Your session has ended. Sign in again.", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, session.user_id)
    if user is None or not user.active:
        raise HTTPException(401, "This account is disabled.")
    request.state.auth_session = session
    return user


def require_role(user, *roles):
    if user.role not in roles:
        raise HTTPException(403, "Your role does not allow this action.")


def can_access(db, user, client_id):
    if user.role == "admin":
        return True
    return db.execute(select(ClientAccess.id).where(ClientAccess.user_id == user.id,
                                                    ClientAccess.client_id == client_id)).first() is not None


def accessible_client_ids(db, user):
    if user.role == "admin":
        return list(db.execute(select(Client.id)).scalars())
    return list(db.execute(select(ClientAccess.client_id).where(ClientAccess.user_id == user.id)).scalars())


def client_or_404(db, user, client_id):
    """Users never learn whether another client's records exist: no access looks the same as not found."""
    client = db.get(Client, client_id)
    if client is None or not can_access(db, user, client.id):
        raise HTTPException(404, NOT_FOUND)
    return client


def owned_or_404(db, user, model, entity_id):
    """Load a client-owned row and check the user's access to its client."""
    row = db.get(model, entity_id)
    if row is None or not can_access(db, user, row.client_id):
        raise HTTPException(404, NOT_FOUND)
    return row
