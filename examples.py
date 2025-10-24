"""
Example usage of the Authentication API
"""

import requests
import json

BASE_URL = "http://localhost:8000"


def register_user():
    """Example: Register a new user"""
    url = f"{BASE_URL}/auth/register"
    data = {
        "name": "Nguyen Van A",
        "email": "user@example.com",
        "phone": "0987654321",
        "password": "mypassword123",
        "confirm_password": "mypassword123"
    }

    response = requests.post(url, json=data)
    print(f"Register Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('temp_registration_id')


def verify_registration(temp_registration_id, otp):
    """Example: Verify registration with OTP"""
    url = f"{BASE_URL}/auth/verify-registration"
    data = {"otp": otp}
    cookies = {"temp_registration_id": temp_registration_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Verify Registration Response: {response.status_code}")
    print(f"Body: {response.json()}")

    if response.status_code == 201:
        print("✅ Registration completed successfully!")
        print("📧 Admin has been notified via email")
        print("⏳ User needs to wait for admin approval")

    return response


def login_user():
    """Example: Login user"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "identifier": "user@example.com",  # or phone number
        "password": "mypassword123"
    }

    response = requests.post(url, json=data)
    print(f"Login Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('temp_session_id')


def verify_login_otp(temp_session_id, otp):
    """Example: Verify login OTP"""
    url = f"{BASE_URL}/auth/verify-otp"
    data = {"otp": otp}
    cookies = {"temp_session_id": temp_session_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Verify OTP Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('auth_session_id')


def resend_registration_otp(temp_registration_id):
    """Example: Resend registration OTP"""
    url = f"{BASE_URL}/auth/resend-registration-otp"
    cookies = {"temp_registration_id": temp_registration_id}

    response = requests.post(url, cookies=cookies)
    print(f"Resend Registration OTP Response: {response.status_code}")
    print(f"Body: {response.json()}")


def resend_login_otp(temp_session_id):
    """Example: Resend login OTP"""
    url = f"{BASE_URL}/auth/resend-otp"
    cookies = {"temp_session_id": temp_session_id}

    response = requests.post(url, cookies=cookies)
    print(f"Resend Login OTP Response: {response.status_code}")
    print(f"Body: {response.json()}")


def logout_user(auth_session_id):
    """Example: Logout user"""
    url = f"{BASE_URL}/auth/logout"
    cookies = {"auth_session_id": auth_session_id}

    response = requests.post(url, cookies=cookies)
    print(f"Logout Response: {response.status_code}")
    print(f"Body: {response.json()}")


def check_health():
    """Example: Check API health"""
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    print(f"Health Check Response: {response.status_code}")
    print(f"Body: {response.json()}")


if __name__ == "__main__":
    """
Example usage of the Authentication API with Admin Approval
"""

BASE_URL = "http://localhost:8000"


def register_user():
    """Example: Register a new user"""
    url = f"{BASE_URL}/auth/register"
    data = {
        "name": "Nguyen Van A",
        "email": "user@example.com",
        "phone": "0987654321",
        "password": "mypassword123",
        "confirm_password": "mypassword123"
    }

    response = requests.post(url, json=data)
    print(f"Register Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('temp_registration_id')


def verify_registration(temp_registration_id, otp):
    """Example: Verify registration with OTP"""
    url = f"{BASE_URL}/auth/verify-registration"
    data = {"otp": otp}
    cookies = {"temp_registration_id": temp_registration_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Verify Registration Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print("🎉 Registration successful! Now waiting for admin approval...")


def login_user_before_approval():
    """Example: Try to login before admin approval (should fail)"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "identifier": "user@example.com",
        "password": "mypassword123"
    }

    response = requests.post(url, json=data)
    print(f"Login Before Approval Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print("❌ Login failed: User not approved yet")


def admin_login():
    """Example: Admin login"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "identifier": "admin@example.com",  # Use your admin email
        "password": "admin123"  # Use your admin password
    }

    response = requests.post(url, json=data)
    print(f"Admin Login Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('temp_session_id')


def admin_verify_otp(temp_session_id, otp):
    """Example: Admin verify login OTP"""
    url = f"{BASE_URL}/auth/verify-otp"
    data = {"otp": otp}
    cookies = {"temp_session_id": temp_session_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Admin Verify OTP Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('auth_session_id')


def get_pending_users(admin_session_id):
    """Example: Admin get pending users"""
    url = f"{BASE_URL}/auth/admin/pending-users"
    cookies = {"auth_session_id": admin_session_id}

    response = requests.get(url, cookies=cookies)
    print(f"Pending Users Response: {response.status_code}")
    print(f"Body: {response.json()}")

    if response.status_code == 200:
        users = response.json()
        if users:
            return users[0]['id']  # Return first pending user ID
    return None


def approve_user(admin_session_id, user_id):
    """Example: Admin approve user"""
    url = f"{BASE_URL}/auth/admin/approve-user"
    data = {"user_id": user_id}
    cookies = {"auth_session_id": admin_session_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Approve User Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print("✅ User approved successfully!")


def login_user_after_approval():
    """Example: Login user after approval (should work)"""
    url = f"{BASE_URL}/auth/login"
    data = {
        "identifier": "user@example.com",
        "password": "mypassword123"
    }

    response = requests.post(url, json=data)
    print(f"Login After Approval Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('temp_session_id')


def verify_login_otp(temp_session_id, otp):
    """Example: Verify login OTP"""
    url = f"{BASE_URL}/auth/verify-otp"
    data = {"otp": otp}
    cookies = {"temp_session_id": temp_session_id}

    response = requests.post(url, json=data, cookies=cookies)
    print(f"Verify Login OTP Response: {response.status_code}")
    print(f"Body: {response.json()}")
    print(f"Cookies: {response.cookies}")

    return response.cookies.get('auth_session_id')


def get_all_users(admin_session_id):
    """Example: Admin get all users"""
    url = f"{BASE_URL}/auth/admin/all-users"
    cookies = {"auth_session_id": admin_session_id}

    response = requests.get(url, cookies=cookies)
    print(f"All Users Response: {response.status_code}")
    print(f"Body: {response.json()}")


def logout_user(auth_session_id):
    """Example: Logout user"""
    url = f"{BASE_URL}/auth/logout"
    cookies = {"auth_session_id": auth_session_id}

    response = requests.post(url, cookies=cookies)
    print(f"Logout Response: {response.status_code}")
    print(f"Body: {response.json()}")


def check_health():
    """Example: Check API health"""
    url = f"{BASE_URL}/health"
    response = requests.get(url)
    print(f"Health Check Response: {response.status_code}")
    print(f"Body: {response.json()}")


if __name__ == "__main__":
    print("=== Authentication API Examples with Admin Approval ===")

    # Check if API is running
    print("\n1. Checking API health...")
    check_health()

    # User registration flow
    print("\n2. User Registration Flow...")
    temp_reg_id = register_user()

    if temp_reg_id:
        print("📧 Check your email for OTP and enter it below:")
        otp = input("Enter OTP: ")
        verify_registration(temp_reg_id, otp)

    # Try to login before approval (should fail)
    print("\n3. Try to login before admin approval...")
    login_user_before_approval()

    # Admin workflow
    print("\n4. Admin Workflow...")
    print("🔑 Admin needs to login first")

    # Note: You need to create admin user first using create_admin.py
    admin_temp_session = admin_login()

    if admin_temp_session:
        print("📧 Check admin email for OTP and enter it below:")
        admin_otp = input("Enter Admin OTP: ")
        admin_session = admin_verify_otp(admin_temp_session, admin_otp)

        if admin_session:
            # Get pending users
            print("\n5. Getting pending users...")
            pending_user_id = get_pending_users(admin_session)

            if pending_user_id:
                # Approve user
                print("\n6. Approving user...")
                approve_user(admin_session, pending_user_id)

                # Now user can login
                print("\n7. User login after approval...")
                user_temp_session = login_user_after_approval()

                if user_temp_session:
                    print("📧 Check user email for OTP and enter it below:")
                    user_otp = input("Enter User OTP: ")
                    user_session = verify_login_otp(user_temp_session, user_otp)

                    if user_session:
                        print("✅ User logged in successfully!")

                        # Logout user
                        print("\n8. Logout user...")
                        logout_user(user_session)

                # Show all users
                print("\n9. Show all users...")
                get_all_users(admin_session)

                # Logout admin
                print("\n10. Logout admin...")
                logout_user(admin_session)
            else:
                print("No pending users found.")

    print("\n🎉 Demo completed!")
    print("\nNote: Make sure you have:")
    print("1. Created admin user using: python create_admin.py")
    print("2. Updated database schema using: python update_schema.py")
    print("3. Configured email settings in .env file")
