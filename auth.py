import hashlib
from typing import Optional, Tuple

import streamlit as st

import database


SECURITY_QUESTIONS = [
    "What is your favorite color?",
    "What is your first school name?",
    "What is your pet name?",
    "What is your birthplace?",
]


def hash_text(raw_text: str) -> str:
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def init_session_state() -> None:
    st.session_state.setdefault("authenticated", False)
    st.session_state.setdefault("user_id", None)
    st.session_state.setdefault("user_email", "")
    st.session_state.setdefault("auth_view", "login")
    st.session_state.setdefault("role", "")


def logout() -> None:
    st.session_state["authenticated"] = False
    st.session_state["user_id"] = None
    st.session_state["user_email"] = ""
    st.session_state["role"] = ""
    st.session_state["auth_view"] = "login"


def sync_role_from_db_if_needed() -> None:
    """Populate session role after deploy/migration when older sessions lacked it."""
    if not st.session_state.get("authenticated"):
        return
    if st.session_state.get("role"):
        return
    email = (st.session_state.get("user_email") or "").strip()
    if not email:
        return
    row = database.get_user_by_email(email)
    if not row:
        st.session_state["role"] = database.DEFAULT_USER_ROLE
        return
    try:
        raw = row["role"]
    except (IndexError, KeyError):
        raw = None
    st.session_state["role"] = database.normalize_user_role(raw)


def login_user(email: str, password: str) -> Tuple[bool, str]:
    user = database.get_user_by_email(email)
    if not user:
        return False, "Please sign up first"
    if user["password"] != hash_text(password):
        return False, "Invalid password"
    st.session_state["authenticated"] = True
    st.session_state["user_id"] = int(user["id"])
    st.session_state["user_email"] = user["email"]
    try:
        stored_role = user["role"]
    except (IndexError, KeyError):
        stored_role = None
    st.session_state["role"] = database.normalize_user_role(stored_role)
    return True, "Login successful"


def signup_user(
    email: str,
    password: str,
    mobile: str,
    security_question: str,
    security_answer: str,
) -> Tuple[bool, str]:
    return database.create_user(
        email=email,
        password_hash=hash_text(password),
        mobile=mobile,
        security_question=security_question,
        security_answer_hash=hash_text(security_answer.strip().lower()),
    )


def validate_security_answer(email: str, answer: str) -> bool:
    user = database.get_user_by_email(email)
    if not user:
        return False
    return user["security_answer"] == hash_text(answer.strip().lower())


def reset_password(email: str, new_password: str) -> None:
    database.update_user_password(email, hash_text(new_password))


def render_auth_ui() -> bool:
    init_session_state()

    st.markdown(
        """
        <style>
            .main .block-container {
                padding-top: 1.2rem;
                padding-bottom: 1.2rem;
            }
            div[data-testid="stVerticalBlock"] > div:empty {
                display: none;
            }
            div[data-testid="stMarkdownContainer"] p {
                margin-bottom: 0;
            }
            .auth-wrap {
                max-width: 720px;
                margin: 0 auto 1rem auto;
                text-align: center;
            }
            .auth-title {
                text-align: center;
                font-size: 44px;
                font-weight: 700;
                color: #f7f9ff;
                margin-bottom: 0.35rem;
                letter-spacing: 0.4px;
                text-shadow: 0 8px 30px rgba(99, 102, 241, 0.35);
            }
            .auth-sub {
                text-align: center;
                color: #cfd8ff;
                margin-bottom: 1.5rem;
                font-size: 15px;
                font-weight: 400;
            }
            div[data-testid="stVerticalBlockBorderWrapper"] {
                border: 1px solid rgba(255, 255, 255, 0.22) !important;
                border-radius: 18px !important;
                background: rgba(255, 255, 255, 0.09) !important;
                box-shadow: 0 14px 40px rgba(0, 0, 0, 0.25) !important;
                backdrop-filter: blur(14px) !important;
            }
            [data-baseweb="input"] > div,
            [data-baseweb="select"] > div,
            [data-baseweb="base-input"] > div {
                border-radius: 12px !important;
                border: 1px solid rgba(255, 255, 255, 0.24) !important;
                background: rgba(255, 255, 255, 0.08) !important;
            }
            .stButton > button {
                border-radius: 12px !important;
                font-weight: 600 !important;
            }
        </style>
        <div class="auth-wrap">
            <div class="auth-title">🚗 Car Price Prediction 🚗</div>
            <div class="auth-sub">Secure login and smart resale valuation</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.session_state["authenticated"]:
        return True

    left, center, right = st.columns([1, 1.6, 1])
    with center:
        with st.container(border=True):
            current_view = st.session_state.get("auth_view", "login")

            if current_view == "login":
                st.subheader("👤 Login")
                email = st.text_input(" 📫  Email / Username", key="login_email")
                password = st.text_input("🔑 Password", type="password", key="login_password")

                c1, c2, c3 = st.columns(3)
                if c1.button("Login", use_container_width=True):
                    if not email or not password:
                        st.error("Please enter email and password")
                    else:
                        with st.spinner("Authenticating..."):
                            ok, message = login_user(email, password)
                        if ok:
                            st.success(message)
                            st.rerun()
                        else:
                            st.error(message)

                if c2.button("Sign Up", use_container_width=True):
                    st.session_state["auth_view"] = "signup"
                    st.rerun()

                if c3.button("Forgot Password", use_container_width=True):
                    st.session_state["auth_view"] = "forgot"
                    st.rerun()

            elif current_view == "signup":
                st.subheader("Sign Up")
                email = st.text_input("Email", key="signup_email")
                password = st.text_input("Password", type="password", key="signup_password")
                mobile = st.text_input("Mobile Number", key="signup_mobile")
                security_question = st.selectbox("Security Question", SECURITY_QUESTIONS, key="signup_q")
                security_answer = st.text_input("Security Answer", key="signup_a")

                c1, c2 = st.columns(2)
                if c1.button("Create Account", use_container_width=True):
                    if not all([email, password, mobile, security_question, security_answer]):
                        st.error("Please fill all fields")
                    else:
                        with st.spinner("Creating account..."):
                            ok, message = signup_user(
                                email=email,
                                password=password,
                                mobile=mobile,
                                security_question=security_question,
                                security_answer=security_answer,
                            )
                        if ok:
                            st.success("Account created successfully")
                            st.session_state["auth_view"] = "login"
                            st.rerun()
                        else:
                            st.error(message)
                if c2.button("Back to Login", use_container_width=True):
                    st.session_state["auth_view"] = "login"
                    st.rerun()

            else:
                st.subheader("Forgot Password")
                email = st.text_input("Enter Email", key="fp_email")
                user = database.get_user_by_email(email) if email else None
                if email and user:
                    st.info(f"Security Question: {user['security_question']}")
                    answer = st.text_input("Security Answer", key="fp_answer")
                    new_password = st.text_input("New Password", type="password", key="fp_new_password")

                    c1, c2 = st.columns(2)
                    if c1.button("Reset Password", use_container_width=True):
                        if not answer or not new_password:
                            st.error("Please enter answer and new password")
                        elif not validate_security_answer(email, answer):
                            st.error("Security answer is incorrect")
                        else:
                            with st.spinner("Resetting password..."):
                                reset_password(email, new_password)
                            st.success("Password reset successfully")
                            st.session_state["auth_view"] = "login"
                            st.rerun()
                    if c2.button("Back to Login", use_container_width=True):
                        st.session_state["auth_view"] = "login"
                        st.rerun()
                elif email:
                    st.error("Please sign up first")
                    if st.button("Go to Sign Up", use_container_width=True):
                        st.session_state["auth_view"] = "signup"
                        st.rerun()
                else:
                    if st.button("Back to Login", use_container_width=True):
                        st.session_state["auth_view"] = "login"
                        st.rerun()

    return False
