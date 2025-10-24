import random
import re
import string
from datetime import datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import (ALGORITHM, AUTH_SESSION_EXPIRE_MINUTES,
                             OTP_EXPIRE_MINUTES, SECRET_KEY,
                             SESSION_EXPIRE_MINUTES)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def generate_otp() -> str:
    """Generate a 6-digit OTP"""
    return ''.join(random.choices(string.digits, k=6))


def is_email(identifier: str) -> bool:
    """Check if identifier is an email"""
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, identifier) is not None


def is_phone(identifier: str) -> bool:
    """Check if identifier is a phone number"""
    phone_pattern = r'^[0-9]{10,11}$'
    return re.match(phone_pattern, identifier) is not None


def get_otp_expiry() -> datetime:
    """Get OTP expiry time"""
    return datetime.utcnow() + timedelta(minutes=OTP_EXPIRE_MINUTES)


def get_session_expiry() -> datetime:
    """Get session expiry time"""
    return datetime.utcnow() + timedelta(minutes=SESSION_EXPIRE_MINUTES)


def get_auth_session_expiry() -> datetime:
    """Get auth session expiry time"""
    return datetime.utcnow() + timedelta(minutes=AUTH_SESSION_EXPIRE_MINUTES)


def is_expired(expires_at: datetime) -> bool:
    """Check if a timestamp is expired"""
    return datetime.utcnow() > expires_at


def create_access_token(data: dict) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=AUTH_SESSION_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict:
    """Verify JWT token"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def generate_session_token() -> str:
    """Generate a unique session token"""
    return ''.join(random.choices(string.ascii_letters + string.digits, k=64))
