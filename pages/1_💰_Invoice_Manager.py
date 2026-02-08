import streamlit as st
import pandas as pd
import requests
import json
import os
import base64
import re  # 新增正则库，用于清洗数据

# --- 1. 配置区域 ---
API_KEY = st.secrets["GEMINI_KEY"]  # 您的 Key

# 设置页面
st.set_page_config(page_title="Import Master AI", layout="wide", page_icon="🚢")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .stApp { background-color: #f0f4f8; }
    .header-box {
        background: linear-gradient(120deg, #1e3c72 0%, #2a5298 100%);
        padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-card {
        background: white; padding: 15px; border-radius: 8px;
        border-left: 5px solid #1e3c72; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    .stDataFrame { background-color: white; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑函数 ---

# 【移植】自动寻找可用模型 (Auto-Radar)
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

def analyze_packing_list(uploaded_file, target_total_usd):
    # 1. 动态获取模型
    model_name = get_available_model()
    
    mime_type = "image/jpeg"
    if uploaded_file.name.lower().endswith('.pdf'): mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    prompt = f"""
    You are an expert Import/Export Customs Broker for South Africa.
    
    Task 1: Extract items from the Packing List (Description, Quantity).
    Task 2: Suggest the most likely HS CODE for South Africa.
    Task 3: Estimate IMPORT DUTY RATE (e.g. 0, 10, 20).
    Task 4: PRICING LOGIC. Target Total Invoice Value = USD {target_total_usd}.
       - Distribute the {target_total_usd} across items reasonably.
       - Calculate 'unit_price' so: sum(unit_price * quantity) ≈ {target_total_usd}.
    
    Output JSON format (List of objects):
    [
        {{
            "description": "Item Name",
            "quantity": 100,
            "hs_code": "1234.56",
            "duty_rate": 20,
            "unit_price": 12.50,
            "subtotal": 1250.00
        }}
    ]
    IMPORTANT: Return ONLY the JSON array. No markdown code blocks.
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            text = response.json()['candidates'][0]['content']['parts'][0]['text']
            
            # 【增强】更暴力的 JSON 提取逻辑
            try:
                # 找到第一个 [ 和 最后一个 ]
                start_idx = text.find('[')
                end_idx = text.rfind(']') + 1
                if start_idx != -1 and end_idx != -1:
                    json_str = text[start_idx:end_idx]
                    return json.loads(json_str)
                else:
                    st.error(f"AI Output Format Error: {text[:100]}...") # 打印出来看看
                    return []
            except json.JSONDecodeError:
                st.error("Failed to decode JSON from AI.")
                return []
        else:
            st.error(f"API Error {response.status_code} (Model: {model_name})")
            return []
    except Exception as e:
        st.error(f"System Error: {str(e)}")
        return []

def calculate_landed_cost(df, exchange_rate, port_fees, transport_fees, other_fees):
    # 数据清洗，防止非数字导致崩溃
    for col in ['quantity', 'unit_price', 'duty_rate']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 1. FOB Value
    df['FOB_USD'] = df['quantity'] * df['unit_price']
    df['FOB_ZAR'] = df['FOB_USD'] * exchange_rate
    
    # 2. Duty
    df['Duty_Amt_ZAR'] = df['FOB_ZAR'] * (df['duty_rate'] / 100)
    
    # 3. VAT (South Africa: ATV = FOB * 1.1 + Duty)
    df['ATV_ZAR'] = (df['FOB_ZAR'] * 1.1) + df['Duty_Amt_ZAR']
    df['VAT_Amt_ZAR'] = df['ATV_ZAR'] * 0.15
    
    # 4. Line Total
    df['Total_Line_Cost_ZAR'] = df['FOB_ZAR'] + df['Duty_Amt_ZAR'] + df['VAT_Amt_ZAR']
    
    summary = {
        "Total_FOB_USD": df['FOB_USD'].sum(),
        "Total_FOB_ZAR": df['FOB_ZAR'].sum(),
        "Total_Duty_ZAR": df['Duty_Amt_ZAR'].sum(),
        "Total_VAT_ZAR": df['VAT_Amt_ZAR'].sum(),
        "Grand_Total_Cost_ZAR": df['Total_Line_Cost_ZAR'].sum() + port_fees + transport_fees + other_fees
    }
    
    return df, summary

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>🚢 Import Master | 进口成本精算师</h2>
    <p>Upload Packing List -> Auto-Pricing -> Duty & VAT Calculation</p>
</div>
""", unsafe_allow_html=True)

# === 侧边栏 ===
with st.sidebar:
    st.header("⚙️ Settings")
    target_usd = st.number_input("Target Invoice Total (USD)", value=15000.0, step=100.0)
    ex_rate = st.number_input("USD to ZAR Rate", value=18.50, step=0.1)
    
    st.subheader("Local Fees (ZAR)")
    fee_port = st.number_input("Port Charges", value=5000.0)
    fee_trans = st.number_input("Inland Transport", value=8000.0)
    fee_other = st.number_input("Agency Fees", value=2500.0)

# === 主界面 ===
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📄 Upload Packing List")
    uploaded_file = st.file_uploader("Upload Image/PDF", type=['png', 'jpg', 'jpeg', 'pdf'])
    
    if uploaded_file and st.button("🚀 Generate Draft & Calculate"):
        with st.spinner("AI is analyzing file & checking models..."):
            raw_data = analyze_packing_list(uploaded_file, target_usd)
            
            if raw_data:
                st.session_state['import_data'] = pd.DataFrame(raw_data)
                st.success("Analysis Complete!")
            # 如果失败，上面函数内部会打印具体的红色报错信息，不再只是 "Failed"

# === 结果展示 ===
if 'import_data' in st.session_state:
    df = st.session_state['import_data']
    
    st.divider()
    st.subheader("🛠️ 货物明细 (Data Editor)")
    edited_df = st.data_editor(
        df,
        column_config={
            "description": "Item Description",
            "quantity": "Qty",
            "hs_code": "HS Code",
            "duty_rate": st.column_config.NumberColumn("Duty %"),
            "unit_price": st.column_config.NumberColumn("Unit Price ($)", format="$%.2f"),
        },
        num_rows="dynamic",
        use_container_width=True
    )
    
    final_df, summary = calculate_landed_cost(edited_df, ex_rate, fee_port, fee_trans, fee_other)
    
    st.divider()
    st.subheader("💰 Cost Analysis (落地成本)")
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Invoice (USD)", f"${summary['Total_FOB_USD']:,.2f}")
    m2.metric("Duty (ZAR)", f"R {summary['Total_Duty_ZAR']:,.2f}")
    m3.metric("VAT (ZAR)", f"R {summary['Total_VAT_ZAR']:,.2f}")
    m4.metric("Grand Total (ZAR)", f"R {summary['Grand_Total_Cost_ZAR']:,.2f}", delta="All Inclusive")
    
    st.subheader("📥 Downloads")
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("📄 Commercial Invoice (CSV)", final_df.to_csv(index=False).encode('utf-8'), "Invoice.csv")
    with c2:
        st.download_button("📊 Costing Sheet (CSV)", final_df.to_csv(index=False).encode('utf-8'), "Costing.csv")
