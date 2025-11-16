from datetime import datetime, timedelta
from typing import Optional, Tuple
import os
import secrets

from passlib.context import CryptContext
from jose import jwt
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.user import User
from app.logging_config import get_logger


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
logger = get_logger(__name__)

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 7


def get_secret_key() -> str:
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        raise RuntimeError(
            "SECRET_KEY environment variable is not set. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
        )
    if secret_key in {
        "change-this-in-production",
        "secret",
        "dev",
        "test",
        "your-secret-key-here",
    }:
        raise RuntimeError("SECRET_KEY uses a known insecure placeholder. Please set a secure value.")
    if len(secret_key) < 32:
        raise RuntimeError("SECRET_KEY must be at least 32 characters long.")
    return secret_key


def generate_secret_key() -> str:
    key = secrets.token_urlsafe(64)
    logger.info("Generated new secret key")
    return key


def _truncate_password_for_bcrypt(password: str) -> str:
    """
    Truncate password to 72 bytes (bcrypt limit).
    Bcrypt only uses the first 72 bytes of a password.
    """
    if not isinstance(password, str):
        password = str(password)
    password_bytes = password.encode('utf-8')
    original_len = len(password_bytes)
    if original_len > 72:
        # Truncate to exactly 72 bytes
        truncated_bytes = password_bytes[:72]
        # Decode back to string, handling any incomplete UTF-8 sequences
        password = truncated_bytes.decode('utf-8', errors='ignore')
        logger.warning(
            f"Password truncated from {original_len} bytes to 72 bytes (bcrypt limit). "
            f"Only first 72 bytes will be used for hashing."
        )
    return password


def hash_password(password: str) -> str:
    # Bcrypt has a 72-byte limit for passwords
    # Truncate BEFORE passing to passlib to avoid initialization errors
    password = _truncate_password_for_bcrypt(password)
    # Verify truncation worked
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        logger.error(f"Password still too long after truncation: {len(password_bytes)} bytes")
        # Force truncate again
        password = password_bytes[:72].decode('utf-8', errors='ignore')
    try:
        return pwd_context.hash(password)
    except ValueError as e:
        if "cannot be longer than 72 bytes" in str(e):
            logger.error(f"Bcrypt error despite truncation. Password length: {len(password.encode('utf-8'))} bytes")
            # Last resort: force to 72 bytes
            password_bytes = password.encode('utf-8')[:72]
            password = password_bytes.decode('utf-8', errors='ignore')
            return pwd_context.hash(password)
        raise


def verify_password(password: str, password_hash: str) -> bool:
    # Truncate password to 72 bytes to match hash_password behavior
    password = _truncate_password_for_bcrypt(password)
    return pwd_context.verify(password, password_hash)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=JWT_ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, get_secret_key(), algorithm=JWT_ALGORITHM)
    return encoded_jwt


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def get_user_count(db: AsyncSession) -> int:
    result = await db.execute(select(func.count(User.id)))
    return int(result.scalar() or 0)


async def create_user(db: AsyncSession, email: str, password: str, role: str = "staff") -> Tuple[Optional[User], Optional[str]]:
    existing = await get_user_by_email(db, email)
    if existing:
        return None, "User already exists"
    user = User(email=email, password_hash=hash_password(password), role=role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user, None


async def ensure_admin_user(db: AsyncSession, email: Optional[str], password: Optional[str]) -> None:
    """
    Create an admin user if none exists and env ADMIN_EMAIL/ADMIN_PASSWORD provided.
    """
    if not email or not password:
        logger.info("Admin bootstrap skipped - ADMIN_EMAIL or ADMIN_PASSWORD not set")
        return
    count = await get_user_count(db)
    if count > 0:
        logger.info(f"Admin bootstrap skipped - {count} user(s) already exist")
        return
    logger.info(f"Creating initial admin user: {email}")
    user, error = await create_user(db, email=email, password=password, role="admin")
    if error:
        logger.error(f"Failed to create admin user: {error}")
        raise RuntimeError(f"Admin user creation failed: {error}")
    logger.info(f"Admin user created successfully: {email} (ID: {user.id})")


