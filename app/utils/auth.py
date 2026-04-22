from flask import current_app, make_response, redirect, request, session, url_for
from flask_jwt_extended import create_access_token, decode_token, set_access_cookies, unset_jwt_cookies


AUTH_SESSION_KEYS = (
    "user_id",
    "user_name",
    "email",
    "user_email",
    "role",
    "worker_id",
    "district_id",
    "taluka_id",
)

PUBLIC_PATHS = {
    "/",
    "/about",
    "/services",
    "/portal-selection",
    "/health",
    "/auth/login",
    "/auth/logout",
    "/auth/register",
    "/auth/get_talukas",
    "/auth/get_villages",
    "/user/login",
    "/user/logout",
}

PROTECTED_PREFIXES = (
    "/auth/citizen",
    "/auth/worker",
    "/auth/district-dashboard",
    "/auth/taluka-dashboard",
    "/auth/api/worker",
    "/user/",
)


def build_auth_payload(user, role):
    name = user.get("name") or user.get("full_name") or "User"
    email = user.get("email")
    payload = {
        "user_id": int(user["id"]),
        "user_name": name,
        "email": email,
        "user_email": email,
        "role": role,
    }

    district_id = user.get("district_id")
    taluka_id = user.get("taluka_id")

    if district_id is not None:
        payload["district_id"] = int(district_id)
    if taluka_id is not None:
        payload["taluka_id"] = int(taluka_id)
    if role == "worker":
        payload["worker_id"] = int(user["id"])

    return payload


def clear_auth_session():
    for key in AUTH_SESSION_KEYS:
        session.pop(key, None)


def store_auth_session(payload, clear_existing=False):
    if clear_existing:
        clear_auth_session()

    for key in AUTH_SESSION_KEYS:
        if key in payload and payload[key] is not None:
            session[key] = payload[key]
        elif clear_existing:
            session.pop(key, None)

    session.permanent = True


def role_dashboard_endpoint(role):
    return {
        "district_admin": "auth_bp.district_dashboard",
        "admin": "auth_bp.taluka_dashboard",
        "worker": "auth_bp.worker_dashboard",
        "user": "auth_bp.citizen_dashboard",
    }.get(role, "auth_bp.login")


def _access_cookie_name():
    return current_app.config.get("JWT_ACCESS_COOKIE_NAME", "access_token_cookie")


def get_auth_claims_from_request():
    token = request.cookies.get(_access_cookie_name())
    if not token:
        return None

    try:
        decoded = decode_token(token, allow_expired=False)
    except Exception:
        return None

    claims = {
        "user_id": int(decoded["sub"]),
        "user_name": decoded.get("user_name"),
        "email": decoded.get("email"),
        "user_email": decoded.get("user_email") or decoded.get("email"),
        "role": decoded.get("role"),
        "worker_id": decoded.get("worker_id"),
        "district_id": decoded.get("district_id"),
        "taluka_id": decoded.get("taluka_id"),
    }
    return {key: value for key, value in claims.items() if value is not None}


def sync_session_from_jwt():
    claims = get_auth_claims_from_request()
    if claims:
        store_auth_session(claims, clear_existing=True)
        return claims

    clear_auth_session()
    return None


def make_login_response(target, payload, use_url=False):
    flashes = session.get("_flashes", [])
    session.clear()
    if flashes:
        session["_flashes"] = flashes

    store_auth_session(payload, clear_existing=False)

    claims = {key: value for key, value in payload.items() if key != "user_id" and value is not None}
    access_token = create_access_token(identity=str(payload["user_id"]), additional_claims=claims)

    response = make_response(redirect(target if use_url else url_for(target)))
    set_access_cookies(response, access_token)
    return response


def make_logout_response(target="auth_bp.login", use_url=False):
    flashes = session.get("_flashes", [])
    session.clear()
    if flashes:
        session["_flashes"] = flashes

    response = make_response(redirect(target if use_url else url_for(target)))
    unset_jwt_cookies(response)
    response.headers["Clear-Site-Data"] = "\"cache\", \"cookies\", \"storage\""
    return response


def is_protected_path(path):
    if not path or path.startswith("/static") or path in PUBLIC_PATHS:
        return False
    if path == "/dashboard":
        return True
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def should_disable_cache(path):
    if not path or path.startswith("/static"):
        return False
    return path == "/dashboard" or path.startswith("/auth") or path.startswith("/user")
