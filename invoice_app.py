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
    div.stButton > button { background-color: #059669; color: white; border-radius: 6px; border: none; padding: 0.5rem 1rem; font-weight: 600; transition: all 0.2s; }
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
            for model in data.get('models', []):
                if 'generateContent' in model.get('supportedGenerationMethods', []):
                    return model['name'].replace('models/', '')
    except: pass
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
    if uploaded_file.name.lower().endswith('.pdf'): mime_type = "application/pdf"
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    target_entity = "Vendor/Supplier Name" if mode == "input" else "Client/Customer Name"
    entity_key = "vendor" if mode == "input" else "client"
    
    prompt = f"""
    Extract invoice data into JSON.
    Fields required: "date" (YYYY-MM-DD), "invoice_number", "{entity_key}", "subtotal", "vat", "total", "currency".
    Rules: If no VAT shown, set "vat": 0. Return pure numbers. If currency is Dollars, return "USD".
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text.replace('```json', '').replace('```', '').strip())
        return {"Error": f"API Error {response.status_code}"}
    except Exception as e: return {"Error": str(e)}

def load_existing_signatures(csv_file):
    signatures = set()
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
                # 历史数据也强制转大写对比，防止漏网之鱼
                inv_no = str(row.get('Invoice No', '')).strip().upper()
                try: total = float(str(row.get('Total', 0)).replace(',', ''))
                except: total = 0.0
                signatures.add((inv_no, total))
        except: pass
    return signatures

def process_and_save(files, mode, allow_duplicates):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    entity_label = "Vendor" if mode == "input" else "Client"
    key_name = "vendor" if mode == "input" else "client"
    existing_signatures = load_existing_signatures(csv_file)
    progress_bar = st.progress(0)
    results = []
    skipped_files = []
    
    for i, file in enumerate(files):
        res = extract_invoice_data(file, mode=mode)
        if "date" in res:
            # --- 【关键修改】强制转大写 (UPPERCASE) ---
            raw_inv_no = str(res.get("invoice_number", "")).strip().upper()
            raw_entity_name = str(res.get(key_name, "")).strip().upper()
            currency = str(res.get("currency", "ZAR")).upper()
            # ---------------------------------------

            raw_subtotal = float(str(res.get("subtotal", 0)).replace(',', ''))
            raw_vat = float(str(res.get("vat", 0)).replace(',', ''))
            raw_total = float(str(res.get("total", 0)).replace(',', ''))
            
            is_duplicate = (raw_inv_no, raw_total) in existing_signatures
            if is_duplicate and not allow_duplicates:
                skipped_files.append(f"{file.name}")
                continue
            
            row = {
                "Date": res.get("date"), 
                "Invoice No": raw_inv_no,       # 大写
                entity_label: raw_entity_name,  # 大写 (Vendor/Client)
                "Currency": currency,           # 大写
                "Subtotal": 0.0, "VAT": 0.0, "Total": 0.0,
                "Total (USD)": "", "Exchange Rate": 1.0, 
                "Validation": "", "File Name": file.name
            }
            if is_duplicate and allow_duplicates: row["Validation"] = "⚠️ DUPLICATE"
            
            if "USD" in currency:
                rate = get_historical_zar_rate(row["Date"])
                if not rate: rate = 1.0; row["Exchange Rate"] = "Error"
                else: row["Exchange Rate"] = round(rate, 4)
                converted_val = round(raw_subtotal * (rate if isinstance(rate, float) else 0), 2)
                row["Subtotal"] = converted_val; row["VAT"] = 0.0; row["Total"] = converted_val
                row["Total (USD)"] = raw_subtotal
                if not is_duplicate: row["Validation"] = "✅ USD Auto"
            else:
                row["Subtotal"] = raw_subtotal; row["VAT"] = raw_vat; row["Total"] = raw_total
                row["Total (USD)"] = ""; row["Exchange Rate"] = 1.0
                if not is_duplicate:
                    calc_total = round(row["Subtotal"] + row["VAT"], 2)
                    if abs(calc_total - row["Total"]) < 0.05: row["Validation"] = "✅ OK"
                    else: row["Validation"] = "❌ Math Error"
            results.append(row)
        progress_bar.progress((i + 1) / len(files))

    if skipped_files: st.toast(f"🚫 Skipped {len(skipped_files)} duplicates", icon="🔕")
    if results:
        st.toast(f"✅ Processed {len(results)} new files", icon="🎉")
        df = pd.DataFrame(results)
        core_cols = ["Date", "Invoice No", entity_label, "Subtotal", "VAT", "Total", "Currency"]
        extra_cols = ["Validation", "File Name", "Total (USD)", "Exchange Rate"]
        df = df[core_cols + extra_cols]
        if os.path.exists(csv_file): df.to_csv(csv_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        else: df.to_csv(csv_file, mode='w', header=True, index=False, encoding='utf-8-sig')
        time.sleep(1)
        st.rerun()

def show_interactive_table(mode):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        edited_df = st.data_editor(
            df, key=f"editor_{mode}", num_rows="dynamic", use_container_width=True, hide_index=True,
            column_config={"Validation": st.column_config.TextColumn("Status")}
        )
        if not df.equals(edited_df):
            if st.button(f"💾 Save Changes", key=f"save_{mode}"):
                edited_df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                st.success("Saved!")
                time.sleep(1); st.rerun()
        st.download_button(f"📥 Download CSV", df.to_csv(index=False).encode('utf-8-sig'), f"OONCE_{mode.upper()}.csv")
    else: st.info("No records.")

def calculate_metrics():
    total_in = 0.0; total_out = 0.0
    if os.path.exists(FILE_INPUT):
        try: total_in = pd.read_csv(FILE_INPUT)['Total'].sum()
        except: pass
    if os.path.exists(FILE_OUTPUT):
        try: total_out = pd.read_csv(FILE_OUTPUT)['Total'].sum()
        except: pass
    return total_in, total_out

# --- 4. 页面布局 ---

with st.sidebar:
    st.markdown("### 📊 Dashboard")
    tot_in, tot_out = calculate_metrics()
    net_profit = tot_out - tot_in
    st.metric("Total Cost (Input)", f"R {tot_in:,.2f}", delta="-Cost", delta_color="inverse")
    st.metric("Total Revenue (Output)", f"R {tot_out:,.2f}", delta="+Rev")
    st.divider()
    st.metric("Net Profit", f"R {net_profit:,.2f}", delta_color="normal" if net_profit>=0 else "inverse")
    st.markdown("---")
    st.markdown("### ⚙️ Settings")
    allow_dup_in = st.checkbox("Allow Duplicates (Input)", value=False)
    allow_dup_out = st.checkbox("Allow Duplicates (Output)", value=False)
    st.markdown("---")
    st.caption("System: OONCE v14.0")

st.markdown("""
<div class="brand-header">
    <div>
        <div class="brand-title">OONCE FINANCE</div>
        <div class="brand-subtitle">Enterprise Edition | Intelligent Automation</div>
    </div>
    <div style="font-size:32px;">💎</div>
</div>
""", unsafe_allow_html=True)

with st.container(border=True): 
    st.markdown("### 📥 Input Invoices (Cost)")
    c1, c2 = st.columns([3, 1])
    with c1: files_in = st.file_uploader("Upload Vendor Invoices", accept_multiple_files=True, key="in")
    with c2: 
        st.write(""); st.write("")
        if files_in and st.button("Process Input", key="btn_in"):
            process_and_save(files_in, "input", allow_dup_in)
    st.markdown("---")
    show_interactive_table("input")

st.write("")

with st.container(border=True):
    st.markdown("### 📤 Output Invoices (Revenue)")
    c1, c2 = st.columns([3, 1])
    with c1: files_out = st.file_uploader("Upload Client Invoices", accept_multiple_files=True, key="out")
    with c2: 
        st.write(""); st.write("")
        if files_out and st.button("Process Output", key="btn_out"):
            process_and_save(files_out, "output", allow_dup_out)
    st.markdown("---")
    show_interactive_table("output")
