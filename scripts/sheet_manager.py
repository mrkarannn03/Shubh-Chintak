import gspread
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool
import pandas as pd
from dateutil import parser
from datetime import datetime
import os

import pandas as pd
from dateutil import parser
from langchain_core.tools import tool
from datetime import datetime

# 1. Define the absolute path to your credentials
# This ensures Python finds the file regardless of where you run it from
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_PATH = os.path.join(BASE_DIR, "credentials.json")

SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def get_sheet():
    if not os.path.exists(CRED_PATH):
        raise FileNotFoundError(f"Missing credentials.json at {CRED_PATH}")
    
    # Use the path to the file
    creds = Credentials.from_service_account_file(CRED_PATH, scopes=SCOPE)
    client = gspread.authorize(creds)
    
    # !!! CHANGE THIS to your exact Google Sheet Name !!!
    SHEET_NAME = "Mall_Daily_Sales" 
    return client.open(SHEET_NAME).sheet1

from dateutil import parser # You might need: pip install python-dateutil

@tool
def get_sales_data(start_date: str, end_date: str = None):
    """
    Retrieves sales records for a specific date, a month, a year, or a custom range.
    Args:
        start_date: The start date (YYYY-MM-DD). For a whole year, use YYYY-01-01.
        end_date: (Optional) The end date (YYYY-MM-DD). If omitted, only start_date is used.
    """
    try:
        sheet = get_sheet()
        records = sheet.get_all_records()
        if not records:
            return "The spreadsheet is empty."

        df = pd.DataFrame(records)
        # Convert the 'Date' column in your sheet to actual datetime objects
        df['Date'] = pd.to_datetime(df['Date'], errors='coerce')

        # 1. Parse the inputs
        d1 = parser.parse(start_date)
        if end_date:
            d2 = parser.parse(end_date)
        else:
            d2 = d1 # If no end_date, we just look at one day

        # 2. Filter the DataFrame
        mask = (df['Date'] >= d1) & (df['Date'] <= d2)
        results = df.loc[mask].copy()

        if results.empty:
            return f"No records found between {d1.strftime('%Y-%m-%d')} and {d2.strftime('%Y-%m-%d')}."

        # 3. Format Output
        results['Date'] = results['Date'].dt.strftime('%Y-%m-%d')
        total_sum = results['Sales (in rupees)'].sum()
        
        # If the result is huge, only show the first 15 rows + the total
        if len(results) > 15:
            table = results.head(15).to_markdown(index=False)
            return f"Showing first 15 of {len(results)} rows:\n\n{table}\n\n... (truncated)\n\n**TOTAL SALES: {total_sum}**"
        
        return f"{results.to_markdown(index=False)}\n\n**TOTAL SALES: {total_sum}**"

    except Exception as e:
        print(f"--- DATABASE ERROR --- \n{str(e)}")
        return "I had trouble accessing the range. Ensure dates are valid."
