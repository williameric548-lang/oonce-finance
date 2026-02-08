import streamlit as st
import pandas as pd
import requests
import json
import math
import base64
import re

# --- 1. 安全配置 ---
# 厂长，这次我们只从 Secrets 读取，绝对不写死在代码里！
# 这样 GitHub 怎么扫描都扫不到，Google 就不会封您的号了。
try:
    API_KEY = st.secrets["GEMINI_KEY"]
except Exception:
    st.error("🚨 未检测到 API Key！请在 Streamlit 后台 Settings -> Secrets 中配置 GEMINI_KEY。")
    st.stop()

st.set_page_config(page_title="Project Quoter", layout="wide", page_icon="🏗️")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .stApp { background-color: #f4f6f9; }
    .header-box {
        background: linear-gradient(135deg, #2c3e50 0%, #4ca1af 100%);
        padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .truck-card {
        background-color: #fff; border: 2px solid #ff9800; border-radius: 10px;
        padding: 15px; text-align: center; color: #333;
    }
    .metric-box {
        background: white; padding: 15px; border-radius: 8px;
        border-left: 5px solid #2c3e50; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    div[data-testid="stDataFrame"] { width: 100%; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    return "gemini-1.5-flash"

def analyze_project_list(uploaded_file):
    model_name = get_available_model()
    file_ext = uploaded_file.name.lower().split('.')[-1]
    
    prompt_base = """
    You are an expert Quantity Surveyor.
    Task: Analyze Project List.
    Requirements:
    1. Extract: Item, Spec, Quantity.
    2. Price (USD): Estimate `china_price` and `sa_price` (0 if unavailable).
    3. Logistics: Estimate `weight_kg` and `volume_m3` per unit.
    Output JSON ONLY:
    [
      {"item": "Item A", "spec": "Spec", "quantity": 10, "china_price": 5.0, "sa_price": 0, "weight_kg": 1, "volume_m3": 0.01}
    ]
    """

    payload = {}
    if file_ext in ['xlsx', 'xls']:
        try:
            df = pd.read_excel(uploaded_file)
            excel_text = df.to_string(index=False)
            payload = {"contents": [{"parts": [{"text": prompt_base + f"\nData:\n{excel_text}"}]}]}
        except Exception as e: return [], f"Excel Error: {str(e)}"
    else:
        mime_type = "image/jpeg"
        if file_ext == 'pdf': mime_type = "application/pdf"
        bytes_data = uploaded_file.getvalue()
        base64_data = base64.b64encode(bytes_data).decode('utf-8')
        payload = {"contents": [{"parts": [{"text": prompt_base}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return [], "No content returned"
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match: return json.loads(match.group(0)), None
            else: return [], text
        else: return [], f"API Error {response.status_code}"
    except Exception as e: return [], str(e)

def calculate_logistics_and_price(df, freight_rate, china_markup, profit_margin):
    for col in ['quantity', 'china_price', 'sa_price', 'weight_kg', 'volume_m3']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    def get_strategy_price(row):
        if row['sa_price'] > 0: return row['sa_price']
        else: return row['china_price'] * china_markup
    
    df['base_price'] = df.apply(get_strategy_price, axis=1)
    df['final_unit_price'] = df['base_price'] * (1 + profit_margin / 100.0)
    df['subtotal_product'] = df['quantity'] * df['final_unit_price']

    total_weight = (df['quantity'] * df['weight_kg']).sum()
    total_volume = (df['quantity'] * df['volume_m3']).sum()
    
    num_trucks = math.ceil(max(total_weight / 34000.0, total_volume / (108.0 * 0.9)))
    if num_trucks < 1: num_trucks = 1
    
    total_freight = num_trucks * (freight_rate * 34.0)
    grand_total = df['subtotal_product'].sum() + total_freight

    summary = {
        "total_product_value": df['subtotal_product'].sum(),
        "num_trucks": num_trucks,
        "total_freight": total_freight,
        "grand_total": grand_total,
        "total_weight": total_weight / 1000.0,
        "total_volume": total_volume
    }
    return df, summary

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>🏗️ Project Quoter V3.2 (Secure Edition)</h2>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("💰 Pricing Strategy")
    china_markup = st.number_input("China Markup Factor", value=2.5, step=0.1)
    profit_margin = st.slider("Additional Profit Margin (%)", 0, 100, 30)
    st.divider()
    st.header("🚛 Logistics")
    freight_rate = st.number_input("Freight ($/Ton)", value=500.0)

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📄 Upload Project List")
    uploaded_file = st.file_uploader("Upload Excel/Image/PDF", type=['xlsx', 'xls', 'png', 'jpg', 'pdf'])
    
    if uploaded_file and st.button("🚀 Analyze & Quote"):
        with st.spinner("AI is Calculating..."):
            raw_data, err = analyze_project_list(uploaded_file)
            if raw_data:
                st.session_state['project_data'] = pd.DataFrame(raw_data)
                st.success("Done!")
            else:
                st.error("Failed")
                if err: st.text(err)

if 'project_data' in st.session_state:
    df = st.session_state['project_data']
    st.divider()
    st.subheader(f"🛠️ Quote Builder (Margin: {profit_margin}%)")
    
    final_df, summary = calculate_logistics_and_price(df, freight_rate, china_markup, profit_margin)
    
    edited_df = st.data_editor(
        final_df,
        column_config={
            "item": "Item", "spec": "Spec", "quantity": "Qty",
            "china_price": st.column_config.NumberColumn("China Cost"),
            "sa_price": st.column_config.NumberColumn("SA Market"),
            "base_price": st.column_config.NumberColumn("Base ($)", disabled=True),
            "final_unit_price": st.column_config.NumberColumn("Unit Quote ($)", format="$%.2f", disabled=True),
            "subtotal_product": st.column_config.NumberColumn("Subtotal ($)", format="$%.2f", disabled=True),
            "weight_kg": st.column_config.NumberColumn("Kg", disabled=True),
            "volume_m3": st.column_config.NumberColumn("CBM", disabled=True),
        },
        num_rows="dynamic", use_container_width=True
    )
    
    st.divider()
    st.subheader("💰 Final Quotation Overview")
    
    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f"<div class='metric-box'><h4>Product Subtotal</h4><h2>${summary['total_product_value']:,.2f}</h2></div>", unsafe_allow_html=True)
    with c2: st.markdown(f"<div class='metric-box'><h4>Freight Cost</h4><h2>${summary['total_freight']:,.2f}</h2><p>{int(summary['num_trucks'])}x Superlinks</p></div>", unsafe_allow_html=True)
    with c3: st.markdown(f"<div class='metric-box' style='border-left-color: #d32f2f;'><h4>Grand Total</h4><h2 style='color:#d32f2f'>${summary['grand_total']:,.2f}</h2></div>", unsafe_allow_html=True)

    csv = final_df.to_csv(index=False).encode('utf-8')
    st.download_button("📄 Download Full Quote (CSV)", csv, "Project_Quote.csv")
