import os
import pandas as pd
from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://postgres:Indium%40123@localhost:5432/olist"
)

folder = r"C:\Users\SaseendranS\Downloads\olist"

for file in os.listdir(folder):
    if file.endswith(".csv"):
        table_name = os.path.splitext(file)[0]

        print(f"Importing {table_name}")

        df = pd.read_csv(os.path.join(folder, file))

        df.to_sql(
            table_name,
            engine,
            schema="public",
            if_exists="replace",
            index=False
        )

print("Done!")