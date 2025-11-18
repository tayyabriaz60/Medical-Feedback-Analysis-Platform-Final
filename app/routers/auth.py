from typing import Optional
import os
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt, JWTError
from sqlalchemy import select, delete

from app.db import get_db
from app.services.auth_service import (
    create_user,
    get_user_by_email,
    verify_password,
    create_access_token,
    create_refresh_token,
    get_secret_key,
    get_user_count,
    hash_password,
)
from app.models.user import User
from app.deps import get_current_user, get_current_user_optional
from app.logging_config import get_logger


router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger(__name__)


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    role: Optional[str] = Field(default="staff", pattern="^(admin|staff)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    role: str


@router.post("/register", response_model=dict, status_code=201)
async def register(
    request: Request,
    payload: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional)
):
    """
    Create a user.
    - If no users exist yet, allow open registration (bootstrap).
    - Otherwise, require current user to be admin.
    """
    total = await get_user_count(db)
    if total > 0 and (not current_user or current_user.role != "admin"):
        raise HTTPException(status_code=403, detail="Only admin can register users")
    user, error = await create_user(db, payload.email, payload.password, role=payload.role or "staff")
    if error:
        raise HTTPException(status_code=400, detail=error)
    return {"id": user.id, "email": user.email, "role": user.role}


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db)
):
    logger.info(f"Login attempt for email: {payload.email}")
    
    # Check if user exists (case-insensitive email match)
    user = await get_user_by_email(db, payload.email)
    if not user:
        # Log all users for debugging (only in development)
        import os
        if os.getenv("ENVIRONMENT", "production").lower() == "development":
            all_users = await db.execute(select(User))
            users_list = all_users.scalars().all()
            logger.debug(f"Available users in database: {[u.email for u in users_list]}")
        
        logger.warning(f"Login failed: User not found for email: {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid credentials"
        )
    
    # Verify password
    try:
        password_valid = verify_password(payload.password, user.password_hash)
    except Exception as e:
        logger.error(f"Password verification error for {payload.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials"
        )
    
    if not password_valid:
        logger.warning(f"Login failed: Invalid password for email: {payload.email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Invalid credentials"
        )
    
    logger.info(f"Login successful for user: {user.email} (role: {user.role})")
    access_token = create_access_token({"sub": str(user.id), "email": user.email, "role": user.role})
    refresh_token = create_refresh_token({"sub": str(user.id)})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token, role=user.role)


def decode_token(token: str) -> dict:
    return jwt.decode(token, get_secret_key(), algorithms=["HS256"])


@router.post("/bootstrap-admin", response_model=dict, status_code=201)
async def bootstrap_admin(db: AsyncSession = Depends(get_db)):
    """
    Create admin user from environment variables if no users exist.
    This is a fallback if admin bootstrap failed during startup.
    """
    import os
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    logger.info(f"Bootstrap endpoint called. ADMIN_EMAIL: {admin_email}, ADMIN_PASSWORD: {'*' * len(admin_password) if admin_password else 'NOT SET'}")
    
    if not admin_email or not admin_password:
        logger.error("Bootstrap failed: ADMIN_EMAIL or ADMIN_PASSWORD not set in environment")
        raise HTTPException(
            status_code=400, 
            detail="ADMIN_EMAIL and ADMIN_PASSWORD environment variables must be set"
        )
    
    # Check if admin user already exists (by exact email)
    existing = await get_user_by_email(db, admin_email)
    if existing:
        logger.info(f"Admin user already exists: {existing.email} (ID: {existing.id})")
        return {
            "message": "Admin user already exists",
            "email": existing.email,
            "role": existing.role,
            "id": existing.id
        }
    
    # Check if any users exist
    total = await get_user_count(db)
    if total > 0:
        # List all users for debugging
        all_users_result = await db.execute(select(User))
        all_users = all_users_result.scalars().all()
        user_emails = [u.email for u in all_users]
        logger.warning(f"Users already exist ({total}): {user_emails}. Cannot bootstrap admin.")
        raise HTTPException(
            status_code=400,
            detail=f"Users already exist ({total}). Cannot bootstrap admin. Existing users: {', '.join(user_emails)}"
        )
    
    # Create admin user
    logger.info(f"Bootstrap: Creating admin user: {admin_email}")
    try:
        user, error = await create_user(db, admin_email, admin_password, role="admin")
        if error:
            logger.error(f"Bootstrap failed: {error}")
            raise HTTPException(status_code=400, detail=f"Failed to create admin user: {error}")
        
        logger.info(f"Bootstrap: Admin user created successfully: {admin_email} (ID: {user.id})")
        return {
            "message": "Admin user created successfully",
            "email": user.email,
            "role": user.role,
            "id": user.id
        }
    except Exception as e:
        logger.exception(f"Bootstrap exception: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create admin user: {str(e)}")


@router.get("/me", response_model=dict)
async def me(current_user: User = Depends(get_current_user)):
    """
    Get current user information using Authorization: Bearer <token>
    """
    return {"id": current_user.id, "email": current_user.email, "role": current_user.role}


@router.post("/setup-admin", response_model=dict, status_code=201)
async def setup_admin(db: AsyncSession = Depends(get_db)):
    """
    Setup admin user from environment variables
    - Deletes any existing admin with same email
    - Creates fresh admin with ENV credentials
    - Use this to fix login issues
    """
    # Get credentials from environment
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_password = os.getenv("ADMIN_PASSWORD")
    
    logger.info(f"Setup Admin endpoint called. Email: {admin_email}")
    
    if not admin_email or not admin_password:
        logger.error("Setup failed: ADMIN_EMAIL or ADMIN_PASSWORD not set in environment")
        return {
            "error": "ADMIN_EMAIL or ADMIN_PASSWORD not set in environment",
            "status": "failed"
        }
    
    try:
        # Delete existing admin with same email
        await db.execute(delete(User).where(User.email == admin_email))
        await db.commit()
        logger.info(f"Deleted existing admin: {admin_email}")
        
        # Create fresh admin with new password hash
        new_admin = User(
            email=admin_email,
            password_hash=hash_password(admin_password),
            role="admin"
        )
        db.add(new_admin)
        await db.commit()
        await db.refresh(new_admin)
        
        logger.info(f"Created fresh admin: {admin_email} (ID: {new_admin.id})")
        
        return {
            "message": "Admin setup successful",
            "email": admin_email,
            "id": new_admin.id,
            "status": "success"
        }
        
    except Exception as e:
        logger.error(f"Admin setup failed: {str(e)}")
        return {
            "error": str(e),
            "status": "failed"
        }

