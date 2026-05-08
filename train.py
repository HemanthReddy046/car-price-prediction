import pandas as pd
import numpy as np
import joblib
import json
import os
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from xgboost import XGBRegressor
from lightgbm import LGBMRegressor
from catboost import CatBoostRegressor
import random
from tempfile import NamedTemporaryFile

# Load dataset
df = pd.read_csv("dataset\\train-data_with_accidents.csv")

# Drop unnecessary columns
df.drop(columns=['Unnamed: 0', 'New_Price'], inplace=True, errors="ignore")

# Handle missing values and convert columns
df['Mileage'] = df['Mileage'].str.replace(" kmpl", "").str.replace(" km/kg", "").astype(float)
df['Engine'] = df['Engine'].str.replace(" CC", "").astype(float)
df['Power'] = df['Power'].str.replace(" bhp", "").replace("null", None).astype(float)

df.fillna({
    'Mileage': df['Mileage'].median(),
    'Engine': df['Engine'].median(),
    'Power': df['Power'].median(),
    'Seats': df['Seats'].mode()[0]
}, inplace=True)

# Feature Engineering
df['Car_Age'] = 2025 - df['Year']  # Calculate car age
df.drop(columns=['Year'], inplace=True)  # Drop original year column

# Extract Brand and Model before dropping Name
df['Brand'] = df['Name'].str.split().str[0]
df['Model'] = df['Name'].str.split().str[1]
df.drop(columns=['Name'], inplace=True)

# Keep existing accidents data if available; otherwise generate fallback values.
if "Accidents" not in df.columns:
    df['Accidents'] = [random.randint(0, 3) for _ in range(len(df))]
df["Accidents"] = df["Accidents"].fillna(0).astype(int).astype(str)

# Then include 'Model' and 'Accidents' in categorical features
categorical_cols = ['Fuel_Type', 'Transmission', 'Owner_Type', 'Location', 'Brand', 'Model', 'Accidents']
numerical_cols = [col for col in df.columns if col not in categorical_cols + ['Price']]

# One-Hot Encoding for categorical variables
ohe = OneHotEncoder(handle_unknown='ignore', sparse_output=False)
encoded_categorical = ohe.fit_transform(df[categorical_cols])
encoded_df = pd.DataFrame(encoded_categorical, columns=ohe.get_feature_names_out(categorical_cols))

# Scale Numerical Features
scaler = StandardScaler()
scaled_numerical = scaler.fit_transform(df[numerical_cols])
scaled_df = pd.DataFrame(scaled_numerical, columns=numerical_cols)

# Combine features
X = pd.concat([scaled_df, encoded_df], axis=1)
y = np.log1p(df['Price'])  # Apply log transformation

# Remove outliers (Prices beyond 99th percentile)
upper_limit = np.percentile(y, 99)
lower_limit = np.percentile(y, 1)
y = np.clip(y, lower_limit, upper_limit)

# Split data
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Define models
models = {
    "XGBoost": XGBRegressor(n_estimators=500, learning_rate=0.05, max_depth=6, random_state=42),
    "LightGBM": LGBMRegressor(n_estimators=500, learning_rate=0.05, max_depth=6, random_state=42),
    "CatBoost": CatBoostRegressor(n_estimators=500, learning_rate=0.05, depth=6, verbose=0, random_state=42)
}

# Train and evaluate models
best_model, best_score = None, float("-inf")
model_metrics = []

for name, model in models.items():
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_pred = np.expm1(y_pred)  # Convert log-transformed predictions back
    y_test_original = np.expm1(y_test)
    
    mae = mean_absolute_error(y_test_original, y_pred)
    mse = mean_squared_error(y_test_original, y_pred)
    score = r2_score(y_test_original, y_pred)

    model_metrics.append(
        {
            "Model": name,
            "R2": float(score),
            "MAE": float(mae),
            "MSE": float(mse),
        }
    )

    print(f"\n{name} Model Performance:")
    print("MAE:", mae)
    print("MSE:", mse)
    print("R2 Score:", score)

    # Save the best model
    if score > best_score:
        best_model, best_score = model, score

# Save the best model and encoders
with NamedTemporaryFile(delete=False, suffix=".pkl") as model_tmp, \
    NamedTemporaryFile(delete=False, suffix=".pkl") as ohe_tmp, \
    NamedTemporaryFile(delete=False, suffix=".pkl") as scaler_tmp, \
    NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8") as metrics_tmp:
    model_tmp_path = model_tmp.name
    ohe_tmp_path = ohe_tmp.name
    scaler_tmp_path = scaler_tmp.name
    metrics_tmp_path = metrics_tmp.name

try:
    joblib.dump(best_model, model_tmp_path)
    joblib.dump(ohe, ohe_tmp_path)
    joblib.dump(scaler, scaler_tmp_path)
    with open(metrics_tmp_path, "w", encoding="utf-8") as metrics_file:
        json.dump(model_metrics, metrics_file, indent=2)

    os.replace(model_tmp_path, "car_price_model.pkl")
    os.replace(ohe_tmp_path, "encoder.pkl")
    os.replace(scaler_tmp_path, "scaler.pkl")
    os.replace(metrics_tmp_path, "model_metrics.json")
except Exception as exc:
    print(f"\nRetraining failed. Existing model artifacts were kept intact. Error: {exc}")
finally:
    for tmp_path in [model_tmp_path, ohe_tmp_path, scaler_tmp_path, metrics_tmp_path]:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

print("\nBest model and encoders saved successfully!")
print("Model metrics saved to model_metrics.json")
