from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Response, Request, Depends, status
from fastapi.responses import JSONResponse
from app.db.models import *
from app.db.database import database, users_table, temp_registrations_table, temp_sessions_table, auth_sessions_table, password_resets_table
from app.utils import *
from app.services.email_service import send_otp_email, send_otp_sms, send_admin_notification
from datetime import datetime
from typing import Optional, List
import uuid
from datetime import datetime, timedelta
from typing import List, Optional
import uuid
import sqlalchemy

from fastapi import APIRouter, HTTPException, Response, Request, Depends, status

from app.db.database import (auth_sessions_table, database,
                             password_resets_table, temp_registrations_table,
                             temp_sessions_table, users_table)
from app.db.models import (
    RegisterRequest,
    VerifyRegistrationRequest,
    LoginRequest,
    VerifyOTPRequest,
    UserResponse,
    RegisterSuccessResponse,
    RegisterResponse,
    LoginPendingResponse,
    LoginSuccessResponse,
    SuccessResponse,
    UserListResponse,
    ApproveUserRequest,
    AdminResponse,
    ForgotPasswordRequest,
    VerifyResetOTPRequest,
    ResetPasswordRequest,
    ChangePasswordRequest,
)
from app.services.email_service import send_admin_notification, send_otp_email
from app.utilities import (
    hash_password,
    verify_password,
    generate_otp,
    is_email,
    is_phone,
    get_otp_expiry,
    get_auth_session_expiry,
    is_expired,
    generate_session_token,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ==================================================================================
# 1. HELPER FUNCTIONS - Cookie handling and user validation utilities
# ==================================================================================

# Helper function to get temp_registration_id from cookie


def get_temp_registration_id(request: Request) -> Optional[str]:
    return request.cookies.get("temp_registration_id")

# Helper function to get temp_session_id from cookie


def get_temp_session_id(request: Request) -> Optional[str]:
    return request.cookies.get("temp_session_id")

# Helper function to get auth_session_id from cookie


def get_auth_session_id(request: Request) -> Optional[str]:
    return request.cookies.get("auth_session_id")

# Helper function to get temp_password_reset_id from cookie


def get_temp_password_reset_id(request: Request) -> Optional[str]:
    return request.cookies.get("temp_password_reset_id")

# Helper function to get current user from session

async def get_current_user(request: Request) -> Optional[dict]:
    """Get current user from auth session"""
    auth_session_id = get_auth_session_id(request)
    if not auth_session_id:
        return None

    # Check auth session
    query = sqlalchemy.select(auth_sessions_table).where(
        auth_sessions_table.c.session_token == auth_session_id
    )
    session = await database.fetch_one(query)

    if not session or is_expired(session["expires_at"]):
        return None

    # Get user
    user_query = sqlalchemy.select(users_table).where(
        users_table.c.id == session.user_id
    )
    user = await database.fetch_one(user_query)
    return dict(user) if user else None

# Strict dependency to require authentication in routes
async def require_user(request: Request) -> dict:
    """Dependency that enforces an authenticated user (401 if missing)."""
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Not authenticated"}
        )
    return user

# Helper function to check if user is admin


async def require_admin(request: Request):
    """Require admin role"""
    user = await get_current_user(request)
    if not user or user.get('role') != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "error", "message": "Requires admin privileges"}
        )
    return user


# ==================================================================================
# 2. USER REGISTRATION - New user registration flow with email OTP verification
# ==================================================================================

@router.post("/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, response: Response):
    """
    Step 1 of Registration: Create temporary registration and send OTP
    
    Process:
    1. Validate password confirmation
    2. Check for existing email/phone
    3. Generate OTP and hash password
    4. Store temporary registration
    5. Send OTP via email
    6. Set temporary cookie for OTP verification
    """

    # Validate password confirmation
    if request.password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mật khẩu không trùng khớp"}
        )

    # Check if email or phone already exists
    query = sqlalchemy.select(users_table).where(
        sqlalchemy.or_(
            users_table.c.email == request.email,
            users_table.c.phone == request.phone
        )
    )
    existing_user = await database.fetch_one(query)

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"status": "error", "message": "Email hoặc số điện thoại đã được đăng kí"}
        )

    # Generate OTP and hash password
    otp = generate_otp()
    password_hash = hash_password(request.password)

    # Save temporary registration
    temp_reg_id = str(uuid.uuid4())
    temp_reg_data = {
        "id": temp_reg_id,
        "name": request.name,
        "email": request.email,
        "phone": request.phone,
        "password_hash": password_hash,
        "otp_code": otp,
        "otp_expires_at": get_otp_expiry()
    }

    # Delete any existing temp registration for this email/phone
    delete_query = sqlalchemy.delete(temp_registrations_table).where(
        sqlalchemy.or_(
            temp_registrations_table.c.email == request.email,
            temp_registrations_table.c.phone == request.phone
        )
    )
    await database.execute(delete_query)

    # Insert new temp registration
    insert_query = temp_registrations_table.insert().values(temp_reg_data)
    await database.execute(insert_query)
    # Set cookie
    response.set_cookie(
        key="temp_registration_id",
        value=temp_reg_id,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=300  # 5 minutes
    )

    return RegisterResponse(
        status="Loading",
        message="Mã OTP đã gửi vào email mà bạn nhập. Vui lòng hoàn thiện quá trình đăng kí"
    )


@router.post("/verify-registration", response_model=RegisterSuccessResponse, status_code=status.HTTP_201_CREATED)
async def verify_registration(request: VerifyRegistrationRequest, http_request: Request, response: Response):
    """
    Step 2 of Registration: Verify OTP and create user account
    
    Process:
    1. Validate temporary registration cookie
    2. Check OTP code and expiration
    3. Create user account (not approved yet)
    4. Send admin notification email
    5. Clean up temporary registration
    6. Return success response
    """

    temp_reg_id = get_temp_registration_id(http_request)
    if not temp_reg_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Chưa thấy đăng kí"}
        )

    # Get temp registration
    query = sqlalchemy.select(temp_registrations_table).where(
        temp_registrations_table.c.id == temp_reg_id
    )
    temp_reg = await database.fetch_one(query)

    if not temp_reg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Chưa thấy đăng kí"}
        )

    # Check OTP and expiry
    if temp_reg.otp_code != request.otp or is_expired(temp_reg.otp_expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mã OTP đã hết hạn hoặc không tồn tại"}
        )

    # Create user (not approved yet)
    user_id = str(uuid.uuid4())
    user_data = {
        "id": user_id,
        "name": temp_reg.name,
        "email": temp_reg.email,
        "phone": temp_reg.phone,
        "password_hash": temp_reg.password_hash,
        "role": "user",
        "is_active": True,
        "is_approved": False  # Need admin approval
    }

    insert_user_query = users_table.insert().values(user_data)
    await database.execute(insert_user_query)

    # Send notification to admin about new registration
    admin_notification_data = {
        "name": temp_reg.name,
        "email": temp_reg.email,
        "phone": temp_reg.phone,
        "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    }

    # Send admin notification (don't fail registration if email fails)
    try:
        await send_admin_notification(admin_notification_data)
    except Exception as e:
        print(f"Warning: Failed to send admin notification: {e}")

    # Delete temp registration
    delete_temp_query = sqlalchemy.delete(temp_registrations_table).where(
        temp_registrations_table.c.id == temp_reg_id
    )
    await database.execute(delete_temp_query)

    # Clear temp registration cookie
    response.delete_cookie(key="temp_registration_id", path="/")

    return RegisterSuccessResponse(
        status="success",
        message="Chúc mừng bạn đã đăng kí thành công! Vui lòng chờ admin phê duyệt.",
        user=UserResponse(
            id=user_id,
            name=temp_reg.name,
            email=temp_reg.email,
            phone=temp_reg.phone,
            role="user",
            is_approved=False
        )
    )


@router.post("/resend-registration-otp", response_model=SuccessResponse)
async def resend_registration_otp(request: Request):
    """
    Resend Registration OTP: Send new OTP if previous one expired or lost
    
    Process:
    1. Validate temporary registration session
    2. Generate new OTP code
    3. Update registration record with new OTP
    4. Send new OTP via email
    """

    temp_reg_id = get_temp_registration_id(request)
    if not temp_reg_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Không thấy đăng kí"}
        )

    # Get temp registration
    query = sqlalchemy.select(temp_registrations_table).where(
        temp_registrations_table.c.id == temp_reg_id
    )
    temp_reg = await database.fetch_one(query)

    if not temp_reg:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Không thấy đăng kí"}
        )

    # Generate new OTP
    new_otp = generate_otp()

    # Update temp registration with new OTP
    update_query = sqlalchemy.update(temp_registrations_table).where(
        temp_registrations_table.c.id == temp_reg_id
    ).values(
        otp_code=new_otp,
        otp_expires_at=get_otp_expiry()
    )
    await database.execute(update_query)

    # Send new OTP
    email_sent = await send_otp_email(temp_reg.email, new_otp, "registration")
    if not email_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Không thể gửi email xác thực"}
        )

    return SuccessResponse(
        status="success",
        message="1 mã OTP mới được gửi đến email của bạn."
    )


# ==================================================================================
# 3. USER LOGIN - Two-factor authentication login process
# ==================================================================================

@router.post("/login", response_model=LoginPendingResponse)
async def login(request: LoginRequest, response: Response):
    """
    Step 1 of Login: Validate credentials and send OTP
    
    Process:
    1. Identify user by email or phone
    2. Verify password
    3. Check user approval and active status
    4. Generate OTP and create temporary session
    5. Send OTP via email
    6. Set temporary session cookie
    """

    # Determine if identifier is email or phone
    if is_email(request.identifier):
        query = sqlalchemy.select(users_table).where(users_table.c.email == request.identifier)
    elif is_phone(request.identifier):
        query = sqlalchemy.select(users_table).where(users_table.c.phone == request.identifier)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Định dạng email hoặc số điện thoại không hợp lệ"}
        )

    user = await database.fetch_one(query)
    if not user or not verify_password(request.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Thông tin đăng nhập không chính xác"}
        )

    # Check if user is approved
    if not user["is_approved"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"status": "error", "message": "Tài khoản của bạn chưa được admin phê duyệt"}
        )

    if not user["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Tài khoản đã bị vô hiệu hóa"}
        )

    # Generate OTP and create temp session
    otp = generate_otp()
    temp_session_id = str(uuid.uuid4())

    # Delete any existing temp sessions for this user
    delete_query = sqlalchemy.delete(temp_sessions_table).where(
        temp_sessions_table.c.user_id == user["id"]
    )
    await database.execute(delete_query)

    # Create new temp session
    temp_session_data = {
        "id": temp_session_id,
        "user_id": user["id"],
        "otp_code": otp,
        "otp_expires_at": get_otp_expiry()
    }

    insert_query = temp_sessions_table.insert().values(temp_session_data)
    await database.execute(insert_query)
    # Set cookie
    response.set_cookie(
        key="temp_session_id",
        value=temp_session_id,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=300  # 5 minutes
    )

    return LoginPendingResponse(
        status="pending",
        message="OTP has been sent to your email or phone."
    )
# --------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# ==================================================================================
# 4. PASSWORD RESET - Forgot password recovery flow with email verification
# ==================================================================================

@router.post("/forgot-password", response_model=SuccessResponse)
async def forgot_password(request: ForgotPasswordRequest, response: Response):
    """
    Step 1 of Password Reset: Request password reset
    
    Process:
    1. Validate user email and approval status
    2. Generate reset token and OTP
    3. Store password reset record
    4. Send OTP via email
    5. Set temporary reset cookie
    """
    email = request.email.lower().strip()

    # Chỉ tìm user khi email khớp và đã được phê duyệt
    user_query = (
        sqlalchemy.select(users_table)
        .where(users_table.c.email == email)
        .where(users_table.c.is_approved)
    )
    user = await database.fetch_one(user_query)

    # Nếu không tìm thấy user hoặc chưa được phê duyệt => không cho reset
    if not user:
        return SuccessResponse(
            status="failed",
            message="Email không tồn tại hoặc chưa được phê duyệt. Vui lòng liên hệ quản trị viên."
        )

    # Nếu hợp lệ thì tạo bản ghi reset password
    reset_id = str(uuid.uuid4())
    otp = generate_otp()
    reset_data = {
        "id": reset_id,
        "user_id": user["id"],
        "email": email,
        "otp_code": otp,
        "otp_expires_at": get_otp_expiry(),
        "is_verified": False,
        "used": False
    }

    # Xóa bản ghi reset cũ của email này (nếu có)
    await database.execute(
        sqlalchemy.delete(password_resets_table).where(password_resets_table.c.email == email)
    )

    insert_query = password_resets_table.insert().values(reset_data)
    await database.execute(insert_query)

    # Gửi OTP qua email (nếu lỗi thì chỉ log, không thông báo cho client)
    try:
        await send_otp_email(email, otp, "password_reset")
    except Exception as e:
        print(f"Warning: failed to send password reset OTP to {email}: {e}")

    # Đặt cookie tạm để xác thực OTP
    response.set_cookie(
        key="temp_password_reset_id",
        value=reset_id,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=600  # 10 phút
    )

    return SuccessResponse(
        status="success",
        message="OTP đã được gửi. Vui lòng kiểm tra email và nhập mã OTP để tiếp tục."
    )

@router.post("/change-password", response_model=SuccessResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: dict = Depends(require_user),
):
    """
    Change Password: Authenticated user updates their password

    Process:
    1. Require user login
    2. Check current password
    3. Verify new password & confirm
    4. Hash and update in DB
    5. Return success
    """

    # 1. Check current password
    if not verify_password(request.current_password, current_user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mật khẩu hiện tại không chính xác"},
        )

    # 2. Confirm new password match
    if request.new_password != request.confirm_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Xác nhận mật khẩu mới không khớp"},
        )

    # 3. Hash new password
    new_hashed = hash_password(request.new_password)

    # 4. Update vào DB
    update_q = (
        users_table.update()
        .where(users_table.c.id == current_user["id"])
        .values(password_hash=new_hashed)
    )
    await database.execute(update_q)

    # 5. (optional) có thể xoá session cũ để buộc đăng nhập lại
    # await database.execute(sqlalchemy.delete(auth_sessions_table).where(
    #     auth_sessions_table.c.user_id == current_user["id"]
    # ))

    return SuccessResponse(
        status="success",
        message="Đổi mật khẩu thành công!"
    )
@router.post("/verify-reset-otp", response_model=SuccessResponse)
async def verify_reset_otp(request: VerifyResetOTPRequest, http_request: Request):
    """
    Step 2 of Password Reset: Verify OTP code
    
    Process:
    1. Validate reset session cookie
    2. Check OTP code and expiration
    3. Auto-resend OTP if expired
    4. Mark OTP as verified if valid
    """
    reset_id = get_temp_password_reset_id(http_request)
    if not reset_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên reset không hợp lệ"}
        )

    query = sqlalchemy.select(password_resets_table).where(password_resets_table.c.id == reset_id)
    reset_record = await database.fetch_one(query)
    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên reset không hợp lệ"}
        )

    if reset_record.used:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mã đã được sử dụng"}
        )

    # Nếu OTP đã hết hạn (sau 5 phút) thì sinh lại OTP mới và gửi lại
    if is_expired(reset_record.otp_expires_at):
        await resend_otp(reset_record)
        return SuccessResponse(
            status="expired",
            message="Mã OTP đã hết hạn. OTP mới đã được gửi đến email của bạn."
        )

    # Nếu OTP không khớp
    if reset_record.otp_code != request.otp:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mã OTP không hợp lệ"}
        )

    # Nếu mọi thứ hợp lệ => mark là verified
    update_q = (
        sqlalchemy.update(password_resets_table)
        .where(password_resets_table.c.id == reset_id)
        .values(is_verified=True)
    )
    await database.execute(update_q)

    return SuccessResponse(
        status="success",
        message="Xác thực OTP thành công. Vui lòng đặt mật khẩu mới."
    )


async def resend_otp(reset_record):
    """
    Utility function: Generate and send new OTP when previous one expires
    
    Process:
    1. Generate new OTP with 5-minute expiry
    2. Update database record
    3. Send new OTP via email
    """
    new_otp = generate_otp()
    new_expiry = get_otp_expiry(minutes=5)  # chỉ sống 5 phút

    # Update record trong DB
    update_q = (
        sqlalchemy.update(password_resets_table)
        .where(password_resets_table.c.id == reset_record.id)
        .values(otp_code=new_otp, otp_expires_at=new_expiry, is_verified=False)
    )
    await database.execute(update_q)

    # Gửi lại email OTP
    try:
        await send_otp_email(reset_record.email, new_otp, "password_reset")
    except Exception as e:
        print(f"Warning: resend OTP failed for {reset_record.email}: {e}")

    return new_otp


@router.post("/resend-reset-otp", response_model=SuccessResponse)
async def resend_reset_otp(http_request: Request):
    """
    Manual Resend Reset OTP: Allow user to request new OTP
    
    Process:
    1. Validate reset session
    2. Generate new OTP with fresh expiry
    3. Update database record
    4. Send new OTP via email
    """

    reset_id = get_temp_password_reset_id(http_request)
    if not reset_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên reset không hợp lệ"}
        )

    query = sqlalchemy.select(password_resets_table).where(password_resets_table.c.id == reset_id)
    reset_record = await database.fetch_one(query)
    if not reset_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên reset không hợp lệ"}
        )

    # Sinh OTP mới
    new_otp = generate_otp()
    new_expiry = get_otp_expiry(minutes=5)

    update_q = (
        sqlalchemy.update(password_resets_table)
        .where(password_resets_table.c.id == reset_id)
        .values(
            otp_code=new_otp,
            otp_expires_at=new_expiry,
            is_verified=False
        )
    )
    await database.execute(update_q)

    # Gửi email OTP mới
    try:
        await send_otp_email(reset_record.email, new_otp, "password_reset")
    except Exception as e:
        print(f"Warning: resend OTP failed for {reset_record.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Không thể gửi lại OTP, thử lại sau."}
        )

    return SuccessResponse(
        status="success",
        message="Mã OTP mới đã được gửi đến email của bạn. Vui lòng kiểm tra hộp thư."
    )


@router.post("/reset-password", response_model=SuccessResponse)
async def reset_password(request: ResetPasswordRequest, http_request: Request, response: Response):
    """
    Step 3 of Password Reset: Set new password after OTP verification
    
    Process:
    1. Validate reset session and verification status
    2. Confirm password match
    3. Update user password hash
    4. Invalidate all existing auth sessions (force logout)
    5. Mark reset request as used
    6. Clear reset cookie
    """
    reset_id = get_temp_password_reset_id(http_request)
    if not reset_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"status": "error", "message": "Phiên reset không hợp lệ"})

    # fetch reset record
    query = sqlalchemy.select(password_resets_table).where(password_resets_table.c.id == reset_id)
    reset_record = await database.fetch_one(query)
    if not reset_record:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail={"status": "error", "message": "Phiên reset không hợp lệ"})

    if reset_record.used:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "error", "message": "Yêu cầu reset đã được xử lý"})

    if not reset_record.is_verified:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "error", "message": "OTP chưa được xác thực"})

    if is_expired(reset_record.otp_expires_at):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "error", "message": "Phiên reset đã hết hạn"})

    # check password match
    if request.password != request.confirm_password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"status": "error", "message": "Mật khẩu không trùng khớp"})

    # find user by user_id or email
    user = None
    if reset_record.user_id:
        user_q = sqlalchemy.select(users_table).where(users_table.c.id == reset_record.user_id)
        user = await database.fetch_one(user_q)
    else:
        # fallback by email if user_id is null (maybe account did not exist at request time)
        user_q = sqlalchemy.select(users_table).where(users_table.c.email == reset_record.email)
        user = await database.fetch_one(user_q)

    # If user does not exist -> we still return generic success to avoid leakage,
    # but no password is changed.
    if user:
        new_hash = hash_password(request.password)
        update_user_q = users_table.update().where(users_table.c.id == user["id"]).values(password_hash=new_hash)
        await database.execute(update_user_q)

        # Optional: Invalidate all existing auth sessions for the user (force logout)
        await database.execute(sqlalchemy.delete(auth_sessions_table).where(auth_sessions_table.c.user_id == user["id"]))

    # mark reset record used
    await database.execute(sqlalchemy.update(password_resets_table).where(password_resets_table.c.id == reset_id).values(used=True))

    # remove cookie
    response.delete_cookie(key="temp_password_reset_id", path="/")

    return SuccessResponse(status="success", message="Mật khẩu đã được đặt lại. Vui lòng đăng nhập lại.")
# ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------


# ==================================================================================
# 5. SESSION MANAGEMENT - Login completion, logout, and user introspection
# ==================================================================================

@router.post("/verify-otp", response_model=LoginSuccessResponse)
async def verify_otp(request: VerifyOTPRequest, http_request: Request, response: Response):
    """
    Step 2 of Login: Complete login process with OTP verification
    
    Process:
    1. Validate temporary session cookie
    2. Check OTP code and expiration
    3. Create permanent auth session
    4. Set auth session cookie
    5. Clean up temporary session
    6. Return user information
    """

    temp_session_id = get_temp_session_id(http_request)
    if not temp_session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên đăng nhập không hợp lệ"}
        )

    # Get temp session
    query = sqlalchemy.select(temp_sessions_table).where(
        temp_sessions_table.c.id == temp_session_id
    )
    temp_session = await database.fetch_one(query)

    if not temp_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên đăng nhập không hợp lệ"}
        )

    # Check OTP and expiry
    if temp_session.otp_code != request.otp or is_expired(temp_session.otp_expires_at):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Mã OTP không hợp lệ hoặc đã hết hạn"}
        )

    # Get user info
    user_query = sqlalchemy.select(users_table).where(
        users_table.c.id == temp_session.user_id
    )
    user = await database.fetch_one(user_query)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Người dùng không tồn tại"}
        )    # Create auth session
    auth_session_id = str(uuid.uuid4())
    session_token = generate_session_token()

    auth_session_data = {
        "id": auth_session_id,
        "user_id": user["id"],
        "session_token": session_token,
        "expires_at": get_auth_session_expiry()
    }

    # Delete any existing auth sessions for this user
    delete_auth_query = sqlalchemy.delete(auth_sessions_table).where(
        auth_sessions_table.c.user_id == user["id"]
    )
    await database.execute(delete_auth_query)

    # Insert new auth session
    insert_auth_query = auth_sessions_table.insert().values(auth_session_data)
    await database.execute(insert_auth_query)

    # Delete temp session
    delete_temp_query = sqlalchemy.delete(temp_sessions_table).where(
        temp_sessions_table.c.id == temp_session_id
    )
    await database.execute(delete_temp_query)

    # Set auth cookie and clear temp cookie
    response.set_cookie(
        key="auth_session_id",
        value=session_token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=86400  # 24 hours
    )
    response.delete_cookie(key="temp_session_id", path="/")

    return LoginSuccessResponse(
        status="success",
        message="Login successful",
        user=UserResponse(
            id=str(user["id"]),
            name=user["name"],
            email=user["email"],
            phone=user["phone"],
            role=user["role"],
            is_approved=user["is_approved"]
        )
    )


@router.post("/resend-otp", response_model=SuccessResponse)
async def resend_otp(request: Request):
    """
    Resend Login OTP: Send new OTP for login process
    
    Process:
    1. Validate temporary session
    2. Get user information
    3. Generate new OTP
    4. Update temporary session
    5. Send new OTP via email
    """

    temp_session_id = get_temp_session_id(request)
    if not temp_session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên đăng nhập không hợp lệ"}
        )

    # Get temp session with user info
    query = sqlalchemy.select(temp_sessions_table).where(
        temp_sessions_table.c.id == temp_session_id
    )
    temp_session = await database.fetch_one(query)

    if not temp_session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên đăng nhập không hợp lệ"}
        )

    # Get user info
    user_query = sqlalchemy.select(users_table).where(
        users_table.c.id == temp_session.user_id
    )
    user = await database.fetch_one(user_query)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Người dùng không tồn tại"}
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Phiên đăng nhập không hợp lệ"}
        )

    # Generate new OTP
    new_otp = generate_otp()

    # Update temp session with new OTP
    update_query = sqlalchemy.update(temp_sessions_table).where(
        temp_sessions_table.c.id == temp_session_id
    ).values(
        otp_code=new_otp,
        otp_expires_at=get_otp_expiry()
    )
    await database.execute(update_query)

    # Send new OTP to email (you can modify logic to determine email vs SMS)
    otp_sent = await send_otp_email(user["email"], new_otp, "login")

    if not otp_sent:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"status": "error", "message": "Không thể gửi mã OTP"}
        )

    return SuccessResponse(
        status="success",
        message="A new OTP has been sent to your email/phone."
    )


@router.post("/logout", response_model=SuccessResponse)
async def logout(request: Request, response: Response):
    """
    User Logout: Terminate user session
    
    Process:
    1. Get auth session cookie
    2. Delete session from database
    3. Clear auth session cookie
    """

    auth_session_id = get_auth_session_id(request)
    if auth_session_id:
        # Delete auth session from database
        delete_query = sqlalchemy.delete(auth_sessions_table).where(
            auth_sessions_table.c.session_token == auth_session_id
        )
        await database.execute(delete_query)

    # Clear cookie
    response.delete_cookie(key="auth_session_id", path="/")

    return SuccessResponse(
        status="success",
        message="Đăng xuất thành công"
    )

# Session introspection


@router.get("/me", response_model=UserResponse)
async def me(request: Request):
    """
    Get Current User: Return current authenticated user information
    
    Process:
    1. Validate auth session cookie
    2. Get user information from database
    3. Return user details
    """
    user = await get_current_user(request)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"status": "error", "message": "Chưa đăng nhập"}
        )
    return UserResponse(
        id=str(user["id"]),
        name=user["name"],
        email=user["email"],
        phone=user["phone"],
        role=user["role"],
        is_approved=user["is_approved"],
    )

# ==================================================================================
# 6. ADMIN ENDPOINTS - Administrative user management functions
# ==================================================================================

@router.get("/admin/pending-users", response_model=List[UserListResponse])
async def get_pending_users(request: Request, admin_user=Depends(require_admin)):
    """
    Get Pending Users: List all users awaiting admin approval
    
    Process:
    1. Verify admin privileges
    2. Query users with is_approved=False
    3. Return list ordered by creation date
    """

    query = sqlalchemy.select(users_table).where(
        users_table.c.is_approved == False
    ).order_by(users_table.c.created_at.desc())

    users = await database.fetch_all(query)

    return [
        UserListResponse(
            id=str(user["id"]),
            name=user["name"],
            email=user["email"],
            phone=user["phone"],
            role=user["role"],
            is_approved=user["is_approved"],
            is_active=user["is_active"],
            created_at=user["created_at"]
        )
        for user in users
    ]


@router.post("/admin/approve-user", response_model=AdminResponse)
async def approve_user(request: ApproveUserRequest, http_request: Request, admin_user=Depends(require_admin)):
    """
    Approve User: Grant user access after admin review
    
    Process:
    1. Verify admin privileges
    2. Check user exists and is not already approved
    3. Update user approval status with admin details
    4. Send approval confirmation email
    5. Return success response
    """

    # Check if user exists
    user_query = sqlalchemy.select(users_table).where(
        users_table.c.id == request.user_id
    )
    user = await database.fetch_one(user_query)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Người dùng không tồn tại"}
        )

    if user["is_approved"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"status": "error", "message": "Người dùng đã được phê duyệt"}
        )

    # Approve user
    update_query = users_table.update().where(
        users_table.c.id == request.user_id
    ).values(
        is_approved=True,
        approved_at=datetime.utcnow(),
        approved_by=admin_user["id"]
    )
    await database.execute(update_query)

    # Send approval email
    approval_sent = await send_otp_email(
        user["email"],
        "",
        "approval"
    )

    return AdminResponse(
        status="success",
        message=f"Đã phê duyệt người dùng {user['name']}",
        data={"user_id": request.user_id, "user_name": user["name"]}
    )


@router.get("/admin/all-users", response_model=List[UserListResponse])
async def get_all_users(request: Request, admin_user=Depends(require_admin)):
    """
    Get All Users: List all users in the system
    
    Process:
    1. Verify admin privileges
    2. Query all users from database
    3. Return complete user list ordered by creation date
    """

    query = sqlalchemy.select(users_table).order_by(users_table.c.created_at.desc())
    users = await database.fetch_all(query)

    return [
        UserListResponse(
            id=str(user["id"]),
            name=user["name"],
            email=user["email"],
            phone=user["phone"],
            role=user["role"],
            is_approved=user["is_approved"],
            is_active=user["is_active"],
            created_at=user["created_at"]
        )
        for user in users
    ]


@router.delete("/admin/delete-user/{user_id}", response_model=AdminResponse)
async def delete_user(user_id: str, http_request: Request, admin_user=Depends(require_admin)):
    """
    Delete User: Permanently remove user from system
    
    Process:
    1. Verify admin privileges
    2. Check user exists
    3. Delete user record from database
    4. Return confirmation response
    
    WARNING: This is a permanent action that cannot be undone
    """

    # Check if user exists
    user_query = sqlalchemy.select(users_table).where(
        users_table.c.id == user_id
    )
    user = await database.fetch_one(user_query)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"status": "error", "message": "Người dùng không tồn tại"}
        )

    # Delete user
    delete_query = sqlalchemy.delete(users_table).where(
        users_table.c.id == user_id
    )
    await database.execute(delete_query)

    return AdminResponse(
        status="success",
        message=f"Đã xóa người dùng {user['name']}",
        data={"user_id": user_id, "user_name": user["name"]}
    )
