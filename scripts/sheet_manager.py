import gspread
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool
import pandas as pd
from dateutil import parser
from datetime import datetime
import os

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
def get_sales_data(target_date: str):
    """
    Retrieves sales records from the spreadsheet.
    Args:
        target_date: Any date string (e.g., 'today', '22-08-2025', '2025-08-22').
    """
    try:
        # 1. Smart Date Parsing
        try:
            # This handles almost any format (DD/MM, MM/DD, etc.)
            clean_date = parser.parse(target_date, dayfirst=True).strftime("%Y-%m-%d")
        except:
            return "Error: I couldn't understand that date. Please use DD-MM-YYYY."

        sheet = get_sheet()
        records = sheet.get_all_records()
        df = pd.DataFrame(records)

        # Convert sheet dates to string for matching
        results = df[df['Date'].astype(str) == clean_date]

        if results.empty:
            return f"I checked the sheet, but there are no sales recorded for {clean_date}."

        # The 'to_markdown' requires 'tabulate' (which you just installed)
        return results.to_markdown(index=False)

    except Exception as e:
        print(f"--- DATABASE ERROR --- \n{str(e)}\n----------------------")
        return "I had trouble reading the sales sheet. Please try again in a moment."