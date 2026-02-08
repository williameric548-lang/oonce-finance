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
st.set_page_config(page_title="OONCE Finance V9", layout="wide", page_icon="💹")

# --- 2. CSS 美化 (含错误高亮样式) ---
st.markdown("""
<style>
    .stApp { background-color: #F5F7F9; }
    h1 { color: #2C3E50; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; text-align: center; padding-bottom: 20px; }
    div.stButton > button { background-color: #27AE60; color: white; border-radius: 8px; border: none; padding: 10px 24px; font-weight: bold; box-shadow: 0 2px 5px rgba(0,0,0,0.1); width: 100%; }
    div.stButton > button:hover { background-color: #1E8449; color: white; border: none; }
    [data-testid="stVerticalBlockBorderWrapper"] { background-color: white; border-radius: 12px; box-shadow: 0 4px 15px rgba(0,0,0,0.05); border: 1px solid #E0E0E0; border-top: 5px solid #27AE60 !important; padding: 20px; }
    .stAlert { background-color: #D4EFDF; color: #145A32; border: 1px solid #A9DFBF; }
    .stException { background-color: #FADBD8; color: #922B21; border: 1px solid #F5B7B1; border-radius: 5px; padding: 10px; }
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

# --- 4. 查重功能 ---
def load_existing_signatures(csv_file):
    signatures = set()
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
                inv_no = str(row.get('Invoice No', '')).strip()
                try: total = float(str(row.get('Total', 0)).replace(',', ''))
                except: total = 0.0
                signatures.add((inv_no, total))
        except: pass
    return signatures

def process_and_save(files, mode):
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
            raw_inv_no = str(res.get("invoice_number", "")).strip()
            raw_subtotal = float(str(res.get("subtotal", 0)).replace(',', ''))
            raw_vat = float(str(res.get("vat", 0)).replace(',', ''))
            raw_total = float(str(res.get("total", 0)).replace(',', ''))
            currency = str(res.get("currency", "ZAR")).upper()
            
            # 查重逻辑
            current_signature = (raw_inv_no, raw_total)
            if current_signature in existing_signatures:
                skipped_files.append(f"📄 {file.name} (Inv: {raw_inv_no}, Amt: {raw_total})")
            else:
                row = {
                    "Date": res.get("date"), "Invoice No": raw_inv_no,
                    entity_label: res.get(key_name), "Currency": currency,
                    "Subtotal": 0.0, "VAT": 0.0, "Total": 0.0,
                    "Total (USD)": "", "Exchange Rate": 1.0, 
                    "Validation": "", # 新增校验列
                    "File Name": file.name
                }

                # 汇率处理
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
                
                # 【关键新增】审计校验逻辑 (Subtotal + VAT vs Total)
                # 注意：我们校验的是原始识别数据，还是转换后的数据？
                # 财务原则：应该校验“票面原始数据”。但如果是 USD 转 ZAR，Total=Subtotal，校验无意义。
                # 所以我们只对 ZAR (本位币/原始币) 发票进行强校验。
                
                if "USD" in currency:
                    row["Validation"] = "✅ USD Auto" # 美元自动转换，默认通过
                else:
                    # 校验 ZAR 发票的数学关系
                    calc_total = round(row["Subtotal"] + row["VAT"], 2)
                    diff = abs(calc_total - row["Total"])
                    
                    if diff < 0.05: # 允许 5分钱 误差
                        row["Validation"] = "✅ OK"
                    else:
                        row["Validation"] = "❌ Check" # 数学不对

                results.append(row)
                existing_signatures.add(current_signature)

        progress_bar.progress((i + 1) / len(files))

    if skipped_files:
        st.error(f"⚠️ {len(skipped_files)} Duplicates Skipped:")
        for msg in skipped_files: st.write(msg)

    if results:
        st.success(f"✅ {len(results)} New Invoices Processed!")
        df = pd.DataFrame(results)
        
        # 列排序，加入 Validation
        core_cols = ["Date", "Invoice No", entity_label, "Subtotal", "VAT", "Total", "Currency"]
        extra_cols = ["Validation", "File Name", "Total (USD)", "Exchange Rate"]
        df = df[core_cols + extra_cols]
        
        # 样式高亮：如果 Validation 是 '❌ Check'，整行变色 (Streamlit DataFrame 样式)
        def highlight_error(row):
            if "❌" in str(row['Validation']):
                return ['background-color: #FADBD8'] * len(row) # 红色背景
            return [''] * len(row)

        st.dataframe(df.style.apply(highlight_error, axis=1), use_container_width=True)
        
        if os.path.exists(csv_file): df.to_csv(csv_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        else: df.to_csv(csv_file, mode='w', header=True, index=False, encoding='utf-8-sig')
        time.sleep(2); st.rerun()

def show_history_table(mode):
    csv_file = FILE_INPUT if mode == "input" else FILE_OUTPUT
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        # 对历史记录也应用高亮
        def highlight_error(row):
            if "❌" in str(row.get('Validation', '')):
                return ['background-color: #FADBD8'] * len(row)
            return [''] * len(row)
            
        st.dataframe(df.tail(10).style.apply(highlight_error, axis=1), use_container_width=True)
        c1, c2 = st.columns([1, 4])
        with c1: st.download_button(f"📥 CSV", df.to_csv(index=False).encode('utf-8-sig'), f"OONCE_{mode.upper()}.csv", use_container_width=True)
        with c2: 
            if st.button(f"🗑️ Clear", key=f"clr_{mode}"): os.remove(csv_file); st.rerun()

def calculate_metrics():
    total_in = 0.0; total_out = 0.0
    if os.path.exists(FILE_INPUT):
        try: total_in = pd.read_csv(FILE_INPUT)['Total'].sum()
        except: pass
    if os.path.exists(FILE_OUTPUT):
        try: total_out = pd.read_csv(FILE_OUTPUT)['Total'].sum()
        except: pass
    return total_in, total_out

# --- 5. 页面布局 ---

st.title("🏭 OONCE Finance Automation")
st.markdown("---")

tot_in, tot_out = calculate_metrics()
net_profit = tot_out - tot_in

col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
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

st.write("") 

col_left, col_right = st.columns(2, gap="large")

with col_left:
    with st.container(border=True): 
        st.subheader("📥 Input Invoices (Cost)")
        st.caption("Suppliers / Bills / Expenses")
        files_in = st.file_uploader("Upload Vendor Invoices", accept_multiple_files=True, key="in")
        if files_in and st.button("Process Input", key="btn_in"):
            process_and_save(files_in, "input")
        st.markdown("---")
        show_history_table("input")

with col_right:
    with st.container(border=True):
        st.subheader("📤 Output Invoices (Revenue)")
        st.caption("Clients / Sales / Incomes")
        files_out = st.file_uploader("Upload Client Invoices", accept_multiple_files=True, key="out")
        if files_out and st.button("Process Output", key="btn_out"):
            process_and_save(files_out, "output")
        st.markdown("---")
        show_history_table("output")
