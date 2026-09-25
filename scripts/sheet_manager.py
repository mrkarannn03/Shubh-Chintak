import os
import sys
import re
import gspread
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from langchain_core.tools import tool

# Force UTF-8 encoding for Windows standard output / logging
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

import json

# --- AUTH SETUP ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CRED_PATH = os.path.join(BASE_DIR, "credentials.json")

def get_sheet():
    google_creds_env = os.getenv("GOOGLE_CREDENTIALS")
    scopes = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    if google_creds_env:
        creds_dict = json.loads(google_creds_env)
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    elif os.path.exists(CRED_PATH):
        creds = Credentials.from_service_account_file(CRED_PATH, scopes=scopes)
    else:
        raise FileNotFoundError("Google credentials not found in environment variable or credentials.json file.")

    client = gspread.authorize(creds)
    return client.open("Mall_Daily_Sales").sheet1 

def create_ascii_chart(df, group_col, sales_col="Sales_Clean", top_k=5):
    try:
        if df.empty or group_col not in df.columns:
            return ""
        summary = df.groupby(group_col)[sales_col].sum().reset_index()
        summary = summary.sort_values(sales_col, ascending=False).head(top_k)
        if summary.empty: 
            return ""
        
        max_val = summary[sales_col].max()
        chart = "\n```\n" 
        for _, row in summary.iterrows():
            label = str(row[group_col])[:12].strip().ljust(12)
            val = row[sales_col]
            bar_len = int((val / max_val) * 15) if max_val > 0 else 0
            chart += f"{label} |{'█' * bar_len} ${val:,.2f}\n"
        chart += "```"
        return chart
    except Exception as e:
        return f"(Chart Error: {e})"

import time

_cached_df = None
_last_fetch_time = 0

def get_cached_dataframe(ttl_seconds=60):
    global _cached_df, _last_fetch_time
    now = time.time()
    if _cached_df is not None and (now - _last_fetch_time) < ttl_seconds:
        return _cached_df.copy()
    
    sheet = get_sheet()
    raw_values = sheet.get_all_values()
    if not raw_values or len(raw_values) < 2:
        return pd.DataFrame()

    df = pd.DataFrame(raw_values[1:], columns=raw_values[0])
    df.columns = df.columns.str.strip()

    if 'Sales' in df.columns:
        df['Sales_Clean'] = df['Sales'].astype(str).str.replace('$', '', regex=False).str.replace(',', '', regex=False).str.strip()
        df['Sales_Clean'] = pd.to_numeric(df['Sales_Clean'], errors='coerce').fillna(0.0)
    else:
        df['Sales_Clean'] = 0.0

    _cached_df = df
    _last_fetch_time = now
    return df.copy()

@tool
def get_sales_data(
    start_date: str = None, 
    end_date: str = None, 
    order_id: str = None, 
    location: str = None, 
    group_by: str = None, 
    top_k: int = 5,
    action: str = None,
    **kwargs
):
    """Retrieves REAL data from the Google Sheet. Supports order_id lookup, date filtering, location filtering, and grouping top performers."""
    try:
        df = get_cached_dataframe(ttl_seconds=60)
        if df.empty:
            return "ERROR: Google Sheet is empty or missing data."

        # --- 1. ORDER ID SEARCH ---
        if order_id:
            id_col = next((c for c in df.columns if 'Order ID' in c), "Order ID")
            target_id = str(order_id).strip().lower()
            match = df[df[id_col].astype(str).str.strip().str.lower() == target_id]
            
            if match.empty:
                # Substring fallback search
                match = df[df[id_col].astype(str).str.strip().str.lower().str.contains(target_id, na=False)]
            
            if match.empty:
                return f"ERROR: Order ID '{order_id}' not found in Google Sheet."
            
            data = match.iloc[0].to_dict()
            return (
                f"--- REAL_SHEET_DATA_FOUND (ORDER LOOKUP) ---\n"
                f"Row ID: {data.get('Row ID', 'N/A')}\n"
                f"Order ID: {data.get('Order ID', 'N/A')}\n"
                f"Order Date: {data.get('Order Date', 'N/A')}\n"
                f"Ship Date: {data.get('Ship Date', 'N/A')}\n"
                f"Ship Mode: {data.get('Ship Mode', 'N/A')}\n"                
                f"Customer ID: {data.get('Customer ID', 'N/A')}\n"  
                f"Customer Name: {data.get('Customer Name', 'N/A')}\n"   
                f"Segment: {data.get('Segment', 'N/A')}\n"           
                f"Country: {data.get('Country', 'N/A')}\n"
                f"City: {data.get('City', 'N/A')}, State: {data.get('State', 'N/A')}\n"
                f"Region: {data.get('Region', 'N/A')}\n"                
                f"Product ID: {data.get('Product ID', 'N/A')}\n"
                f"Category: {data.get('Category', 'N/A')}\n"
                f"Sub-Category: {data.get('Sub-Category', 'N/A')}\n"
                f"Product Name: {data.get('Product Name', 'N/A')}\n"
                f"Sales Amount: ${data.get('Sales_Clean', 0.0):,.2f}\n"
                f"--- END ---"
            )

        # --- 2. FILTER BY LOCATION ---
        if location:
            loc_str = str(location).strip().lower()
            mask = (
                df['City'].astype(str).str.lower().str.contains(loc_str, na=False) |
                df['State'].astype(str).str.lower().str.contains(loc_str, na=False) |
                df['Region'].astype(str).str.lower().str.contains(loc_str, na=False)
            )
            df_filtered = df[mask]
            if not df_filtered.empty:
                df = df_filtered

        # --- 3. FILTER BY DATE RANGE ---
        if 'Order Date' in df.columns and (start_date or end_date):
            parsed_dates = pd.to_datetime(df['Order Date'], dayfirst=True, errors='coerce')
            if start_date:
                try:
                    s_dt = pd.to_datetime(start_date)
                    df = df[parsed_dates >= s_dt]
                    parsed_dates = parsed_dates[parsed_dates >= s_dt]
                except Exception:
                    pass
            if end_date:
                try:
                    e_dt = pd.to_datetime(end_date)
                    df = df[parsed_dates <= e_dt]
                except Exception:
                    pass

        if df.empty:
            return "NO_DATA_FOUND: No sales records matched your specified filters."

        # --- 4. CALCULATE AGGREGATED METRICS ---
        total_sales = df['Sales_Clean'].sum()
        total_orders = len(df)
        avg_order = total_sales / total_orders if total_orders > 0 else 0

        # --- 5. GROUP BY ANALYSIS ---
        target_group_col = None
        if group_by:
            gb_clean = str(group_by).strip().lower()
            for col in df.columns:
                if gb_clean in col.lower() or col.lower() in gb_clean:
                    target_group_col = col
                    break

        if not target_group_col:
            # Smart default grouping column search
            for fallback_col in ['Sub-Category', 'Category', 'Product Name', 'Customer Name', 'Segment', 'State', 'Region']:
                if fallback_col in df.columns:
                    target_group_col = fallback_col
                    break

        chart_str = ""
        breakdown_summary = ""
        if target_group_col and target_group_col in df.columns:
            top_k = int(top_k) if top_k else 5
            grp = df.groupby(target_group_col)['Sales_Clean'].agg(['sum', 'count']).reset_index()
            grp = grp.sort_values(by='sum', ascending=False).head(top_k)
            
            chart_str = create_ascii_chart(df, target_group_col, sales_col='Sales_Clean', top_k=top_k)
            
            items = []
            for _, row in grp.iterrows():
                items.append(f"- {row[target_group_col]}: ${row['sum']:,.2f} ({row['count']} orders)")
            breakdown_summary = "\n".join(items)

        result_str = (
            f"--- REAL_SHEET_DATA_FOUND ---\n"
            f"Total Sales Revenue: ${total_sales:,.2f}\n"
            f"Total Orders Count: {total_orders}\n"
            f"Average Order Value: ${avg_order:,.2f}\n"
        )
        if target_group_col:
            result_str += f"\nTop {target_group_col} Breakdown:\n{breakdown_summary}\n"
        if chart_str:
            result_str += f"\nASCII Dashboard Chart:{chart_str}\n"
            
        result_str += "--- END ---"
        return result_str

    except Exception as e:
        return f"Tool Error executing get_sales_data: {str(e)}"