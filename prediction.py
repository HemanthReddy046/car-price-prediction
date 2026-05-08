import json
import os
import re
import socket
import uuid
from io import BytesIO
from datetime import datetime
from typing import Dict

import joblib
import numpy as np
import pandas as pd
import qrcode
import streamlit as st

import database
from report_utils import build_prediction_report_pdf

PREDICTION_ID_PATTERN = re.compile(r"^[A-Z0-9]{8,10}$")


@st.cache_resource
def load_artifacts():
    model = joblib.load("car_price_model.pkl")
    ohe = joblib.load("encoder.pkl")
    scaler = joblib.load("scaler.pkl")
    return model, ohe, scaler


@st.cache_data
def load_reference_data():
    df = pd.read_csv("dataset\\train-data_with_accidents.csv")
    df["Brand"] = df["Name"].str.split().str[0]
    df["Model"] = df["Name"].str.split().str[1]

    brand_model_map = (
        df.groupby("Brand")["Model"]
        .apply(lambda x: x.value_counts().nlargest(10).index.tolist())
        .to_dict()
    )

    unique_brands = sorted(brand_model_map.keys())
    unique_locations = sorted(df["Location"].unique())
    return brand_model_map, unique_brands, unique_locations


def is_valid_prediction_id(prediction_id: str) -> bool:
    return bool(PREDICTION_ID_PATTERN.match((prediction_id or "").strip().upper()))


def _resolve_mobile_base_url() -> str:
    configured_url = (os.getenv("APP_BASE_URL", "") or "").strip().rstrip("/")
    if configured_url:
        return configured_url
    hostname = socket.gethostname()
    local_ip = socket.gethostbyname(hostname)
    if local_ip.startswith("127."):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                sock.connect(("8.8.8.8", 80))
                local_ip = sock.getsockname()[0]
        except OSError:
            pass
    return f"http://{local_ip}:8501"


def _render_mobile_report_content(prediction_row, user_email: str) -> None:
    parsed_inputs = json.loads(prediction_row["input_data"])
    predicted_price = float(prediction_row["predicted_price"])
    recommended_price = float(prediction_row["recommended_price"])
    negotiation_low = predicted_price * 0.90
    negotiation_high = predicted_price * 1.05

    st.markdown("## 📱 Mobile Report View")
    st.success("✅ Report Generated Successfully")
    st.info("📱 Mobile Access Ready")
    st.info("📷 QR Code Generated")
    st.markdown(f"### 📄 Prediction ID: `{prediction_row['prediction_id']}`")
    st.caption(f"Generated On: {prediction_row['timestamp']} | User: {user_email}")

    with st.container(border=True):
        st.markdown("#### 🚘 Car Details")
        c1, c2 = st.columns(2)
        c1.write(f"**Brand:** {parsed_inputs.get('Brand', 'N/A')}")
        c1.write(f"**Model:** {parsed_inputs.get('Model', 'N/A')}")
        c1.write(f"**Fuel Type:** {parsed_inputs.get('Fuel_Type', 'N/A')}")
        c1.write(f"**Transmission:** {parsed_inputs.get('Transmission', 'N/A')}")
        c2.write(f"**Owner Type:** {parsed_inputs.get('Owner_Type', 'N/A')}")
        c2.write(f"**Location:** {parsed_inputs.get('Location', 'N/A')}")
        c2.write(f"**Accidents:** {parsed_inputs.get('Accidents', 'N/A')}")
        c2.write(f"**Kilometers Driven:** {parsed_inputs.get('Kilometers_Driven', 'N/A')}")

    with st.container(border=True):
        st.markdown("#### 💰 Price Summary")
        st.write(f"**Predicted Price:** INR {predicted_price:.2f} Lakhs")
        st.write(f"**Recommended Price:** INR {recommended_price:.2f} Lakhs")
        st.write(
            f"**Negotiation Range:** INR {negotiation_low:.2f} Lakhs - INR {negotiation_high:.2f} Lakhs"
        )


def render_mobile_report_view(prediction_id: str, user_id: int | None, user_email: str) -> None:
    normalized_id = (prediction_id or "").strip().upper()
    row = database.get_prediction_by_public_id(normalized_id, user_id=user_id)
    if not row:
        st.error("❌ Report not found")
        return
    _render_mobile_report_content(row, user_email=user_email)
    _, report_path = get_or_create_report_pdf(row, user_email=user_email)
    with open(report_path, "rb") as report_file:
        mobile_pdf = report_file.read()
    if st.download_button(
        "📥 Download PDF",
        data=mobile_pdf,
        file_name=os.path.basename(report_path),
        mime="application/pdf",
        use_container_width=True,
        key=f"mobile_view_download_{normalized_id}",
    ):
        qr_id = st.query_params.get("qr_id", "")
        database.save_report_access_event(
            prediction_id=normalized_id,
            qr_id=qr_id,
                    qr_url="",
            access_type="PDF_DOWNLOAD",
            access_status="DOWNLOADED",
        )


def get_or_create_report_pdf(
    prediction_row,
    user_email: str,
) -> tuple[bytes, str]:
    reports_dir = database.ensure_reports_dir()
    prediction_id = (prediction_row["prediction_id"] or "").strip().upper()
    report_path = os.path.join(reports_dir, f"prediction_{prediction_id}.pdf")
    if os.path.exists(report_path):
        with open(report_path, "rb") as existing_file:
            existing_bytes = existing_file.read()
        # Prevent reusing previously corrupted/invalid PDF files.
        if existing_bytes and existing_bytes.startswith(b"%PDF"):
            return existing_bytes, report_path

    input_data = json.loads(prediction_row["input_data"])
    pdf_bytes = build_prediction_report_pdf(
        user_email=user_email,
        input_data=input_data,
        predicted_price=float(prediction_row["predicted_price"]),
        recommended_price=float(prediction_row["recommended_price"]),
        prediction_id=prediction_id,
        generated_at=prediction_row["timestamp"],
    )
    with open(report_path, "wb") as fp:
        fp.write(pdf_bytes)
    database.save_report(int(prediction_row["user_id"]), report_path)
    return pdf_bytes, report_path


def render_predict_price_page(user_id: int, user_email: str) -> None:
    model, ohe, scaler = load_artifacts()
    brand_model_map, unique_brands, unique_locations = load_reference_data()
    st.session_state.setdefault("prediction_history", [])

    st.markdown(
        """
        <style>
            .title {
                text-align: center;
                font-size: 40px;
                font-weight: 700;
                color: #f7f9ff;
                letter-spacing: 0.4px;
                margin-bottom: 0.3rem;
                text-shadow: 0 8px 30px rgba(99, 102, 241, 0.35);
            }
            .subtitle {
                text-align: center;
                font-size: 16px;
                color: #d0d8ff;
                margin-bottom: 22px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown('<h1 class="title">Choose Your Car Details 🧑‍💻</h1>', unsafe_allow_html=True)

    with st.container(border=True):
        st.markdown("### Enter Car Details")
        c1, c2 = st.columns(2)

        with c1:
            brand = st.selectbox("Car Brand", unique_brands)
            model_list = brand_model_map.get(brand, [])
            model_name = st.selectbox("Car Model", model_list)
            fuel_type = st.selectbox("Fuel Type", ["Petrol", "Diesel"])
            transmission = st.selectbox("Transmission", ["Manual", "Automatic"])
            owner_type_label = st.selectbox(
                "Owner Type",
                [
                    "First Owner",
                    "Second Owner",
                    "Third Owner",
                    "Fourth Owner",
                    "Fifth Owner",
                    "Sixth Owner",
                ],
            )
            owner_type_to_model_value = {
                "First Owner": "First",
                "Second Owner": "Second",
                "Third Owner": "Third",
                # Dataset category is grouped as "Fourth & Above".
                "Fourth Owner": "Fourth & Above",
                "Fifth Owner": "Fourth & Above",
                "Sixth Owner": "Fourth & Above",
            }
            owner_type = owner_type_to_model_value[owner_type_label]
            location = st.selectbox("Location", unique_locations)
            accidents = st.selectbox("Number of Accidents", list(range(0, 11)), index=0)

        with c2:
            manufacturing_year = st.number_input(
                "Manufacturing Year", min_value=1990, value=2015, step=1
            )
            kms_driven = st.number_input(
                "Kilometers Driven", min_value=0, value=50000, step=1000
            )
            mileage = st.number_input("Mileage (kmpl)", min_value=0.0, value=20.0, step=0.1)
            engine = st.number_input(
                "Engine Capacity (CC)", min_value=500, value=1500, step=100
            )
            power = st.number_input("Power (BHP)", min_value=20, value=100, step=5)
            seats = st.selectbox("Seats", [2, 4, 5, 6])

    accidents_int = int(accidents)
    # Existing prediction logic retained.
    car_age = 2025 - manufacturing_year
    input_data = pd.DataFrame(
        {
            "Kilometers_Driven": [kms_driven],
            "Mileage": [mileage],
            "Engine": [engine],
            "Power": [power],
            "Seats": [seats],
            "Car_Age": [car_age],
            "Fuel_Type": [fuel_type],
            "Transmission": [transmission],
            "Owner_Type": [owner_type],
            "Location": [location],
            "Brand": [brand],
            "Model": [model_name],
            "Accidents": [str(accidents_int)],
        }
    )

    encoded_input = ohe.transform(
        input_data[
            [
                "Fuel_Type",
                "Transmission",
                "Owner_Type",
                "Location",
                "Brand",
                "Model",
                "Accidents",
            ]
        ]
    )
    encoded_df = pd.DataFrame(encoded_input, columns=ohe.get_feature_names_out())

    scaled_numerical = scaler.transform(
        input_data[
            [
                "Kilometers_Driven",
                "Mileage",
                "Engine",
                "Power",
                "Seats",
                "Car_Age",
            ]
        ]
    )
    scaled_df = pd.DataFrame(
        scaled_numerical,
        columns=["Kilometers_Driven", "Mileage", "Engine", "Power", "Seats", "Car_Age"],
    )
    final_input = pd.concat([scaled_df, encoded_df], axis=1)

    col_a, col_b, col_c = st.columns([1, 2, 1])
    with col_b:
        run_prediction = st.button("Estimate Car Price", use_container_width=True)

    generated_this_run = False
    if run_prediction:
        with st.spinner("Calculating best estimate..."):
            predicted_price = model.predict(final_input)
            estimated_price = float(np.expm1(predicted_price)[0])

            # Enhancement-only additions.
            recommended_price = estimated_price * 1.075
            negotiation_low = estimated_price * 0.90
            negotiation_high = estimated_price * 1.05

            st.success(f"Predicted Price: INR {estimated_price:.2f} Lakhs")
            st.info(f"Recommended Price: INR {recommended_price:.2f} Lakhs")
            st.warning(
                f"Negotiation Range: INR {negotiation_low:.2f} Lakhs - INR {negotiation_high:.2f} Lakhs"
            )

            raw_inputs: Dict[str, str] = {
                "Brand": brand,
                "Model": model_name,
                "Fuel_Type": fuel_type,
                "Transmission": transmission,
                "Owner_Type": owner_type_label,
                "Location": location,
                "Accidents": str(accidents_int),
                "Manufacturing_Year": str(manufacturing_year),
                "Kilometers_Driven": str(kms_driven),
                "Mileage": str(mileage),
                "Engine": str(engine),
                "Power": str(power),
                "Seats": str(seats),
            }

            _, public_prediction_id = database.save_prediction_with_public_id(
                user_id=user_id,
                input_data=raw_inputs,
                predicted_price=estimated_price,
                recommended_price=recommended_price,
            )
            st.session_state["prediction_history"].append(
                {
                    "prediction_id": public_prediction_id,
                    "timestamp": datetime.now().isoformat(),
                    "predicted_price": estimated_price,
                    "recommended_price": recommended_price,
                }
            )

            pdf_bytes = build_prediction_report_pdf(
                user_email=user_email,
                input_data=raw_inputs,
                predicted_price=estimated_price,
                recommended_price=recommended_price,
                prediction_id=public_prediction_id,
            )

            reports_dir = database.ensure_reports_dir()
            file_name = f"prediction_{public_prediction_id}.pdf"
            report_path = os.path.join(reports_dir, file_name)
            if not os.path.exists(report_path):
                with open(report_path, "wb") as fp:
                    fp.write(pdf_bytes)
                database.save_report(user_id, report_path)

            st.session_state["latest_prediction"] = {
                "prediction_id": public_prediction_id,
                "pdf_bytes": pdf_bytes,
            }
            st.session_state["active_prediction_id"] = public_prediction_id
            generated_this_run = True

    active_prediction_id = st.session_state.get("active_prediction_id", "")
    if active_prediction_id:
        row = database.get_prediction_by_public_id(active_prediction_id, user_id=user_id)
        if row:
            active_pdf_bytes, _ = get_or_create_report_pdf(row, user_email=user_email)
            if "report_qr_meta" not in st.session_state:
                st.session_state["report_qr_meta"] = {}
            is_new_qr = False
            if active_prediction_id not in st.session_state["report_qr_meta"]:
                qr_id = str(uuid.uuid4())[:8]
                st.session_state["report_qr_meta"][active_prediction_id] = {"qr_id": qr_id}
                is_new_qr = True
            qr_id = st.session_state["report_qr_meta"][active_prediction_id]["qr_id"]

            base_url = _resolve_mobile_base_url()
            mobile_url = f"{base_url}/?report_id={active_prediction_id}&qr_id={qr_id}"
            if is_new_qr:
                database.save_report_access_event(
                    prediction_id=active_prediction_id,
                    qr_id=qr_id,
                    qr_url=mobile_url,
                    access_type="QR_SCAN",
                    access_status="GENERATED",
                )

            st.success("✅ Report Generated Successfully")
            st.info("📱 Mobile Access Ready")
            st.info("📷 QR Code Generated")
            st.markdown(f"### 📄 Prediction ID: `{active_prediction_id}`")

            action_col1, action_col2 = st.columns(2)
            with action_col1:
                if st.download_button(
                    "📥 Download PDF",
                    data=active_pdf_bytes,
                    file_name=f"prediction_{active_prediction_id}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"download_pdf_{active_prediction_id}",
                ):
                    database.save_report_access_event(
                        prediction_id=active_prediction_id,
                        qr_id=qr_id,
                        qr_url=mobile_url,
                        access_type="PDF_DOWNLOAD",
                        access_status="DOWNLOADED",
                    )
            with action_col2:
                if st.button(
                    "📱 Open Mobile View",
                    key=f"mobile_view_{active_prediction_id}",
                    use_container_width=True,
                ):
                    database.save_report_access_event(
                        prediction_id=active_prediction_id,
                        qr_id=qr_id,
                        qr_url=mobile_url,
                        access_type="MOBILE_VIEW",
                        access_status="OPENED",
                    )
                    st.query_params["report_id"] = active_prediction_id
                    st.query_params["qr_id"] = qr_id
                    st.rerun()

            if st.button(
                "📄 View Report",
                key=f"view_report_{active_prediction_id}",
                use_container_width=True,
            ):
                st.session_state["inline_report_prediction_id"] = active_prediction_id
                database.save_report_access_event(
                    prediction_id=active_prediction_id,
                    qr_id=qr_id,
                    qr_url=mobile_url,
                    access_type="MOBILE_VIEW",
                    access_status="VIEWED",
                )
                st.rerun()

            inline_prediction_id = st.session_state.get("inline_report_prediction_id", "")
            if inline_prediction_id and inline_prediction_id == active_prediction_id and not generated_this_run:
                inline_row = database.get_prediction_by_public_id(inline_prediction_id, user_id=user_id)
                if inline_row:
                    _render_mobile_report_content(inline_row, user_email=user_email)

            qr_image = qrcode.make(mobile_url)
            qr_buffer = BytesIO()
            qr_image.save(qr_buffer, format="PNG")
            st.markdown("### 📷 Scan QR To Open Report On Phone")
            st.image(qr_buffer.getvalue(), caption="Scan to open mobile report view", width=240)
            st.info("📱 Connect phone to same WiFi network")
            st.markdown(f"🌐 Mobile URL: `{mobile_url}`")

    st.markdown("---")
    st.subheader("📥 Download Report by Prediction ID")
    with st.container(border=True):
        requested_prediction_id = st.text_input(
            "Enter Prediction ID",
            key="download_prediction_id",
            placeholder="Example: A1B2C3D4",
        )
        if st.button("🔎 Fetch & Download", use_container_width=True):
            normalized_id = (requested_prediction_id or "").strip().upper()
            if not is_valid_prediction_id(normalized_id):
                st.error("Invalid Prediction ID format. Use 8-10 letters/numbers.")
            else:
                row = database.get_prediction_by_public_id(normalized_id, user_id=user_id)
                if not row:
                    st.error("Prediction ID not found.")
                else:
                    try:
                        download_bytes, path = get_or_create_report_pdf(row, user_email=user_email)
                        if st.download_button(
                            "📄 Download Requested Report",
                            data=download_bytes,
                            file_name=os.path.basename(path),
                            mime="application/pdf",
                            use_container_width=True,
                        ):
                            database.save_report_access_event(
                                prediction_id=normalized_id,
                                qr_id="",
                                qr_url="",
                                access_type="PDF_DOWNLOAD",
                                access_status="DOWNLOADED",
                            )
                    except Exception:
                        st.error("Failed to generate report right now. Please try again shortly.")
