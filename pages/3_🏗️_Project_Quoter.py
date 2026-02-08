import streamlit as st
import pandas as pd
import requests
import json
import math
import base64
import re

# --- 1. 全局配置 ---
# 依然从 Secrets 读取 Key，如果没有配置 secrets，请手动替换下面的字符串
# API_KEY = "AIzaSyA0esre-3yI-sXogx-GWtbNC6dhRw2LzVE" 
try:
    API_KEY = st.secrets["GEMINI_KEY"]
except:
    API_KEY = "AIzaSyA0esre-3yI-sXogx-GWtbNC6dhRw2LzVE" # 备用硬编码

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
    .stDataFrame { background-color: white; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    # 优先找 Pro 模型以获得更好的推理能力
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'pro' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
    except: pass
    return "gemini-1.5-flash"

def analyze_project_list(uploaded_file):
    model_name = get_available_model()
    
    mime_type = "image/jpeg"
    if uploaded_file.name.lower().endswith('.pdf'): mime_type = "application/pdf"
    
    bytes_data = uploaded_file.getvalue()
    base64_data = base64.b64encode(bytes_data).decode('utf-8')
    
    # 核心 Prompt：要求 AI 做很多估算工作
    prompt = """
    You are an expert Quantity Surveyor and Logistics Manager.
    Task: Analyze the Project Product List (Image/PDF).
    
    Requirements:
    1. **Extract**: Item Name, Specification/Model, Quantity.
    2. **Price Analysis (USD)**:
       - Estimate `china_price`: Average market price in China.
       - Estimate `sa_price`: Average market price in South Africa. (If unavailable/rare, set to 0).
    3. **Logistics Estimation**:
       - Estimate `weight_kg`: Weight per unit (in kg).
       - Estimate `volume_m3`: Volume per unit (in cubic meters).
    
    Output JSON ONLY:
    [
      {
        "item": "Solar Panel 550W",
        "spec": "2279x1134x35mm",
        "quantity": 500,
        "china_price": 85.00,
        "sa_price": 110.00,
        "weight_kg": 28.0,
        "volume_m3": 0.09
      }
    ]
    """
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return []
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match: return json.loads(match.group(0))
            else: return []
        else: return []
    except Exception as e: return []

def calculate_logistics_and_price(df, freight_rate_per_ton):
    # 1. 清洗数据
    for col in ['quantity', 'china_price', 'sa_price', 'weight_kg', 'volume_m3']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 2. 定价逻辑：如果 SA 价格不存在或为 0，则用 China * 2.5
    # 我们可以创建一个 'final_unit_price'
    def get_final_price(row):
        if row['sa_price'] > 0:
            return row['sa_price'] # 如果南非有市价，参考市价（或者您可以改为取两者最大值）
        else:
            return row['china_price'] * 2.5 # 否则用中国价格翻倍

    df['final_unit_price'] = df.apply(get_final_price, axis=1)
    df['subtotal_product'] = df['quantity'] * df['final_unit_price']

    # 3. 物流计算 (Superlink)
    # Superlink 规格:
    # 前车: 6m x 2.4m x 2.5m = 36 m3
    # 后车: 12m x 2.4m x 2.5m = 72 m3
    # 总容积: 108 m3 (保守估计打个9折装载率 -> 约 97 m3)
    # 总限重: 34,000 kg
    
    total_weight_kg = (df['quantity'] * df['weight_kg']).sum()
    total_volume_m3 = (df['quantity'] * df['volume_m3']).sum()
    
    truck_capacity_weight = 34000.0
    truck_capacity_volume = 108.0 * 0.9 # 90% 装载率
    
    # 需要几辆车？(取重量和体积需求的最大值)
    trucks_by_weight = total_weight_kg / truck_capacity_weight
    trucks_by_volume = total_volume_m3 / truck_capacity_volume
    num_trucks = math.ceil(max(trucks_by_weight, trucks_by_volume))
    
    if num_trucks < 1: num_trucks = 1 # 至少一辆
    
    # 4. 运费计算
    # 运费 = 车数 * (单价 $500 * 34吨)
    truck_cost_per_trip = freight_rate_per_ton * 34.0
    total_freight_cost = num_trucks * truck_cost_per_trip
    
    # 5. 总价
    total_project_value = df['subtotal_product'].sum() + total_freight_cost

    summary = {
        "total_product_value": df['subtotal_product'].sum(),
        "total_weight_ton": total_weight_kg / 1000.0,
        "total_volume_cbm": total_volume_m3,
        "num_trucks": num_trucks,
        "truck_cost_unit": truck_cost_per_trip,
        "total_freight": total_freight_cost,
        "grand_total": total_project_value
    }
    
    return df, summary

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>🏗️ Project Quoter | 工程预算与物流调度</h2>
</div>
""", unsafe_allow_html=True)

# === 侧边栏 ===
with st.sidebar:
    st.header("🚛 Logistics Settings")
    
    st.info("Superlink Standard: 6m+12m Links\nMax Height: 2.5m | Max Load: 34T")
    
    # 运费变量
    freight_rate = st.number_input("Freight Rate ($/Ton)", value=500.0, step=10.0, help="默认为 $500/吨")
    
    st.divider()
    st.subheader("Pricing Strategy")
    markup = st.slider("China Price Markup", 2.0, 4.0, 2.5, help="当南非无货时，中国价格乘以多少倍？默认2.5")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📄 Upload Project List (清单)")
    uploaded_file = st.file_uploader("Upload Image/PDF/Excel", type=['png', 'jpg', 'jpeg', 'pdf'])
    
    if uploaded_file and st.button("🚀 Analyze & Quote"):
        with st.spinner("AI is checking prices in China & SA, and calculating truck loads..."):
            raw_data = analyze_project_list(uploaded_file)
            if raw_data:
                st.session_state['project_data'] = pd.DataFrame(raw_data)
                st.success("Analysis Complete!")
            else:
                st.error("Failed to analyze. Please upload a clear image.")

if 'project_data' in st.session_state:
    df = st.session_state['project_data']
    
    st.divider()
    st.subheader("🛠️ 报价明细 (Quote Details)")
    
    # 数据编辑器
    edited_df = st.data_editor(
        df,
        column_config={
            "item": "Item Name",
            "spec": "Specification",
            "quantity": "Qty",
            "china_price": st.column_config.NumberColumn("China Price ($)", help="AI估算的中国出厂价"),
            "sa_price": st.column_config.NumberColumn("SA Market ($)", help="南非本地价 (0代表无货)"),
            "weight_kg": st.column_config.NumberColumn("Unit Kg", help="单件重量"),
            "volume_m3": st.column_config.NumberColumn("Unit CBM", help="单件体积"),
            "final_unit_price": st.column_config.NumberColumn("Quote Price ($)", disabled=True, help="系统生成的最终报价"),
        },
        num_rows="dynamic",
        use_container_width=True
    )
    
    # 实时计算
    final_df, summary = calculate_logistics_and_price(edited_df, freight_rate)
    
    st.divider()
    
    # === 结果展示区 ===
    
    # 1. 车辆调度卡片
    st.subheader("🚛 Logistics Plan (物流方案)")
    t1, t2, t3, t4 = st.columns(4)
    
    with t1:
        st.markdown(f"""
        <div class="truck-card">
            <h1>{int(summary['num_trucks'])} 🚛</h1>
            <p>Superlinks Required</p>
        </div>
        """, unsafe_allow_html=True)
        
    with t2:
        st.metric("Total Weight", f"{summary['total_weight_ton']:,.2f} Tons", help="总重量")
        st.metric("Total Volume", f"{summary['total_volume_cbm']:,.2f} CBM", help="总体积")
        
    with t3:
        st.metric("Truck Unit Cost", f"${summary['truck_cost_unit']:,.2f}", help=f"Single Truck Cost ({freight_rate} x 34T)")
        
    with t4:
        st.metric("Total Freight", f"${summary['total_freight']:,.2f}", help="总运费 = 车数 x 单车运费")

    st.divider()
    
    # 2. 总报价单
    st.subheader("💰 Final Quotation (总报价)")
    
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"<div class='metric-box'><h4>Product Subtotal</h4><h2>${summary['total_product_value']:,.2f}</h2></div>", unsafe_allow_html=True)
    with m2:
        st.markdown(f"<div class='metric-box'><h4>Freight Cost</h4><h2>${summary['total_freight']:,.2f}</h2></div>", unsafe_allow_html=True)
    with m3:
        st.markdown(f"<div class='metric-box' style='border-left-color: #d32f2f;'><h4>Grand Total</h4><h2 style='color:#d32f2f'>${summary['grand_total']:,.2f}</h2></div>", unsafe_allow_html=True)

    # 下载按钮
    csv = final_df.to_csv(index=False).encode('utf-8')
    st.download_button("📄 Download Project Quote (CSV)", csv, "Project_Quote.csv")
