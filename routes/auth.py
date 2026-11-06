from flask import (
    Blueprint,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from services.auth import verify_credential

bp = Blueprint("auth", __name__)


def _get_client_ip() -> str:
    # With ProxyFix middleware enabled, request.remote_addr is guaranteed to be
    # the client IP from the trusted reverse proxy (X-Forwarded-For).
    return request.remote_addr or "127.0.0.1"


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("is_authenticated"):
        return redirect(url_for("dashboard.index"))

    error = None
    if request.method == "POST":
        # Accept both 'password' and legacy 'pin' form fields
        secret = (
            request.form.get("password")
            or request.form.get("pin")
            or ""
        ).strip()
        client_ip = _get_client_ip()

        success, err_msg = verify_credential(secret, client_ip)
        if success:
            session.permanent = True
            session["is_authenticated"] = True
            next_url = request.args.get("next")
            # Protect against open redirect attacks
            if not next_url or not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("dashboard.index")
            return redirect(next_url)
        error = err_msg

    return render_template("login.html", error=error)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
