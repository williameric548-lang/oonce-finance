import streamlit as st
import pandas as pd
import requests
import json
import os
import base64
import time
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 全局配置 ---
# 厂长，为了保证您现在粘贴就能用，我先把 Key 写在这里。
# 如果您已经在 Streamlit 后台配置了 Secrets，可以把下面这行改成: API_KEY = st.secrets["GEMINI_KEY"]
API_KEY = "AIzaSyA0esre-3yI-sXogx-GWtbNC6dhRw2LzVE"

FILE_INPUT = "oonce_input_v4.csv"
FILE_OUTPUT = "oonce_output_v4.csv"

# 设置页面
st.set_page_config(page_title="OONCE Finance", layout="wide", page_icon="📈")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    .brand-header {
        background: linear-gradient(135deg, #0F2027 0%, #203A43 50%, #2C5364 100%);
        padding: 25px; border-radius: 12px; color: white; margin-bottom: 25px;
        display: flex; align-items: center; justify-content: space-between;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    .brand-title { font-family: 'Helvetica Neue', sans-serif; font-size: 28px; font-weight: 800; letter-spacing: 2px; color: #ffffff; }
    .brand-subtitle { font-size: 14px; opacity: 0.8; font-weight: 400; margin-top: 5px; letter-spacing: 1px; }
    [data-testid="stSidebar"] { background-color: #ffffff; border-right: 1px solid #e5e7eb; }
    div.stButton > button { background-color: #059669; color: white; border-radius: 6px; border: none; padding: 0.5rem 1rem; font-weight: 600; transition: all 0.2s; width: 100%; }
    div.stButton > button:hover { background-color: #047857; box-shadow: 0 4px 12px rgba(5, 150, 105, 0.2); }
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: white; border-radius: 8px; border: 1px solid #e5e7eb; box-shadow: 0 1px 3px rgba(0,0,0,0.05); padding: 20px; border-top: 4px solid #059669 !important; }
    .stDataFrame { font-size: 14px; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 优先寻找 flash
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 兜底
            for model in data.get('models', []):
                if 'generateContent' in model.get('supportedGenerationMethods', []):
                    return model['name'].replace('models/', '')
    except:
        pass
    return "gemini-1.5-flash"

def get_historical_zar_rate(date_str):
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d")
        start_date = inv_date - timedelta(days=5)
        end_date = inv_date + timedelta(days=1)
        data = yf.download("ZAR=X", start=start_date, end=end_date, progress=False)
        if not data.empty: return float(data['Close'].iloc[-1])
        return None
    except: return None

def extract_invoice_data(uploaded_file, mode="input"):
    model_name = get_available_model()
    
    mime_type = "image/jpeg"
    if hasattr(uploaded_file, 'name') and uploaded_file.name.lower().endswith('.pdf'): 
        mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    target_entity = "Vendor/Supplier Name" if mode == "input" else "Client/Customer Name"
    entity_key = "vendor" if mode == "input" else "client"
    
    prompt = f"""
    You are an expert financial auditor OCR system. 
    Task: Extract invoice data into JSON.

    CRITICAL INSTRUCTIONS FOR ACCURACY:
    1. **TOTAL AMOUNT**: Look for "Total Due", "Balance Due", "Grand Total". Be extremely careful with decimal points.
    2. **DATE**: Identify the main Invoice Date. Format: YYYY-MM-DD.
    3. **INVOICE NO**: Extract the unique Invoice Number.
    4. **{target_entity}**: Extract the full company name.
    5. **NO HALLUCINATIONS**: If the image is blurry or not an invoice, return {{"error": "Image unclear/Not invoice"}}.
    
    Output JSON format:
    {{
        "date": "YYYY-MM-DD", 
        "invoice_number": "STRING", 
        "{entity_key}": "STRING", 
        "subtotal": NUMBER, 
        "vat": NUMBER, 
        "total": NUMBER, 
        "currency": "USD" or "ZAR"
    }}
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_text = text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
        else:
            return {"error": f"API Error {response.status_code} (Model: {model_name})"}
    except Exception as e: return {"error": str(e)}

def load_existing_signatures(csv_file):
    signatures = set()
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
                # 1. 发票号去空格、转大写
                inv_no = str(row.get('Invoice No', '')).strip().upper()
                try: 
                    # 2. 【核心修复】金额强制
