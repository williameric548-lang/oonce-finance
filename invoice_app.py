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

# 设置页面 (宽屏模式)
st.set_page_config(page_title="OONCE Finance V11", layout="wide", page_icon="💹")

# --- 2. CSS 美化 (全屏适配) ---
st.markdown("""
<style>
    .stApp { background-color: #F5F7F9; }
    h1 { color: #2C3E50; font-family: 'Helvetica Neue', sans-serif; font-weight: 700; text-align: center; padding-bottom: 20px; }
    
    /* 绿色按钮 */
    div.stButton > button { background-color: #27AE60; color: white; border-radius: 8px; border: none; padding: 10px 24px; font-weight: bold; width: 100%; }
    div.stButton > button:hover { background-color: #1E8449; color: white; }
    
    /* 容器样式 (Input/Output 两个大板块) */
    [data-testid="stVerticalBlockBorderWrapper"] { 
        background-color: white; 
        border-radius: 12px; 
        box-shadow: 0 4px 15px rgba(0,0,0,0.05); 
        border: 1px solid #E0E0E0; 
        border-top: 5px solid #27AE60 !important; 
        padding: 25px; 
        margin-bottom: 30px; /* 板块之间增加间距 */
    }
    
    /* 表格样式优化 */
    .stDataFrame { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 (保持 V10 逻辑不变) ---
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
            raw_inv_no = str(res.get("invoice_number", "")).strip()
            raw_subtotal = float(str(res.get("subtotal", 0)).replace(',', ''))
            raw_vat = float(str(res.get("vat", 0)).replace(',', ''))
            raw_total = float(str(res.get("total", 0)).replace(',', ''))
            currency = str(res.get("currency", "ZAR")).upper()
            
            # 查重
            current_signature = (raw_inv_no, raw_total)
            is_duplicate = current_signature in existing_signatures
            
            if is_duplicate and not allow_duplicates:
                skipped_files.append(f"{file.name}")
                continue
            
            row = {
                "Date": res.get("date"), "Invoice No": raw_inv_no,
                entity_label: res.get(key_name), "Currency": currency,
                "Subtotal": 0.0, "VAT": 0.0, "Total": 0.0,
                "Total (USD)": "", "Exchange Rate": 1.0, 
                "Validation": "", "File Name": file.name
            }

            if is_duplicate and allow_duplicates:
                row["Validation"] = "⚠️ DUPLICATE"
            
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

    if skipped_files:
        st.warning(f"🚫 Skipped {len(skipped_files)} duplicates: {', '.join(skipped_files)}")

    if results:
        st.success(f"✅ Processed {len(results)} files")
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
        
        st.write(f"📝 **{mode.upper()} History Editor (Delete rows using checkbox on left)**")
        
        # 启用全宽模式，确保表格不折叠
        edited_df = st.data_editor(
            df,
            key=f"editor_{mode}",
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "Validation": st.column_config.TextColumn("Status", help="Check for Errors"),
            }
        )

        if not df.equals(edited_df):
            if st.button(f"💾 Save Changes ({mode.upper()})", key=f"save_{mode}"):
                edited_df.to_csv(csv_file, index=False, encoding='utf-8-sig')
                st.success("✅ Changes Saved!")
                time.sleep(1)
                st.rerun()

        st.download_button(f"📥 Download CSV", df.to_csv(index=False).encode('utf-8-sig'), f"OONCE_{mode.upper()}.csv")
    else:
        st.info("No records yet.")

# --- 4. 页面布局 (上下结构) ---

st.title("🏭 OONCE Finance Automation")
st.markdown("---")

# === 板块 1: INPUT (全宽) ===
with st.container(border=True): 
    st.subheader("📥 Input Invoices (Cost)")
    
    # 将上传控件和开关放在两列，稍微整洁一点
    c1, c2 = st.columns([3, 1])
    with c1:
        files_in = st.file_uploader("Upload Vendor Invoices", accept_multiple_files=True, key="in")
    with c2:
        st.write("") # 占位
        st.write("")
        allow_dup_in = st.checkbox("🔘 Allow Duplicates", value=False, key="check_in")
        
    if files_in and st.button("🚀 Process Input", key="btn_in"):
        process_and_save(files_in, "input", allow_dup_in)
    
    st.markdown("---")
    show_interactive_table("input")

st.write("") # 增加一点垂直间距
st.write("") 

# === 板块 2: OUTPUT (全宽) ===
with st.container(border=True):
    st.subheader("📤 Output Invoices (Revenue)")
    
    c1, c2 = st.columns([3, 1])
    with c1:
        files_out = st.file_uploader("Upload Client Invoices", accept_multiple_files=True, key="out")
    with c2:
        st.write("")
        st.write("")
        allow_dup_out = st.checkbox("🔘 Allow Duplicates", value=False, key="check_out")
        
    if files_out and st.button("🚀 Process Output", key="btn_out"):
        process_and_save(files_out, "output", allow_dup_out)
    
    st.markdown("---")
    show_interactive_table("output")
