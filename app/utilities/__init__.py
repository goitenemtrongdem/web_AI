# Utils package for Wind Turbine Management System

# Import utility functions from utils.py module
import importlib.util
import os

# Load utils.py module directly to avoid circular import
utils_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'utils.py')
spec = importlib.util.spec_from_file_location("utils_module", utils_path)
utils_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(utils_module)

# Re-export all functions from utils module
hash_password = utils_module.hash_password
verify_password = utils_module.verify_password
generate_otp = utils_module.generate_otp
is_email = utils_module.is_email
is_phone = utils_module.is_phone
get_otp_expiry = utils_module.get_otp_expiry
get_session_expiry = utils_module.get_session_expiry
get_auth_session_expiry = utils_module.get_auth_session_expiry
is_expired = utils_module.is_expired
create_access_token = utils_module.create_access_token
verify_token = utils_module.verify_token
generate_session_token = utils_module.generate_session_token

# For backward compatibility, support wildcard import
__all__ = [
    'hash_password',
    'verify_password', 
    'generate_otp',
    'is_email',
    'is_phone',
    'get_otp_expiry',
    'get_session_expiry',
    'get_auth_session_expiry',
    'is_expired',
    'create_access_token',
    'verify_token',
    'generate_session_token'
]
