# Authentication System - Traffic Sign ML Pipeline

## Overview
This document explains how authentication works in the Traffic Sign ML Pipeline application using Flask-Login. It covers session management, user verification, access control, and the main functions and decorators used throughout the application.

---

## 1. Authentication Flow

### a. User Login Process
1. User submits email and password via login form
2. Backend retrieves user from database using `User.get_by_email(email)`
3. Password is verified using `user.check_password(password)` (Werkzeug PBKDF2 hashing)
4. If valid, `login_user(user, remember=True/False)` is called

### b. Session Creation & Cookie Signing
When `login_user()` is called, Flask-Login:
1. **Serializes user data** into a JSON object containing:
   - User ID
   - Authentication status
   - Session metadata
   - Remember me flag

2. **Signs the session cookie** using the `SECRET_KEY`:
   - Takes the JSON data as plain text
   - Performs a cryptographic calculation using HMAC with the `SECRET_KEY`
   - Appends the signature (hash result) to the cookie
   - The signature acts as a tamper-proof seal

3. **Sends the signed cookie** to the browser:
   - Cookie name: `session`
   - Contains: `{user_data}.{signature}`
   - HTTPOnly flag prevents JavaScript access
   - Secure flag for HTTPS (production)

**Example Cookie Structure:**
```
session=eyJ1c2VyX2lkIjoiMSJ9.YzBkZjM4.signature_hash_here
         ↑ base64 user data  ↑ timestamp ↑ HMAC signature
```

---

## 2. Request Verification (Every Request)

### a. Cookie Verification Process
On **every incoming request**, Flask automatically:

1. **Reads the session cookie** from the request headers
2. **Extracts the signature** from the cookie
3. **Recalculates the signature**:
   - Takes the user data portion
   - Performs the same HMAC calculation with `SECRET_KEY`
   - Compares the result with the signature in the cookie

4. **Validates the signature**:
   - ✅ If signatures match → Cookie is authentic and unmodified
   - ❌ If signatures don't match → Cookie was tampered with, session is invalid

5. **Populates `current_user` object**:
   - If signature is valid, Flask-Login calls `user_loader` callback
   - `user_loader` fetches the user from database using the user_id
   - Populates `current_user` with user attributes:
     - `current_user.is_authenticated` → `True`
     - `current_user.is_admin` → User's admin status
     - `current_user.name` → User's name
     - `current_user.organization` → User's organization

6. **Makes `current_user` available**:
   - Accessible in all route functions
   - Accessible in all Jinja2 templates
   - Fresh data on every request (refetched from DB)

### b. Security Benefits
- **Tamper-proof**: Modifying cookie data invalidates the signature
- **Secret key protection**: Signature cannot be forged without `SECRET_KEY`
- **Session hijacking prevention**: HTTPOnly flag prevents XSS attacks
- **Automatic expiration**: Sessions expire based on configuration

---

## 3. User Loader Callback

### Purpose
The `user_loader` callback is the bridge between Flask-Login and your database. It's called on every request to load the user object.

### Implementation
```python
# In app.py
from flask_login import LoginManager

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    """Load user by ID for Flask-Login"""
    return User.get_by_id(int(user_id))
```

### How It Works
1. Flask-Login extracts `user_id` from the validated session cookie
2. Calls `load_user(user_id)` to fetch the full user object
3. Returns the user object (or `None` if not found)
4. Stores the user in `current_user` for the duration of the request

---

## 4. Access Control Decorators

### a. `@login_required` - Protect Routes from Anonymous Access

**Location**: `decorators/auth_decorators.py`

**Purpose**: Ensures only authenticated users can access a route

**Implementation**:
```python
from functools import wraps
from flask import redirect, url_for, flash
from flask_login import current_user

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function
```

**How It Works**:
1. Checks `current_user.is_authenticated`
2. If `False` → Redirects to login page with warning message
3. If `True` → Allows the route function to execute

**Usage Example**:
```python
from decorators.auth_decorators import login_required

@app.route('/upload')
@login_required
def upload():
    # Only authenticated users can reach here
    return render_template('upload.html')
```

**Applied To**:
- All upload routes (`/upload`)
- All status routes (`/status`, `/recordings`)
- All download routes (`/download/<recording_id>`)
- All delete/rerun routes

---

### b. `@admin_required` - Restrict to Admin Users Only

**Location**: `decorators/auth_decorators.py`

**Purpose**: Ensures only admin users can access admin panel and privileged actions

**Implementation**:
```python
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for('auth.login'))
        
        if not current_user.is_admin:
            flash("You need admin privileges to access this page.", "danger")
            return redirect(url_for('status.list_recordings'))
        
        return f(*args, **kwargs)
    return decorated_function
```

**How It Works**:
1. First checks if user is authenticated (like `@login_required`)
2. Then checks `current_user.is_admin`
3. If not admin → Redirects to recordings page with error message
4. If admin → Allows the route function to execute

**Usage Example**:
```python
from decorators.auth_decorators import admin_required

@app.route('/admin/users/new')
@admin_required
def create_user():
    # Only admins can reach here
    return render_template('admin/user_form.html')
```

**Applied To**:
- Admin dashboard (`/admin/`)
- Organization management (`/admin/organizations/*`)
- User management (`/admin/users/*`)
- Toggle admin status (`/admin/users/<id>/toggle-admin`)

---

## 5. Key Functions & Services

### a. User Model Functions

**Location**: `models/user.py`

#### `User.create(email, password, name, organization_id, is_admin=False)`
Creates a new user with hashed password
```python
user = User.create(
    email="user@example.com",
    password="SecurePass123!",
    name="John Doe",
    organization_id=1,
    is_admin=False
)
```

#### `User.get_by_email(email)`
Retrieves user by email address (used during login)
```python
user = User.get_by_email("user@example.com")
```

#### `User.get_by_id(user_id)`
Retrieves user by ID (used by `user_loader`)
```python
user = User.get_by_id(1)
```

#### `user.check_password(password)`
Verifies password against stored hash
```python
if user.check_password("user_password"):
    # Password is correct
    login_user(user)
```

#### `user.update_password(new_password)`
Updates user password with new hash
```python
user.update_password("NewSecurePass123!")
```

#### `user.update_admin_status(is_admin)`
Toggles admin privileges for a user
```python
user.update_admin_status(True)  # Make admin
user.update_admin_status(False) # Remove admin
```

---

### b. Authentication Routes

**Location**: `routes/auth_routes.py`

#### `POST /login` - User Login
```python
@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        remember = request.form.get("remember", False)
        
        user = User.get_by_email(email)
        if user and user.check_password(password):
            login_user(user, remember=bool(remember))
            return redirect(url_for('status.list_recordings'))
        else:
            flash("Invalid email or password.", "danger")
    
    return render_template("login.html")
```

**Flow**:
1. Validates email and password
2. Fetches user from database
3. Verifies password hash
4. Calls `login_user()` to create session
5. Redirects to recordings page

#### `GET /logout` - User Logout
```python
@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
```

**Flow**:
1. Calls `logout_user()` to destroy session
2. Clears the session cookie
3. Redirects to login page

---

### c. Organization Service (Multi-Tenancy)

**Location**: `services/organization_service.py`

#### `get_recordings_for_organization(organization_id)`
Returns all recordings belonging to an organization
```python
recordings = OrganizationService.get_recordings_for_organization(
    current_user.organization_id
)
```

#### `can_access_recording(user, recording_id)`
Checks if user has permission to access a recording
```python
if OrganizationService.can_access_recording(current_user, recording_id):
    # User can access this recording
    return download_file(recording_id)
else:
    # Access denied
    abort(403)
```

**Used In**:
- Download routes (verify ownership)
- Delete routes (verify ownership)
- Rerun routes (verify ownership)
- Status display (filter recordings)

#### `register_recording(recording_id, organization_id)`
Associates a recording with an organization during upload
```python
OrganizationService.register_recording(
    recording_id=recording_id,
    organization_id=current_user.organization_id
)
```

---

## 6. Multi-Tenancy & Data Isolation

### How It Works
1. **Every recording is linked to an organization**
2. **Every user belongs to one organization**
3. **Access control checks organization membership**:
   - Users can only see their organization's recordings
   - Users cannot access other organizations' data
   - Admins see all data (if needed) but actions are org-scoped

### Access Control Example
```python
@login_required
def download_recording(recording_id):
    # Verify user owns this recording
    if not OrganizationService.can_access_recording(current_user, recording_id):
        flash("Access denied: Recording not found or not accessible.", "danger")
        return redirect(url_for('status.list_recordings'))
    
    # User has access, proceed with download
    return send_file(...)
```

---

## 7. Security Best Practices

### Secret Key Management
- **Never commit `SECRET_KEY` to version control**
- Store in `.env` file (excluded in `.gitignore`)
- Use a strong random string (minimum 32 characters)

### Password Security
- Passwords are hashed using Werkzeug's `generate_password_hash()` with PBKDF2-SHA256
- Salt is automatically generated and stored with hash
- Never store plain text passwords

### Session Security
- **HTTPOnly cookies**: Prevents JavaScript access (XSS protection)
- **Secure flag in production**: Only sent over HTTPS
- **Remember me option**: Longer session for trusted devices

---

## 8. Configuration

### Flask-Login Setup
```python
from flask_login import LoginManager

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

@login_manager.user_loader
def load_user(user_id):
    return User.get_by_id(int(user_id))
```

### Secret Key Configuration
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-key-change-in-production')
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
```

---

## 9. Common Issues & Troubleshooting

### Issue: "Please log in to access this page" on every request
**Cause**: Invalid or missing `SECRET_KEY`
**Solution**: Check `.env` file has `SECRET_KEY` defined and restart Flask app

### Issue: Users logged out after server restart
**Cause**: `SECRET_KEY` changed or session expired
**Solution**: Keep `SECRET_KEY` consistent across restarts

### Issue: Cannot access admin panel
**Cause**: User's `is_admin` flag is `False`
**Solution**: Toggle admin status using `user.update_admin_status(True)`

### Issue: "Access denied" for own recordings
**Cause**: Recording not associated with user's organization
**Solution**: Re-upload recording or manually fix organization association in database

---

## 10. References

- **Flask-Login Documentation**: https://flask-login.readthedocs.io/
- **Werkzeug Security**: https://werkzeug.palletsprojects.com/en/latest/utils/#module-werkzeug.security
- **Session Management**: https://flask.palletsprojects.com/en/latest/quickstart/#sessions

### Related Files
- `app.py` - Flask-Login initialization
- `models/user.py` - User model and authentication methods
- `routes/auth_routes.py` - Login/logout routes
- `routes/admin_routes.py` - Admin panel routes
- `decorators/auth_decorators.py` - Access control decorators
- `services/organization_service.py` - Multi-tenancy logic
- `config.py` - Security configuration
