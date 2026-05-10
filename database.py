import json
import os
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


DB_PATH = "car_prediction.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    return conn


def _execute_write_with_retry(query: str, params: Tuple[Any, ...] = ()) -> None:
    last_error: Optional[Exception] = None
    for _ in range(3):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(query, params)
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.5)
    if last_error:
        raise last_error


def init_db() -> None:
    with get_connection() as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        cur = conn.cursor()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                mobile TEXT NOT NULL,
                security_question TEXT NOT NULL,
                security_answer TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prediction_id TEXT,
                user_id INTEGER NOT NULL,
                input_data TEXT NOT NULL,
                predicted_price REAL NOT NULL,
                recommended_price REAL NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )
        cur.execute("PRAGMA table_info(predictions)")
        prediction_columns = {row["name"] for row in cur.fetchall()}
        if "prediction_id" not in prediction_columns:
            cur.execute("ALTER TABLE predictions ADD COLUMN prediction_id TEXT")
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_predictions_prediction_id ON predictions(prediction_id)"
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                report_path TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS email_history (
                email_id TEXT PRIMARY KEY,
                prediction_id TEXT,
                recipient_email TEXT NOT NULL,
                sent_at TEXT NOT NULL,
                status TEXT NOT NULL,
                delivery_status TEXT NOT NULL
            )
            """
        )

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS report_access_history (
                access_id TEXT PRIMARY KEY,
                prediction_id TEXT,
                qr_id TEXT,
                qr_url TEXT,
                access_type TEXT,
                access_status TEXT,
                opened_at TIMESTAMP
            )
            """
        )
        cur.execute("PRAGMA table_info(report_access_history)")
        report_access_columns = {row["name"] for row in cur.fetchall()}
        if "qr_url" not in report_access_columns:
            cur.execute("ALTER TABLE report_access_history ADD COLUMN qr_url TEXT")


def create_user(
    email: str,
    password_hash: str,
    mobile: str,
    security_question: str,
    security_answer_hash: str,
) -> Tuple[bool, str]:
    try:
        _execute_write_with_retry(
            """
            INSERT INTO users (email, password, mobile, security_question, security_answer)
            VALUES (?, ?, ?, ?, ?)
            """,
            (email.strip().lower(), password_hash, mobile.strip(), security_question, security_answer_hash),
        )
        return True, "Account created successfully"
    except sqlite3.IntegrityError:
        return False, "User already exists. Please login."


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
        return cur.fetchone()


def update_user_password(email: str, new_password_hash: str) -> None:
    _execute_write_with_retry(
        "UPDATE users SET password = ? WHERE email = ?",
        (new_password_hash, email.strip().lower()),
    )


def generate_prediction_id() -> str:
    # 10-char public ID provides enough entropy while staying user-friendly.
    return uuid.uuid4().hex[:10].upper()


def _save_prediction_record(
    user_id: int,
    input_data: Dict[str, Any],
    predicted_price: float,
    recommended_price: float,
    prediction_id: Optional[str] = None,
) -> Tuple[int, str]:
    public_prediction_id = prediction_id or generate_prediction_id()
    for _ in range(3):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                while True:
                    cur.execute(
                        "SELECT 1 FROM predictions WHERE prediction_id = ?",
                        (public_prediction_id,),
                    )
                    if not cur.fetchone():
                        break
                    public_prediction_id = generate_prediction_id()

                cur.execute(
                    """
                    INSERT INTO predictions (prediction_id, user_id, input_data, predicted_price, recommended_price, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        public_prediction_id,
                        user_id,
                        json.dumps(input_data),
                        float(predicted_price),
                        float(recommended_price),
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                prediction_row_id = cur.lastrowid
            return int(prediction_row_id), public_prediction_id
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.5)
    raise sqlite3.OperationalError("database is locked")


def save_prediction(
    user_id: int,
    input_data: Dict[str, Any],
    predicted_price: float,
    recommended_price: float,
) -> int:
    prediction_row_id, _ = _save_prediction_record(
        user_id=user_id,
        input_data=input_data,
        predicted_price=predicted_price,
        recommended_price=recommended_price,
    )
    return prediction_row_id


def save_prediction_with_public_id(
    user_id: int,
    input_data: Dict[str, Any],
    predicted_price: float,
    recommended_price: float,
) -> Tuple[int, str]:
    return _save_prediction_record(
        user_id=user_id,
        input_data=input_data,
        predicted_price=predicted_price,
        recommended_price=recommended_price,
    )


def save_report(user_id: int, report_path: str) -> None:
    _execute_write_with_retry(
        """
        INSERT INTO reports (user_id, report_path, timestamp)
        VALUES (?, ?, ?)
        """,
        (user_id, report_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
    )


def get_user_predictions(user_id: int) -> List[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM predictions WHERE user_id = ? ORDER BY id DESC",
            (user_id,),
        )
        return cur.fetchall()


def get_prediction_by_public_id(prediction_id: str, user_id: Optional[int] = None) -> Optional[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                "SELECT * FROM predictions WHERE prediction_id = ? LIMIT 1",
                (prediction_id.strip().upper(),),
            )
        else:
            cur.execute(
                "SELECT * FROM predictions WHERE prediction_id = ? AND user_id = ? LIMIT 1",
                (prediction_id.strip().upper(), user_id),
            )
        return cur.fetchone()


def get_dashboard_counts() -> Dict[str, int]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) AS total FROM users")
        total_users = int(cur.fetchone()["total"])
        cur.execute("SELECT COUNT(*) AS total FROM predictions")
        total_predictions = int(cur.fetchone()["total"])
        cur.execute("SELECT COUNT(*) AS total FROM reports")
        total_reports = int(cur.fetchone()["total"])
    return {
        "total_users": total_users,
        "total_predictions": total_predictions,
        "total_reports": total_reports,
    }


def ensure_reports_dir() -> str:
    path = "reports"
    os.makedirs(path, exist_ok=True)
    return path


def save_email_history(
    email_id: str,
    prediction_id: str,
    recipient_email: str,
    status: str,
    delivery_status: str,
) -> None:
    payload = (
        email_id,
        (prediction_id or "").strip().upper(),
        (recipient_email or "").strip(),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status.strip().upper(),
        delivery_status.strip().upper(),
    )
    last_error: Optional[Exception] = None
    for _ in range(3):
        try:
            with get_connection() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO email_history (email_id, prediction_id, recipient_email, sent_at, status, delivery_status)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
            return
        except sqlite3.OperationalError as exc:
            last_error = exc
            if "locked" not in str(exc).lower():
                raise
            time.sleep(0.5)
    if last_error:
        raise last_error


def get_email_history_for_user(user_id: int, user_email: Optional[str] = None) -> List[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        normalized_email = (user_email or "").strip().lower()
        if normalized_email:
            cur.execute(
                """
                SELECT eh.email_id, eh.prediction_id, eh.recipient_email, eh.sent_at, eh.status, eh.delivery_status
                FROM email_history eh
                LEFT JOIN predictions p ON p.prediction_id = eh.prediction_id
                WHERE p.user_id = ? OR LOWER(eh.recipient_email) = ?
                ORDER BY eh.sent_at DESC
                """,
                (user_id, normalized_email),
            )
        else:
            cur.execute(
                """
                SELECT eh.email_id, eh.prediction_id, eh.recipient_email, eh.sent_at, eh.status, eh.delivery_status
                FROM email_history eh
                LEFT JOIN predictions p ON p.prediction_id = eh.prediction_id
                WHERE p.user_id = ?
                ORDER BY eh.sent_at DESC
                """,
                (user_id,),
            )
        return cur.fetchall()


def save_report_access_event(
    prediction_id: str,
    qr_id: str,
    qr_url: str,
    access_type: str,
    access_status: str,
    access_id: Optional[str] = None,
) -> str:
    normalized_prediction_id = (prediction_id or "").strip().upper()
    payload_access_id = access_id or str(uuid.uuid4())[:10]
    payload = (
        payload_access_id,
        normalized_prediction_id,
        (qr_id or "").strip(),
        (qr_url or "").strip(),
        (access_type or "").strip().upper(),
        (access_status or "").strip().upper(),
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    _execute_write_with_retry(
        """
        INSERT INTO report_access_history (access_id, prediction_id, qr_id, qr_url, access_type, access_status, opened_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        payload,
    )
    return payload_access_id


def get_report_access_history_for_user(user_id: int) -> List[sqlite3.Row]:
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT rah.access_id, rah.prediction_id, rah.qr_id, rah.qr_url, rah.access_type, rah.access_status, rah.opened_at
            FROM report_access_history rah
            INNER JOIN predictions p ON p.prediction_id = rah.prediction_id
            WHERE p.user_id = ?
            ORDER BY rah.opened_at DESC
            """,
            (user_id,),
        )
        return cur.fetchall()


def fetch_sql_dataframe(query: str) -> Any:
    """Run a read-only SELECT for admin viewing; short-lived connection."""
    import pandas as pd

    with sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30) as conn:
        return pd.read_sql_query(query, conn)
