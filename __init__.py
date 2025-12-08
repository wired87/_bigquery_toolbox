import os

import dotenv
dotenv.load_dotenv()

def get_bq():
    return
BQ_DATASET_ID = os.environ.get("BQ_DS_ID")
