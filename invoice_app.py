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
API_KEY = "AIzaSyA0esre-3yI-sXogx-GWtbNC6dhRw2LzVE"
FILE_INPUT = "oonce_input_v4.csv"
FILE_OUTPUT = "oonce_output_v4.csv"

# 设置页面
st.set_page_config(page_title="OONCE Finance V7", layout="wide", page_icon="💹")

# --- 2. CSS 美化 (核心修复：针对原生容器进行美化) ---
st.markdown("""
<style>
    /* 全局背景色 */
    .stApp {
        background-color: #F5F7F9;
    }
    
    /* 顶部标题样式 */
    h1 {
        color: #2C3E50;
        font-family: 'Helvetica Neue', sans-serif;
        font-weight: 700;
        text-align: center;
        padding-bottom: 20px;
    }
    
    /* 绿色按钮样式 */
    div.stButton > button {
        background-color: #27AE60;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 10px 24px;
        font-weight: bold;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        width: 100%;
    }
    div.stButton > button:hover {
        background-color: #1E8449;
        color: white;
        border: none;
    }

    /* 【关键修复】美化 Streamlit 原生带边框的容器 */
    /* 这会让 st.container(border=True) 变成我们想要的卡片样子 */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: white;
        border-radius: 12px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.05);
        border: 1px solid #E0E0E0;
        border-top: 5px solid #27AE60 !important; /* 顶部的绿色条 */
        padding: 20px;
    }
    
    /* 成功的绿色提示条 */
    .stAlert {
        background-color: #D4EFDF;
        color: #145A32;
        border: 1px solid #A9DFBF;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 (保持不变) ---
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
    try:
        inv_date = datetime.strptime(date_str, "%Y-%m-%d")
        start_date = inv_date - timedelta(days=5)
        end_date = inv_date + timedelta(days=1)
        data = yf.download("ZAR=X", start=start_date, end=end_date, progress=False)
        if not data.empty:
            return float(data['Close'].iloc[-1])
        return None
    except:
        return None

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
                "Date": res.get("date"), "Invoice No": res.get("invoice_number"),
                entity_label: res.get(key_name), "Currency": currency,
                "Subtotal": 0.0, "VAT": 0.0, "Total": 0.0,
                "Total (USD)": "", "Exchange Rate": 1.0, "File Name": file.name
            }

            if "USD" in currency:
                rate = get_historical_zar_rate(row["Date"])
                if not rate: rate = 1.0; row["Exchange Rate"] = "Error"
                else: row["Exchange Rate"] = round(rate, 4)
                
                converted_val = round(raw_subtotal * (rate if isinstance(rate, float) else 0), 2)
                row["Subtotal"] = converted_val; row["VAT"] = 0.0; row["Total"] = converted_val
                row["Total (USD)"] = raw_subtotal
            else:
                row["Subtotal"] = raw_subtotal; row["VAT"] = raw_vat; row["Total"] = raw_total
                row["Total (USD)"] = ""; row["Exchange Rate"] = 1.0
            results.append(row)
        progress_bar.progress((i + 1) / len(files))

    if results:
        st.success(f"✅ {len(results)} Invoices Processed Successfully!")
        df = pd.DataFrame(results)
        core_cols = ["Date", "Invoice No", entity_label, "Subtotal", "VAT", "Total", "Currency"]
        extra_cols = ["File Name", "Total (USD)", "Exchange Rate"]
        df = df[core_cols + extra_cols]
        st.dataframe(df, use_container_width=True)
        if os.path.exists(csv_file): df.to_csv(csv_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        else: df.to_csv(csv_file, mode='w', header=True, index=False, encoding='utf-8-sig')
        time.sleep(1)
        st.rerun()

def show_history_table(mode):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        st.dataframe(df.tail(5), use_container_width=True)
        c1, c2 = st.columns([1, 4])
        with c1:
            st.download_button(f"📥 Download CSV", df.to_csv(index=False).encode('utf-8-sig'), f"OONCE_{mode.upper()}.csv", use_container_width=True)
        with c2:
            if st.button(f"🗑️ Clear Log", key=f"clr_{mode}"):
                os.remove(csv_file)
                st.rerun()

def calculate_metrics():
    total_in = 0.0
    total_out = 0.0
    if os.path.exists(FILE_INPUT):
        try: total_in = pd.read_csv(FILE_INPUT)['Total'].sum()
        except: pass
    if os.path.exists(FILE_OUTPUT):
        try: total_out = pd.read_csv(FILE_OUTPUT)['Total'].sum()
        except: pass
    return total_in, total_out

# --- 6. 页面主布局 (布局结构) ---

st.title("🏭 OONCE Finance Automation")
st.markdown("---")

# === 顶部仪表盘 ===
tot_in, tot_out = calculate_metrics()
net_profit = tot_out - tot_in

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    # 只要使用了 border=True, 我们的 CSS 就会自动把这个框变成 "绿顶白框"
    with st.container(border=True):
        st.markdown(f"<h4 style='color:#7f8c8d; margin:0;'>📉 Total Cost (Input)</h4>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='color:#2C3E50; margin:0;'>R {tot_in:,.2f}</h2>", unsafe_allow_html=True)

with col_m2:
    with st.container(border=True):
        st.markdown(f"<h4 style='color:#7f8c8d; margin:0;'>📈 Total Revenue (Output)</h4>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='color:#2C3E50; margin:0;'>R {tot_out:,.2f}</h2>", unsafe_allow_html=True)

with col_m3:
    color = "#27AE60" if net_profit >= 0 else "#E74C3C"
    with st.container(border=True):
        st.markdown(f"<h4 style='color:#7f8c8d; margin:0;'>💰 Net Profit</h4>", unsafe_allow_html=True)
        st.markdown(f"<h2 style='color:{color}; margin:0;'>R {net_profit:,.2f}</h2>", unsafe_allow_html=True)

st.write("") # 空一行

# === 主体分栏 (Input / Output) ===
col_left, col_right = st.columns(2, gap="large")

with col_left:
    # --- INPUT 模块 ---
    # 【关键修改】这里使用了 border=True
    # 所有的上传控件、按钮、表格，现在都真正“住”在这个框里了
    with st.container(border=True): 
        st.subheader("📥 Input Invoices (Cost)")
        st.caption("Suppliers / Bills / Expenses")
        
        files_in = st.file_uploader("Upload Vendor Invoices", accept_multiple_files=True, key="in")
        if files_in:
            if st.button("Process Input", key="btn_in"):
                process_and_save(files_in, "input")
        
        st.markdown("---")
        show_history_table("input")

with col_right:
    # --- OUTPUT 模块 ---
    with st.container(border=True):
        st.subheader("📤 Output Invoices (Revenue)")
        st.caption("Clients / Sales / Incomes")
        
        files_out = st.file_uploader("Upload Client Invoices", accept_multiple_files=True, key="out")
        if files_out:
            if st.button("Process Output", key="btn_out"):
                process_and_save(files_out, "output")
        
        st.markdown("---")
        show_history_table("output")
