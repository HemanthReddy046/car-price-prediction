import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import auth
import database
from prediction import (
    get_or_create_report_pdf,
    load_artifacts,
    render_mobile_report_view,
    render_predict_price_page,
)


st.set_page_config(page_title="Car Price Prediction System", page_icon="🚗", layout="wide")
database.init_db()


def inject_global_styles() -> None:
    st.markdown(
        """
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;500;600;700&display=swap');

            .stApp {
                font-family: 'Poppins', sans-serif;
                background: linear-gradient(135deg, #0b1020 0%, #121a33 45%, #1b2a52 100%);
                color: #e8ecff;
            }

            .main .block-container {
                padding-top: 2rem;
                padding-bottom: 2rem;
            }

            [data-testid="stSidebar"] {
                background: rgba(11, 16, 32, 0.78);
                backdrop-filter: blur(14px);
                border-right: 1px solid rgba(255, 255, 255, 0.12);
            }

            h1, h2, h3, h4 {
                color: #f6f8ff !important;
                letter-spacing: 0.2px;
                text-align: center;
            }

            p, label, .stMarkdown, .stText {
                color: #d4dbff !important;
            }

            [data-testid="stMetric"] {
                background: rgba(255, 255, 255, 0.09);
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 16px;
                padding: 14px;
                backdrop-filter: blur(10px);
            }

            [data-testid="stForm"], div[data-testid="stVerticalBlock"] > div:has(> div[data-testid="stDataFrame"]) {
                border-radius: 16px;
            }

            [data-baseweb="input"] > div,
            [data-baseweb="select"] > div,
            [data-baseweb="base-input"] > div,
            .stNumberInput > div > div {
                border-radius: 12px !important;
                border: 1px solid rgba(255, 255, 255, 0.24) !important;
                background: rgba(255, 255, 255, 0.08) !important;
            }

            .stButton > button,
            .stDownloadButton > button {
                border-radius: 12px !important;
                border: 1px solid rgba(255, 255, 255, 0.24) !important;
                color: #ffffff !important;
                font-weight: 600 !important;
                background: linear-gradient(135deg, #5e72eb, #3b82f6) !important;
                box-shadow: 0 8px 20px rgba(59, 130, 246, 0.34) !important;
                transition: all 0.22s ease-in-out !important;
            }

            .stButton > button:hover,
            .stDownloadButton > button:hover {
                transform: translateY(-2px);
                box-shadow: 0 12px 26px rgba(94, 114, 235, 0.45) !important;
                border-color: rgba(255, 255, 255, 0.42) !important;
            }

            .stDataFrame, .stTable {
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid rgba(255, 255, 255, 0.15);
                border-radius: 14px;
                padding: 4px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )


def load_model_metrics() -> pd.DataFrame | None:
    try:
        with open("model_metrics.json", "r", encoding="utf-8") as metrics_file:
            metrics = json.load(metrics_file)

        if not isinstance(metrics, list) or not metrics:
            return None

        metrics_df = pd.DataFrame(metrics)
        expected_cols = {"Model", "R2", "MAE", "MSE"}
        if not expected_cols.issubset(metrics_df.columns):
            return None

        return metrics_df[["Model", "R2", "MAE", "MSE"]]
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, OSError, ValueError):
        return None


def render_dashboard() -> None:
    st.title("🗃 Dashboard")
    counts = database.get_dashboard_counts()
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Users", counts["total_users"])
    c2.metric("Total Predictions", counts["total_predictions"])
    c3.metric("Total Reports Generated", counts["total_reports"])

    if "prediction_history" not in st.session_state:
        st.session_state["prediction_history"] = []

    history_df = pd.DataFrame(st.session_state["prediction_history"])
    if history_df.empty:
        rows = database.get_user_predictions(st.session_state["user_id"])
        restored_history = [
            {
                "prediction_id": row["prediction_id"],
                "timestamp": row["timestamp"],
                "predicted_price": row["predicted_price"],
            }
            for row in rows
        ]
        st.session_state["prediction_history"] = restored_history
        history_df = pd.DataFrame(restored_history)

    st.markdown("### 📈 Predictions Over Time")
    if not history_df.empty and {"timestamp", "predicted_price"}.issubset(history_df.columns):
        history_df["timestamp"] = pd.to_datetime(history_df["timestamp"], errors="coerce")
        history_df = history_df.dropna(subset=["timestamp"]).sort_values("timestamp")
        if not history_df.empty:
            trend_fig = px.line(
                history_df,
                x="timestamp",
                y="predicted_price",
                markers=True,
                title="Predictions Over Time",
                template="plotly_dark",
            )
            trend_fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Date & Time",
                yaxis_title="Predicted Price (Lakhs)",
            )
            st.plotly_chart(trend_fig, use_container_width=True)
        else:
            st.info("No valid prediction timestamps available yet.")
    else:
        st.info("Make at least one prediction to view trend charts.")

    st.markdown("### 📊 Price Distribution")
    if not history_df.empty and "predicted_price" in history_df.columns:
        dist_fig = px.histogram(
            history_df,
            x="predicted_price",
            nbins=20,
            title="Distribution of Predicted Prices",
            template="plotly_dark",
        )
        dist_fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Predicted Price (Lakhs)",
            yaxis_title="Frequency",
        )
        st.plotly_chart(dist_fig, use_container_width=True)
    else:
        st.info("No prediction prices available to show distribution.")


def render_history(user_id: int) -> None:
    st.title("👉 Prediction History")
    rows = database.get_user_predictions(user_id)
    if not rows:
        st.info("No prediction history found.")
        return

    history_rows = []
    for row in rows:
        parsed_inputs = json.loads(row["input_data"])
        history_rows.append(
            {
                "Date": row["timestamp"],
                "Prediction ID": row["prediction_id"] or "N/A",
                "Inputs": ", ".join(f"{k}: {v}" for k, v in parsed_inputs.items()),
                "Price": f"INR {row['predicted_price']:.2f} Lakhs",
                "Recommended": f"INR {row['recommended_price']:.2f} Lakhs",
            }
        )
    st.dataframe(pd.DataFrame(history_rows), use_container_width=True)

    st.markdown("### 📄 Download from History")
    available_rows = [row for row in rows if row["prediction_id"]]
    if not available_rows:
        st.info("No downloadable reports found yet.")
    else:
        selected_id = st.selectbox(
            "Choose Prediction ID",
            [row["prediction_id"] for row in available_rows],
            key="history_prediction_id_select",
        )
        if st.button("Download Selected Report", use_container_width=True):
            selected_row = next((row for row in available_rows if row["prediction_id"] == selected_id), None)
            if not selected_row:
                st.error("Unable to locate the selected prediction.")
            else:
                try:
                    pdf_bytes, report_path = get_or_create_report_pdf(
                        prediction_row=selected_row,
                        user_email=st.session_state["user_email"],
                    )
                    st.download_button(
                        "Download PDF",
                        data=pdf_bytes,
                        file_name=f"prediction_{selected_id}.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                    )
                except Exception:
                    st.error("Could not prepare the selected report right now.")

    st.markdown("### 📱 Report Access History")
    access_rows = database.get_report_access_history_for_user(user_id)
    if not access_rows:
        st.info("No report access history found.")
    else:
        access_df = pd.DataFrame(
            [
                {
                    "Access ID": row["access_id"],
                    "Prediction ID": row["prediction_id"] or "N/A",
                    "QR ID": row["qr_id"] or "N/A",
                    "QR URL": row["qr_url"] or "N/A",
                    "Access Type": row["access_type"],
                    "Status": row["access_status"],
                    "Timestamp": row["opened_at"],
                }
                for row in access_rows
            ]
        )
        st.dataframe(access_df, use_container_width=True)


def render_analytics(user_id: int) -> None:
    st.title("📊 Analytics")
    rows = database.get_user_predictions(user_id)
    if not rows:
        st.info("No data available for analytics.")
        return

    data = []
    for row in rows:
        inputs = json.loads(row["input_data"])
        data.append(
            {
                "timestamp": row["timestamp"],
                "predicted_price": row["predicted_price"],
                "brand": inputs.get("Brand", "Unknown"),
                "fuel_type": inputs.get("Fuel_Type", "Unknown"),
            }
        )
    df = pd.DataFrame(data)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date

    row1_col1, row1_col2 = st.columns(2)
    with row1_col1:
        st.subheader("Predictions Count by Brand")
        brand_counts = df["brand"].value_counts()
        st.bar_chart(brand_counts)

    with row1_col2:
        st.subheader("Fuel Type Distribution")
        fuel_counts = df["fuel_type"].value_counts()
        fig, ax = plt.subplots(facecolor="#0f172a")
        ax.pie(
            fuel_counts.values,
            labels=fuel_counts.index,
            autopct="%1.1f%%",
            startangle=90,
        )
        ax.set_facecolor("#0f172a")
        ax.title.set_color("#e2e8f0")
        ax.axis("equal")
        st.pyplot(fig)

    row2_col1, row2_col2 = st.columns(2)
    with row2_col1:
        st.subheader("Price Trend Over Time")
        trend_df = df.groupby("date", as_index=False)["predicted_price"].mean()
        trend_df = trend_df.rename(columns={"predicted_price": "Average Predicted Price"})
        st.line_chart(trend_df.set_index("date"))

    with row2_col2:
        st.subheader("Actual vs Predicted Price")
        if "analytics_dataset" not in st.session_state:
            st.session_state["analytics_dataset"] = pd.read_csv("dataset\\train-data_with_accidents.csv")

        if "analytics_model" not in st.session_state:
            model, _, _ = load_artifacts()
            st.session_state["analytics_model"] = model

        if "y_test" not in st.session_state or "y_pred" not in st.session_state:
            dataset = st.session_state["analytics_dataset"].copy()
            dataset.drop(columns=["Unnamed: 0", "New_Price"], inplace=True, errors="ignore")
            dataset["Mileage"] = dataset["Mileage"].str.replace(" kmpl", "").str.replace(" km/kg", "").astype(float)
            dataset["Engine"] = dataset["Engine"].str.replace(" CC", "").astype(float)
            dataset["Power"] = dataset["Power"].str.replace(" bhp", "").replace("null", None).astype(float)
            dataset.fillna(
                {
                    "Mileage": dataset["Mileage"].median(),
                    "Engine": dataset["Engine"].median(),
                    "Power": dataset["Power"].median(),
                    "Seats": dataset["Seats"].mode()[0],
                },
                inplace=True,
            )
            dataset["Car_Age"] = 2025 - dataset["Year"]
            dataset["Brand"] = dataset["Name"].str.split().str[0]
            dataset["Model"] = dataset["Name"].str.split().str[1]
            dataset.drop(columns=["Year", "Name"], inplace=True, errors="ignore")
            categorical_cols = [
                "Fuel_Type",
                "Transmission",
                "Owner_Type",
                "Location",
                "Brand",
                "Model",
                "Accidents",
            ]
            numerical_cols = [col for col in dataset.columns if col not in categorical_cols + ["Price"]]
            _, ohe, scaler = load_artifacts()
            encoded_categorical = ohe.transform(dataset[categorical_cols])
            encoded_df = pd.DataFrame(
                encoded_categorical, columns=ohe.get_feature_names_out(categorical_cols)
            )
            scaled_numerical = scaler.transform(dataset[numerical_cols])
            scaled_df = pd.DataFrame(scaled_numerical, columns=numerical_cols)
            X = pd.concat([scaled_df, encoded_df], axis=1)
            y = dataset["Price"].copy()
            sample_size = min(len(X), 1000)
            sample_X = X.head(sample_size)
            sample_y = y.head(sample_size)
            model = st.session_state["analytics_model"]
            y_pred = model.predict(sample_X)
            y_pred = np.expm1(y_pred)
            st.session_state["y_test"] = sample_y
            st.session_state["y_pred"] = y_pred

        y_test = pd.Series(st.session_state["y_test"]).reset_index(drop=True)
        y_pred = pd.Series(st.session_state["y_pred"]).reset_index(drop=True)
        scatter_df = pd.DataFrame({"Actual Price": y_test, "Predicted Price": y_pred})
        diag_min = float(min(scatter_df["Actual Price"].min(), scatter_df["Predicted Price"].min()))
        diag_max = float(max(scatter_df["Actual Price"].max(), scatter_df["Predicted Price"].max()))
        scatter_fig = px.scatter(
            scatter_df,
            x="Actual Price",
            y="Predicted Price",
            opacity=0.6,
            template="plotly_dark",
            title="Actual vs Predicted Price",
        )
        scatter_fig.add_trace(
            go.Scatter(
                x=[diag_min, diag_max],
                y=[diag_min, diag_max],
                mode="lines",
                name="Perfect Prediction",
            )
        )
        scatter_fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Actual Price",
            yaxis_title="Predicted Price",
        )
        st.plotly_chart(scatter_fig, use_container_width=True)

    st.subheader("Feature Importance")
    model = st.session_state.get("analytics_model")
    if model is not None and hasattr(model, "feature_importances_"):
        _, ohe, _ = load_artifacts()
        feature_names = [
            "Kilometers_Driven",
            "Mileage",
            "Engine",
            "Power",
            "Seats",
            "Car_Age",
            *list(
                ohe.get_feature_names_out(
                    [
                        "Fuel_Type",
                        "Transmission",
                        "Owner_Type",
                        "Location",
                        "Brand",
                        "Model",
                        "Accidents",
                    ]
                )
            ),
        ]
        importance_df = pd.DataFrame(
            {"feature": feature_names, "importance": model.feature_importances_}
        ).sort_values("importance", ascending=False)
        top_imp = importance_df.head(15)
        imp_fig = px.bar(
            top_imp.sort_values("importance"),
            x="importance",
            y="feature",
            orientation="h",
            template="plotly_dark",
            title="Top 15 Feature Importances",
        )
        imp_fig.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            xaxis_title="Importance",
            yaxis_title="Feature",
        )
        st.plotly_chart(imp_fig, use_container_width=True)
    else:
        st.info("Feature importance is unavailable for this model.")

    st.subheader("Model Comparison")
    metrics_df = load_model_metrics()
    if metrics_df is None:
        st.info("Model metrics file not found or invalid. Run training to generate model_metrics.json.")
    else:
        display_df = metrics_df.rename(columns={"R2": "R²"})
        st.table(display_df)


def render_app() -> None:
    inject_global_styles()

    report_id = st.query_params.get("report_id", "")
    if report_id:
        normalized_id = str(report_id).strip().upper()
        qr_id = str(st.query_params.get("qr_id", "")).strip()
        tracked_key = f"qr_open_logged_{normalized_id}_{qr_id}"
        if not st.session_state.get(tracked_key, False):
            database.save_report_access_event(
                prediction_id=normalized_id,
                qr_id=qr_id,
                qr_url="",
                access_type="QR_SCAN",
                access_status="OPENED",
            )
            database.save_report_access_event(
                prediction_id=normalized_id,
                qr_id=qr_id,
                qr_url="",
                access_type="MOBILE_VIEW",
                access_status="VIEWED",
            )
            st.session_state[tracked_key] = True

        render_mobile_report_view(
            prediction_id=normalized_id,
            user_id=st.session_state.get("user_id"),
            user_email=st.session_state.get("user_email", "Guest User"),
        )
        if st.button("⬅ Back to App", use_container_width=True):
            st.query_params.clear()
            st.rerun()
        return

    if not auth.render_auth_ui():
        return

    with st.sidebar:
        st.success(f"Logged in as {st.session_state['user_email']}")
        selected_page = st.radio(
            "Navigation",
            [
                "Dashboard",
                "Predict Price",
                "Prediction History",
                "Analytics",
                "Logout",
            ],
        )

    if selected_page == "Dashboard":
        render_dashboard()
    elif selected_page == "Predict Price":
        render_predict_price_page(
            user_id=st.session_state["user_id"],
            user_email=st.session_state["user_email"],
        )
    elif selected_page == "Prediction History":
        render_history(st.session_state["user_id"])
    elif selected_page == "Analytics":
        render_analytics(st.session_state["user_id"])
    elif selected_page == "Logout":
        auth.logout()
        st.success("Logged out successfully")
        st.rerun()


if __name__ == "__main__":
    render_app()
