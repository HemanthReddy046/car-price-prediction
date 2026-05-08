'''import pandas as pd

# Load train and test datasets
train_df = pd.read_csv("dataset\\train-data.csv")
test_df = pd.read_csv("dataset\\test-data.csv")

# Display the first five rows
print(train_df.head())

# Check dataset info
print(train_df.info())

# Check for missing values
print(train_df.isnull().sum())

print(df.columns)
'''
import numpy as np
import pandas as pd
df = pd.read_csv("dataset/train-data.csv")
# Add 'Accidents' column with random values (0, 1, or 2 accidents)
np.random.seed(42)  # For reproducibility
df['Accidents'] = np.random.choice([0, 1, 2], size=len(df))

# Save the updated dataset with accidents
df.to_csv("dataset/train-data_with_accidents.csv", index=False)

# Check the first few rows
print(df.head())

# Example logic: Cars older than 10 years get more accidents, cars younger get fewer
df['Accidents'] = df['Year'].apply(lambda x: 2 if 2025 - x > 10 else (1 if 2025 - x > 5 else 0))

# Save the updated dataset
df.to_csv("dataset/train-data_with_accidents.csv", index=False)

# Check the first few rows
print(df.head())
