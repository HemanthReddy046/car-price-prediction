"""Admin-style read-only database viewer (additive; does not change core app logic)."""

import os

import streamlit as st

import database


def _safe_table(query: str, label: str) -> None:
    try:
        df = database.fetch_sql_dataframe(query)
    except Exception as exc:
        st.warning(f"Could not load {label}: {exc}")
        return
    if df.empty:
        st.info("No records found.")
    else:
        st.dataframe(df, use_container_width=True)


def render_database_viewer() -> None:
    if st.session_state.get("role") != "admin":
        st.markdown("### 🔒 Access Restricted — Admin Only")
        return

    st.markdown("## 🔒 ADMIN DATABASE VIEWER")
    st.caption("Confidential system records — authorized administrators only.")
    st.title("🗄️ Database Viewer")
    st.markdown("Read-only snapshots of SQLite tables.")
    st.divider()

    try:
        users_n = database.fetch_sql_dataframe("SELECT COUNT(*) AS n FROM users")
        pred_n = database.fetch_sql_dataframe("SELECT COUNT(*) AS n FROM predictions")
        qr_n = database.fetch_sql_dataframe("SELECT COUNT(*) AS n FROM report_access_history")
        c1, c2, c3 = st.columns(3)
        c1.metric("👤 Users", int(users_n.iloc[0]["n"]))
        c2.metric("🚗 Predictions", int(pred_n.iloc[0]["n"]))
        c3.metric("📱 Access events", int(qr_n.iloc[0]["n"]))
    except Exception:
        pass

    st.subheader("⬇️ Database download")
    db_path = database.DB_PATH
    if os.path.isfile(db_path):
        with open(db_path, "rb") as db_file:
            db_bytes = db_file.read()
        st.download_button(
            label="⬇ Download Database",
            data=db_bytes,
            file_name="car_prediction.db",
            mime="application/octet-stream",
            use_container_width=True,
        )
    else:
        st.info("Database file not found on this environment.")

    st.divider()
    st.subheader("👤 Users table")
    _safe_table("SELECT * FROM users", "users")

    st.divider()
    st.subheader("🚗 Predictions table")
    _safe_table("SELECT * FROM predictions", "predictions")

    st.divider()
    st.subheader("📱 QR access history")
    st.caption("Table `report_access_history`: QR ID, prediction ID, URL, scan/access type, status, timestamp.")
    _safe_table("SELECT * FROM report_access_history", "report_access_history")
