from typing import Optional, Callable
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models.user import User
from app.services.auth_service import get_secret_key


security_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = credentials.credentials
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
        user_id = int(payload.get("sub", "0"))
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(*allowed_roles: str) -> Callable[[User], User]:
    async def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Returns None if no/invalid credentials instead of raising.
    Useful for routes that allow public access for bootstrap logic.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None
    token = credentials.credentials
    try:
        payload = jwt.decode(token, get_secret_key(), algorithms=["HS256"])
        user_id = int(payload.get("sub", "0"))
    except JWTError:
        return None
    user = await db.get(User, user_id)
    return user


