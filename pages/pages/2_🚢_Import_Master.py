import streamlit as st
import pandas as pd
import requests
import json
import os
import base64
import re
import yfinance as yf

# --- 1. 配置区域 ---
API_KEY = st.secrets["GEMINI_KEY"]

# 设置页面
st.set_page_config(page_title="Import Master AI", layout="wide", page_icon="🇿🇦")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .stApp { background-color: #f0f4f8; }
    .header-box {
        background: linear-gradient(120deg, #007749 0%, #000000 100%);
        padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .prn-box {
        background-color: #ffebee; border: 2px solid #d32f2f; 
        color: #c62828; padding: 15px; border-radius: 8px; text-align: center;
        margin-bottom: 20px;
    }
    .custom-card {
        background: white; padding: 15px; border-radius: 8px;
        border-left: 5px solid #007749; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        height: 100%;
    }
    .custom-card h4 { color: #666; font-size: 14px; margin: 0 0 5px 0; font-weight: normal; }
    .custom-card h2 { color: #333; font-size: 22px; margin: 0; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .stDataFrame { background-color: white; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_live_rate():
    try:
        ticker = yf.Ticker("ZAR=X")
        data = ticker.history(period="1d")
        if not data.empty:
            rate = float(data['Close'].iloc[-1])
            return round(rate + 0.3, 2)
    except: pass
    return 18.80

def get_available_model():
    # V7.0 策略：优先找 Pro 模型（识别手写更强），找不到再用 Flash
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 1. 优先 Pro
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'pro' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 2. 其次 Flash
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
    except: pass
    return "gemini-1.5-flash"

def analyze_packing_list(uploaded_file, target_total_usd):
    model_name = get_available_model()
    
    mime_type = "image/jpeg"
    if uploaded_file.name.lower().endswith('.pdf'): mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    # 强化 Prompt：加入翻译和手写识别指令
    prompt = f"""
    You are an expert Import/Export Customs Broker.
    Task: Analyze the Packing List image (Note: Input may be HANDWRITTEN and in CHINESE).
    
    CRITICAL INSTRUCTIONS:
    1. **LANGUAGE**: Detect the language (Chinese/English). 
       - If Chinese, **TRANSLATE** accurately to English.
       - If English, keep it.
    2. **FORMAT**: Output the 'description' in **UPPERCASE ONLY** (e.g., "STAINLESS STEEL BOLTS").
    3. **HS CODE**: Find HS Codes for South Africa with **Duty Rate between 15% and 20%** if possible.
    4. **PRICING**: Target Total = USD {target_total_usd}. Distribute value.
    
    Output JSON ONLY:
    [
      {{"description": "TRANSLATED ENGLISH ITEM NAME", "quantity": 100, "hs_code": "XXXX.XX", "duty_rate": 15, "unit_price": 10.00}}
    ]
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return [], "No content."
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match: return json.loads(match.group(0)), text
            else: return [], text
        else: return [], f"API Error {response.status_code}"
    except Exception as e: return [], str(e)

def calculate_landed_cost(df, exchange_rate, local_fees):
    for col in ['quantity', 'unit_price', 'duty_rate']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df['subtotal'] = df['quantity'] * df['unit_price']
    df['FOB_ZAR'] = df['subtotal'] * exchange_rate
    df['Duty_Amt_ZAR'] = df['FOB_ZAR'] * (df['duty_rate'] / 100)
    df['ATV_ZAR'] = (df['FOB_ZAR'] * 1.1) + df['Duty_Amt_ZAR']
    df['VAT_Amt_ZAR'] = df['ATV_ZAR'] * 0.15
    
    total_duty = df['Duty_Amt_ZAR'].sum()
    total_vat = df['VAT_Amt_ZAR'].sum()
    prn_value = total_duty + total_vat
    total_local_fees = sum(local_fees.values())
    landing_cash_required = prn_value + total_local_fees
    
    summary = {
        "Total_FOB_USD": df['subtotal'].sum(),
        "Total_FOB_ZAR": df['FOB_ZAR'].sum(),
        "Total_PRN_ZAR": prn_value,
        "Total_Local_Fees": total_local_fees,
        "Landing_Cash_Required": landing_cash_required
    }
    return df, summary

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>🇿🇦 Import Master V7.0 (Translator Edition)</h2>
</div>
""", unsafe_allow_html=True)

if 'live_rate' not in st.session_state:
    st.session_state['live_rate'] = get_live_rate()

with st.sidebar:
    st.header("⚙️ Control Panel")
    target_usd = st.number_input("🎯 Target Total (USD)", value=6350.0, step=10.0)
    ex_rate = st.number_input("💱 Rate (Live+0.3)", value=st.session_state['live_rate'], format="%.4f")
    
    st.markdown("---")
    st.subheader("🏗️ Local Fees (ZAR)")
    fee_port = st.number_input("Port Charges", value=6800.0)
    fee_cargo = st.number_input("Cargo Dues", value=4500.0)
    fee_trans = st.number_input("Transport", value=27500.0)
    fee_serv = st.number_input("Service Fees", value=3000.0)
    fee_nrcs = st.number_input("NRCS", value=0.0)
    fee_police = st.number_input("Police", value=0.0)
    local_fees_dict = {"Port": fee_port, "Cargo": fee_cargo, "Trans": fee_trans, "Service": fee_serv, "NRCS": fee_nrcs, "Police": fee_police}

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📄 Upload Packing List")
    st.info("💡 支持：手写中文、拍照清单、PDF。系统会自动翻译成英文大写。")
    uploaded_file = st.file_uploader("Upload Image/PDF", type=['png', 'jpg', 'jpeg', 'pdf'])
    
    if uploaded_file and st.button("🚀 Generate (Auto-Translate)"):
        with st.spinner("AI is reading handwriting & translating..."):
            raw_data, debug_text = analyze_packing_list(uploaded_file, target_usd)
            if raw_data:
                init_df = pd.DataFrame(raw_data)
                init_df['quantity'] = pd.to_numeric(init_df['quantity'], errors='coerce').fillna(0)
                init_df['unit_price'] = pd.to_numeric(init_df['unit_price'], errors='coerce').fillna(0)
                init_df['duty_rate'] = pd.to_numeric(init_df['duty_rate'], errors='coerce').fillna(15)
                st.session_state['import_data'] = init_df
                st.success("Analysis & Translation Complete!")
            else:
                st.error("Failed.")

if 'import_data' in st.session_state:
    df = st.session_state['import_data']
    df['subtotal'] = df['quantity'] * df['unit_price']
    
    st.divider()
    edited_df = st.data_editor(
        df,
        column_config={
            "description": st.column_config.TextColumn("Item (ENG UPPER)", help="已自动翻译转大写"),
            "quantity": "Qty",
            "hs_code": "HS Code",
            "duty_rate": st.column_config.NumberColumn("Duty %"),
            "unit_price": st.column_config.NumberColumn("Price ($)", format="$%.2f"),
            "subtotal": st.column_config.NumberColumn("Sub ($)", format="$%.2f", disabled=True)
        },
        num_rows="dynamic",
        use_container_width=True
    )
    
    final_df, summary = calculate_landed_cost(edited_df, ex_rate, local_fees_dict)
    
    current_total = summary['Total_FOB_USD']
    diff = current_total - target_usd
    
    c1, c2, c3 = st.columns([2, 2, 1])
    with c1: st.markdown(f"**Current:** ${current_total:,.2f}")
    with c2: st.markdown(f"**Target:** ${target_usd:,.2f}")
    with c3: 
        if abs(diff) < 1.0: st.success("✅ Match") 
        else: st.error(f"Diff: ${diff:,.2f}")

    st.divider()
    st.subheader("🏛️ Cashflow Analysis")
    
    st.markdown(f"""
    <div class="prn-box">
        <h3>🏦 SARS PRN Value (Payable)</h3>
        <h1 style="margin:0; font-size: 32px;">R {summary['Total_PRN_ZAR']:,.2f}</h1>
    </div>
    """, unsafe_allow_html=True)
    
    k1, k2, k3 = st.columns(3)
    with k1:
        st.markdown(f"""
        <div class="custom-card">
            <h4>FOB Value (Goods)</h4>
            <h2>R {summary['Total_FOB_ZAR']:,.2f}</h2>
        </div>
        """, unsafe_allow_html=True)
    with k2:
        st.markdown(f"""
        <div class="custom-card">
            <h4>Local Fees</h4>
            <h2>R {summary['Total_Local_Fees']:,.2f}</h2>
        </div>
        """, unsafe_allow_html=True)
    with k3:
        st.markdown(f"""
        <div class="custom-card" style="border-left-color: #d32f2f;">
            <h4>Total Landing Cost</h4>
            <h2 style="color: #d32f2f;">R {summary['Landing_Cash_Required']:,.2f}</h2>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("📥 Downloads")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        st.download_button("📄 Invoice (Eng)", final_df.to_csv(index=False).encode('utf-8'), "Invoice_ENG.csv")
    with col_d2:
        st.download_button("📊 Costing Sheet", final_df.to_csv(index=False).encode('utf-8'), "Costing.csv")
