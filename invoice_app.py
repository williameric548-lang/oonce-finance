import streamlit as st
import pandas as pd
import requests
import json
import os
import base64
import time
import yfinance as yf
from datetime import datetime, timedelta

# --- 1. 配置区域 ---
# 从云端保险箱读取密钥
API_KEY = st.secrets["GOOGLE_API_KEY"]
FILE_INPUT = "oonce_input_v4.csv"
FILE_OUTPUT = "oonce_output_v4.csv"

st.set_page_config(page_title="OONCE Finance V5", layout="wide")

# --- 2. 核心工具函数 ---
def get_available_model():
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for model in data.get('models', []):
                if 'generateContent' in model.get('supportedGenerationMethods', []):
                    return model['name'].replace('models/', '')
    except:
        pass
    return "gemini-1.5-flash"

def get_historical_zar_rate(date_str):
    """ 
    获取历史汇率 (智能修复版) 
    如果发票日期是周末，会自动寻找最近的一个交易日收盘价
    """
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d")
        
        # 【关键修改】: 不只查当天，而是查“过去5天到明天”这个范围
        # 这样如果当天是周六，就能自动抓到周五的数据
        start_date = inv_date - timedelta(days=5)
        end_date = inv_date + timedelta(days=1)
        
        data = yf.download("ZAR=X", start=start_date, end=end_date, progress=False)
        
        if not data.empty:
            # iloc[-1] 意思是取“最后一条数据”
            # 也就是离发票日期最近的那次收盘价
            return float(data['Close'].iloc[-1])
        return None
    except:
        return None

def extract_invoice_data(uploaded_file, mode="input"):
    model_name = get_available_model()
    
    mime_type = "image/jpeg"
    if uploaded_file.name.lower().endswith('.pdf'):
        mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    target_entity = "Vendor/Supplier Name" if mode == "input" else "Client/Customer Name"
    entity_key = "vendor" if mode == "input" else "client"
    
    prompt = f"""
    Extract invoice data into JSON.
    Fields required: "date" (YYYY-MM-DD), "invoice_number", "{entity_key}", "subtotal", "vat", "total", "currency".
    
    Rules:
    1. If no VAT shown, set "vat": 0.
    2. Return pure numbers, no commas.
    3. If currency is Dollars, return "USD".
    """

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime_type, "data": base64_data}}
            ]
        }]
    }

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            clean_text = text.replace('```json', '').replace('```', '').strip()
            return json.loads(clean_text)
        else:
            return {"Error": f"API Error {response.status_code}"}
    except Exception as e:
        return {"Error": str(e)}

def process_and_save(files, mode):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    entity_label = "Vendor" if mode == "input" else "Client"
    key_name = "vendor" if mode == "input" else "client"
    
    progress_bar = st.progress(0)
    results = []
    
    for i, file in enumerate(files):
        res = extract_invoice_data(file, mode=mode)
        
        if "date" in res:
            raw_subtotal = float(str(res.get("subtotal", 0)).replace(',', ''))
            raw_vat = float(str(res.get("vat", 0)).replace(',', ''))
            raw_total = float(str(res.get("total", 0)).replace(',', ''))
            currency = str(res.get("currency", "ZAR")).upper()
            
            row = {
                "Date": res.get("date"),
                "Invoice No": res.get("invoice_number"),
                entity_label: res.get(key_name),
                "Currency": currency,
                "Subtotal": 0.0,
                "VAT": 0.0,
                "Total": 0.0,
                "Total (USD)": "",
                "Exchange Rate": 1.0,
                "File Name": file.name
            }

            if "USD" in currency:
                rate = get_historical_zar_rate(row["Date"])
                if not rate: 
                    rate = 1.0
                    row["Exchange Rate"] = "Error"
                else:
                    row["Exchange Rate"] = round(rate, 4)
                
                converted_val = round(raw_subtotal * (rate if isinstance(rate, float) else 0), 2)
                row["Subtotal"] = converted_val
                row["VAT"] = 0.0
                row["Total"] = converted_val
                row["Total (USD)"] = raw_subtotal
                
            else:
                row["Subtotal"] = raw_subtotal
                row["VAT"] = raw_vat
                row["Total"] = raw_total
                row["Total (USD)"] = ""
                row["Exchange Rate"] = 1.0

            results.append(row)
        
        progress_bar.progress((i + 1) / len(files))

    if results:
        st.success(f"✅ {mode.upper()} Processed!")
        df = pd.DataFrame(results)
        
        core_cols = ["Date", "Invoice No", entity_label, "Subtotal", "VAT", "Total", "Currency"]
        extra_cols = ["File Name", "Total (USD)", "Exchange Rate"]
        df = df[core_cols + extra_cols]
        
        st.dataframe(df)
        
        if os.path.exists(csv_file):
            df.to_csv(csv_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            df.to_csv(csv_file, mode='w', header=True, index=False, encoding='utf-8-sig')

def show_history(mode):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    
    if os.path.exists(csv_file):
        st.markdown(f"**📂 History ({mode.upper()})**")
        df_hist = pd.read_csv(csv_file)
        st.dataframe(df_hist.tail(5))
        
        c1, c2 = st.columns([1, 4])
        with c1:
            st.download_button(f"📥 Download CSV", df_hist.to_csv(index=False).encode('utf-8-sig'), f"OONCE_{mode.upper()}.csv")
        with c2:
            if st.button(f"🗑️ Clear Log", key=f"clr_{mode}"):
                os.remove(csv_file)
                st.rerun()

# --- 3. 界面 ---
st.title("🏭 OONCE Finance Automation (V5)")

# Input
st.header("📥 INPUT (Vendor)")
files_in = st.file_uploader("Upload Vendor Invoices", accept_multiple_files=True, key="in")
if files_in and st.button("🚀 Process INPUT", key="bin"): process_and_save(files_in, "input")
show_history("input")

st.divider()

# Output
st.header("📤 OUTPUT (Client)")
files_out = st.file_uploader("Upload Client Invoices", accept_multiple_files=True, key="out")
if files_out and st.button("🚀 Process OUTPUT", key="bout"): process_and_save(files_out, "output")
show_history("output")