# Mobile Authentication System - Traffic Sign ML Pipeline

## Overview
This document explains how token-based authentication works for the mobile application. Unlike the web interface which uses Flask-Login sessions, the mobile app uses Bearer tokens for API authentication.

---

## 1. Mobile Authentication Flow (Token-Based)

### a. Mobile Login Process
1. Mobile app sends POST request to `/api/login` with email and password
2. Backend retrieves user from database using `User.get_by_email(email)`
3. Password is verified using `user.check_password(password)` (Werkzeug PBKDF2 hashing)
4. If valid, a new authentication token is generated and stored in database
5. Token and user information are returned to mobile app

### b. Token Generation & Storage
When authentication succeeds:
1. **Token Generation**:
   - Uses Python's `secrets.token_urlsafe(32)` for cryptographically secure random token
   - Generates 32-byte URL-safe string (Base64 encoded)
   - Example: `"AbCdEf123456GhIjKl789MnOpQrStUvWxYz"`

2. **Database Storage**:
   - Token is stored in `auth_tokens` table with:
     - `user_id`: Links token to user account
     - `token`: The actual token string (unique, indexed)
     - `created_at`: Token creation timestamp
     - `expires_at`: Expiration date (365 days from creation)

3. **Response to Mobile App**:
   ```json
   {
     "success": true,
     "token": "AbCdEf123456...",
     "user": {
       "id": 1,
       "name": "User Name",
       "email": "user@example.com",
       "organization_id": 1,
       "organization_name": "Organization Name",
       "is_admin": false
     }
   }
   ```

**Token Storage Table Structure:**
```sql
CREATE TABLE auth_tokens (
    id INTEGER PRIMARY KEY,
    user_id INTEGER NOT NULL,
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users (id)
)
```

---

## 2. Request Verification (Every Mobile API Request)

### a. Token Verification Process
On **every incoming mobile API request**, the backend:

1. **Reads the Authorization header**:
   ```
   Authorization: Bearer AbCdEf123456...
   ```

2. **Extracts the token**:
   - Splits header by space: `["Bearer", "token"]`
   - Takes second element (the actual token)

3. **Validates the token**:
   - Queries database: `SELECT * FROM auth_tokens WHERE token = ?`
   - ❌ If not found → Returns 401 Unauthorized
   - ✅ If found → Checks expiration date

4. **Checks token expiration**:
   ```python
   if token.expires_at < datetime.now():
       # Token expired
       return 401 Unauthorized
   ```

5. **Loads the user**:
   - Fetches user from database using `token.user_id`
   - Populates `g.current_user` with user object
   - Makes user available to route handler

6. **Executes the route function**:
   - User has been authenticated
   - Route can access `g.current_user` for user information
   - Route can check organization membership for data isolation

### b. Security Benefits
- **Stateless**: No server-side session storage needed
- **Scalable**: Works across multiple Gunicorn workers
- **Long-lived**: 365-day validity reduces login frequency
- **Revocable**: Tokens can be deleted from database (logout)
- **Organization isolation**: Each user only sees their organization's data

---

## 3. Token Decorator (@token_required)

### Purpose
The `@token_required` decorator protects mobile API routes by verifying the Bearer token on every request.

### Implementation
```python
# In decorators/auth_decorators.py
from functools import wraps
from flask import request, jsonify, g
from models.auth_token import AuthToken
from models.user import User

def token_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Extract token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Authorization header missing'}), 401
        
        token = auth_header.split(' ')[1]
        
        # 2. Validate token in database
        token_obj = AuthToken.get_by_token(token)
        if not token_obj:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # 3. Load user and store in Flask's g object
        user = User.get_by_id(token_obj.user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 401
        
        g.current_user = user
        
        # 4. Execute the protected route
        return f(*args, **kwargs)
    
    return decorated_function
```

### Usage in Routes
```python
from decorators.auth_decorators import token_required

@api_bp.route('/protected-endpoint', methods=['POST'])
@token_required
def protected_endpoint():
    # User is authenticated, access via g.current_user
    user = g.current_user
    return jsonify({
        'message': f'Hello {user.name}',
        'organization': user.organization.name
    })
```

---

## 4. Hybrid Authentication (@auth_required)

### Purpose
The `@auth_required` decorator allows routes to accept **both** web sessions (Flask-Login) and mobile tokens. This enables code reuse for endpoints like `/upload` and `/extract_status`.

### Implementation
```python
def auth_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Try Flask-Login session first (web)
        if current_user.is_authenticated:
            return f(*args, **kwargs)
        
        # Try Bearer token (mobile)
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            token_obj = AuthToken.get_by_token(token)
            if token_obj:
                user = User.get_by_id(token_obj.user_id)
                if user:
                    g.current_user = user
                    return f(*args, **kwargs)
        
        # Neither authentication method worked
        if request.is_json:
            return jsonify({'error': 'Authentication required'}), 401
        else:
            return redirect(url_for('auth.login'))
    
    return decorated_function
```

### Usage
```python
@upload_bp.route('/upload', methods=['POST'])
@auth_required
def upload_recording():
    # Works for both web and mobile
    # Web: uses current_user (Flask-Login)
    # Mobile: uses g.current_user (token)
    user = current_user if current_user.is_authenticated else g.current_user
    
    # Process upload...
    return jsonify({'job_id': job_id})
```

---

## 5. Mobile API Endpoints

### Login
```
POST /api/login
Content-Type: application/json

Body:
{
  "email": "user@example.com",
  "password": "password123"
}

Response (200):
{
  "success": true,
  "token": "AbCdEf123456...",
  "user": {
    "id": 1,
    "name": "User Name",
    "email": "user@example.com",
    "organization_id": 1,
    "organization_name": "Organization Name",
    "is_admin": false
  }
}

Response (401):
{
  "error": "Invalid email or password"
}
```

### Logout
```
POST /api/logout
Authorization: Bearer <token>

Response (200):
{
  "success": true,
  "message": "Logged out successfully"
}

Response (401):
{
  "error": "Authorization header missing"
}
```

---

## 6. Token Management (AuthToken Model)

### Database Methods

**Create Token**:
```python
# Create new token for user (default 365 days)
token = AuthToken.create(user_id=1, expires_days=365)
# Returns: "AbCdEf123456..."
```

**Get Token**:
```python
# Retrieve token from database
token_obj = AuthToken.get_by_token("AbCdEf123456...")
# Returns: AuthToken object or None if expired/invalid
```

**Delete Token (Logout)**:
```python
# Delete single token
AuthToken.delete("AbCdEf123456...")

# Delete all tokens for a user
AuthToken.delete_all_for_user(user_id=1)
```

### Token Expiration Check
```python
class AuthToken:
    @staticmethod
    def get_by_token(token):
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, user_id, token, created_at, expires_at
            FROM auth_tokens
            WHERE token = ? AND expires_at > datetime('now')
        ''', (token,))
        row = cursor.fetchone()
        
        if not row:
            return None  # Token not found or expired
        
        return AuthToken(*row)
```

---

## 7. Security Considerations

### Token Security
- **Length**: 32 bytes provides 2^256 possible tokens (cryptographically secure)
- **Randomness**: `secrets.token_urlsafe()` uses OS-provided randomness
- **Storage**: Tokens stored in plain text in database (like API keys)
- **Transmission**: Always use HTTPS to prevent token interception

### Best Practices
1. **Never log tokens**: Don't print tokens in logs or error messages
2. **HTTPS only**: Enforce HTTPS in production to protect tokens in transit
3. **Token rotation**: Allow users to logout and regenerate tokens
4. **Expiration**: 365-day expiration forces periodic re-authentication
5. **Revocation**: Implement logout to invalidate compromised tokens

### Limitations
- **No refresh tokens**: Users must re-login after 365 days
- **No rate limiting**: Currently no protection against brute force
- **No token metadata**: Cannot track last used, IP address, device info



