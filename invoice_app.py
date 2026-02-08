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
    if hasattr(uploaded_file, 'name') and uploaded_file.name.lower().endswith('.pdf'): 
        mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    target_entity = "Vendor/Supplier Name" if mode == "input" else "Client/Customer Name"
    entity_key = "vendor" if mode == "input" else "client"
    
    # 【V18 更新 Prompt】: 教会 AI 识别无效图片
    prompt = f"""
    You are a professional invoice OCR system. Extract data into JSON.
    
    CRITICAL RULES:
    1. If the image is NOT an invoice (e.g. selfie, person, landscape, blurry text, random object), return strictly: {{"error": "Not an invoice"}}.
    2. If the image is an invoice but too blurry to read numbers, return: {{"error": "Blurry image"}}.
    3. Fields required: "date" (YYYY-MM-DD), "invoice_number", "{entity_key}", "subtotal", "vat", "total", "currency".
    4. "invoice_number": Extract the main identifier. If missing, return "UNKNOWN".
    5. "vat": If not shown, set to 0.
    6. Return pure numbers for amounts. If currency is Dollars, return "USD".
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
        return {"error": f"API Error {response.status_code}"}
    except Exception as e: return {"error": str(e)}

def load_existing_signatures(csv_file):
    signatures = set()
    if os.path.exists(csv_file):
        try:
            df = pd.read_csv(csv_file)
            for _, row in df.iterrows():
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
    current_batch_signatures = set()
    
    progress_bar = st.progress(0)
    results = []
    skipped_files = []
    failed_files = [] # 【V18】专门记录失败文件
    
    for i, file in enumerate(files):
        # 针对 Camera Input 没有名字的情况，生成一个临时名
        fname = getattr(file, 'name', f"Photo_{datetime.now().strftime('%H%M%S')}.jpg")
        
        try:
            res = extract_invoice_data(file, mode=mode)
            
            # 【V18】检查 AI 是否返回了明确的错误
            if not isinstance(res, dict):
                failed_files.append(f"{fname} (系统响应异常)")
                continue
                
            if "error" in res:
                failed_files.append(f"{fname} ({res['error']})")
                continue

            # 【V18】安全检查关键字段，防止 Key Error
            if "date" in res and ("total" in res or "subtotal" in res):
                raw_inv_no = str(res.get("invoice_number", "UNKNOWN")).strip().upper()
                raw_entity_name = str(res.get(key_name, "UNKNOWN")).strip().upper()
                currency = str(res.get("currency", "ZAR")).upper()

                # 【V18】安全数字转换，防止 Value Error (防崩溃核心)
                try:
                    raw_subtotal = float(str(res.get("subtotal", 0)).replace(',', '').replace(' ', ''))
                    raw_vat = float(str(res.get("vat", 0)).replace(',', '').replace(' ', ''))
                    raw_total = float(str(res.get("total", 0)).replace(',', '').replace(' ', ''))
                except:
                    failed_files.append(f"{fname} (金额识别失败，请重拍)")
                    continue

                # 查重逻辑
                signature = (raw_inv_no, raw_total)
                is_duplicate_history = signature in existing_signatures
                is_duplicate_batch = signature in current_batch_signatures
                
                if (is_duplicate_history or is_duplicate_batch) and not allow_duplicates:
                    skipped_files.append(f"{fname}")
                    continue
                
                row = {
                    "Date": res.get("date"), 
                    "Invoice No": raw_inv_no,       
                    entity_label: raw_entity_name,  
                    "Currency": currency,           
                    "Subtotal": 0.0, "VAT": 0.0, "Total": 0.0,
                    "Total (USD)": "", "Exchange Rate": 1.0, 
                    "Validation": "", "File Name": fname
                }
                
                if (is_duplicate_history or is_duplicate_batch) and allow_duplicates:
                    row["Validation"] = "⚠️ DUPLICATE"
                
                if "USD" in currency:
                    rate = get_historical_zar_rate(row["Date"])
                    if not rate: rate = 1.0; row["Exchange Rate"] = "Error"
                    else: row["Exchange Rate"] = round(rate, 4)
                    converted_val = round(raw_subtotal * (rate if isinstance(rate, float) else 0), 2)
                    row["Subtotal"] = converted_val; row["VAT"] = 0.0; row["Total"] = converted_val
                    row["Total (USD)"] = raw_subtotal
                    if "DUPLICATE" not in row["Validation"]: row["Validation"] = "✅ USD Auto"
                else:
                    row["Subtotal"] = raw_subtotal; row["VAT"] = raw_vat; row["Total"] = raw_total
                    row["Total (USD)"] = ""; row["Exchange Rate"] = 1.0
                    if "DUPLICATE" not in row["Validation"]:
                        calc_total = round(row["Subtotal"] + row["VAT"], 2)
                        # 放宽一点误差容忍度
                        if abs(calc_total - row["Total"]) < 0.1: row["Validation"] = "✅ OK"
                        else: row["Validation"] = "❌ Math Error"
                
                results.append(row)
                current_batch_signatures.add(signature)
            else:
                # 必须字段缺失
                failed_files.append(f"{fname} (未识别到日期或金额)")
        
        except Exception as e:
            # 最后的防线：捕获任何其他未知错误
            failed_files.append(f"{fname} (未知错误: {str(e)})")

        progress_bar.progress((i + 1) / len(files))

    # 统一展示结果
    if skipped_files: st.toast(f"🚫 已跳过 {len(skipped_files)} 个重复文件", icon="🔕")
    
    # 【V18】优雅地展示失败文件，不红屏
    if failed_files:
        st.error(f"⚠️ 以下 {len(failed_files)} 个文件无法处理 (请确保照片清晰且为发票):")
        for msg in failed_files:
            st.text(f"• {msg}")

    if results:
        st.toast(f"✅ 成功录入 {len(results)} 张新发票", icon="🎉")
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
    st.caption("System: OONCE v18.0 (Anti-Crash)")

st.markdown("""
<div class="brand-header">
    <div>
        <div class="brand-title">OONCE FINANCE</div>
        <div class="brand-subtitle">Enterprise Edition | Mobile & Web</div>
    </div>
    <div style="font-size:32px;">💎</div>
</div>
""", unsafe_allow_html=True)

# 板块 1: INPUT
with st.container(border=True): 
    st.markdown("### 📥 Input Invoices (Cost)")
    c1, c2 = st.columns([3, 1])
    with c1: 
        files_in_upload = st.file_uploader("Upload Files (PDF/Image)", accept_multiple_files=True, key="in_up")
        with st.expander("📸 Take a Photo (Camera)"):
            cam_in = st.camera_input("Snap Invoice", key="cam_in")
            
    with c2: 
        st.write(""); st.write("")
        allow_dup_in = st.checkbox("Allow Duplicates", value=False, key="dup_in")
        
        if st.button("Process Input", key="btn_in"):
            all_files_in = []
            if files_in_upload: all_files_in.extend(files_in_upload)
            if cam_in: all_files_in.append(cam_in)
            
            if all_files_in:
                process_and_save(all_files_in, "input", allow_dup_in)
            else:
                st.warning("Please upload a file or take a photo.")

    st.markdown("---")
    show_interactive_table("input")

st.write("")

# 板块 2: OUTPUT
with st.container(border=True):
    st.markdown("### 📤 Output Invoices (Revenue)")
    c1, c2 = st.columns([3, 1])
    with c1: 
        files_out_upload = st.file_uploader("Upload Files (PDF/Image)", accept_multiple_files=True, key="out_up")
        with st.expander("📸 Take a Photo (Camera)"):
            cam_out = st.camera_input("Snap Invoice", key="cam_out")
            
    with c2: 
        st.write(""); st.write("")
        allow_dup_out = st.checkbox("Allow Duplicates", value=False, key="dup_out")
        
        if st.button("Process Output", key="btn_out"):
            all_files_out = []
            if files_out_upload: all_files_out.extend(files_out_upload)
            if cam_out: all_files_out.append(cam_out)
            
            if all_files_out:
                process_and_save(all_files_out, "output", allow_dup_out)
            else:
                st.warning("Please upload a file or take a photo.")

    st.markdown("---")
    show_interactive_table("output")
