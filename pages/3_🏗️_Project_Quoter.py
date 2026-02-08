import streamlit as st
import pandas as pd
import requests
import json
import math
import base64
import re

# --- 1. 全局配置 ---
try:
    API_KEY = st.secrets["GEMINI_KEY"]
except:
    API_KEY = "AIzaSyA0esre-3yI-sXogx-GWtbNC6dhRw2LzVE"

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
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 优先找 Pro (推理能力强)
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'pro' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 兜底 Flash
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
    except: pass
    return "gemini-1.5-flash"

def analyze_project_list(uploaded_file):
    model_name = get_available_model()
    file_ext = uploaded_file.name.lower().split('.')[-1]
    
    # 通用 Prompt
    prompt_base = """
    You are an expert Quantity Surveyor and Logistics Manager.
    Task: Analyze the Project Product List.
    
    Requirements:
    1. **Extract/Read**: Item Name, Specification/Model, Quantity.
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

    payload = {}
    
    # === 分支 A: 处理 Excel (xlsx, xls) ===
    if file_ext in ['xlsx', 'xls']:
        try:
            # 读取 Excel 内容转为字符串
            df = pd.read_excel(uploaded_file)
            # 将 DataFrame 转换为 CSV 格式的字符串，喂给 AI
            excel_text = df.to_string(index=False)
            
            full_prompt = prompt_base + f"\n\n[DATA FROM UPLOADED EXCEL FILE]:\n{excel_text}"
            payload = {"contents": [{"parts": [{"text": full_prompt}]}]}
            
        except Exception as e:
            return [], f"Excel Read Error: {str(e)}"

    # === 分支 B: 处理 图片/PDF ===
    else:
        mime_type = "image/jpeg"
        if file_ext == 'pdf': mime_type = "application/pdf"
        
        bytes_data = uploaded_file.getvalue()
        base64_data = base64.b64encode(bytes_data).decode('utf-8')
        
        payload = {"contents": [{"parts": [{"text": prompt_base}, {"inline_data": {"mime_type": mime_type, "data": base64_data}}]}]}

    # === 发送请求 ===
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            res_json = response.json()
            if 'candidates' not in res_json: return [], "No content returned."
            text = res_json['candidates'][0]['content']['parts'][0]['text']
            
            # 提取 JSON
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                return json.loads(match.group(0)), None
            else:
                return [], text # 返回原始文本用于调试
        else:
            return [], f"API Error {response.status_code}"
    except Exception as e:
        return [], str(e)

def calculate_logistics_and_price(df, freight_rate_per_ton):
    # 1. 清洗数据
    for col in ['quantity', 'china_price', 'sa_price', 'weight_kg', 'volume_m3']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # 2. 定价逻辑：如果 SA 价格不存在或为 0，则用 China * 2.5
    def get_final_price(row):
        if row['sa_price'] > 0:
            return row['sa_price'] 
        else:
            return row['china_price'] * 2.5

    df['final_unit_price'] = df.apply(get_final_price, axis=1)
    df['subtotal_product'] = df['quantity'] * df['final_unit_price']

    # 3. 物流计算 (Superlink)
    # 前车: 6m (36m3), 后车: 12m (72m3) -> 108m3 理论 -> 90%装载率 -> ~97m3
    # 限重: 34T
    
    total_weight_kg = (df['quantity'] * df['weight_kg']).sum()
    total_volume_m3 = (df['quantity'] * df['volume_m3']).sum()
    
    truck_capacity_weight = 34000.0
    truck_capacity_volume = 108.0 * 0.9 
    
    # 车辆数量 = Max(重量需求, 体积需求)
    trucks_by_weight = total_weight_kg / truck_capacity_weight
    trucks_by_volume = total_volume_m3 / truck_capacity_volume
    num_trucks = math.ceil(max(trucks_by_weight, trucks_by_volume))
    if num_trucks < 1: num_trucks = 1
    
    # 4. 运费计算 (每车运费 = 单价/吨 * 34吨)
    # 注意：这里假设无论是否装满34吨，包车都是按34吨算钱（或按车次算）
    # 您的需求是：车的单价默认值为 $500 x 34吨
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
    <h2>🏗️ Project Quoter | 工程预算 & 物流调度</h2>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🚛 Logistics Settings")
    st.info("Superlink Standard: 6m+12m Links\nMax Height: 2.5m | Max Load: 34T")
    freight_rate = st.number_input("Freight Rate ($/Ton)", value=500.0, step=10.0, help="默认运费单价")

col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📄 Upload Project List (支持 Excel)")
    # 【核心修改】支持 xlsx, xls
    uploaded_file = st.file_uploader("Upload Image/PDF/Excel", type=['png', 'jpg', 'jpeg', 'pdf', 'xlsx', 'xls'])
    
    if uploaded_file and st.button("🚀 Analyze & Quote"):
        with st.spinner("AI is calculating prices and logistics..."):
            raw_data, debug_msg = analyze_project_list(uploaded_file)
            
            if raw_data:
                st.session_state['project_data'] = pd.DataFrame(raw_data)
                st.success("Analysis Complete!")
            else:
                st.error("Analysis Failed.")
                if debug_msg:
                    with st.expander("Show Error Details"):
                        st.text(debug_msg)

if 'project_data' in st.session_state:
    df = st.session_state['project_data']
    
    st.divider()
    st.subheader("🛠️ 报价明细 (Data Editor)")
    
    edited_df = st.data_editor(
        df,
        column_config={
            "item": "Item",
            "spec": "Spec",
            "quantity": "Qty",
            "china_price": st.column_config.NumberColumn("China ($)", help="中国出厂价"),
            "sa_price": st.column_config.NumberColumn("SA ($)", help="南非市价 (0=无货)"),
            "weight_kg": st.column_config.NumberColumn("Kg/Unit"),
            "volume_m3": st.column_config.NumberColumn("CBM/Unit"),
            "final_unit_price": st.column_config.NumberColumn("Quote ($)", disabled=True),
        },
        num_rows="dynamic",
        use_container_width=True
    )
    
    final_df, summary = calculate_logistics_and_price(edited_df, freight_rate)
    
    st.divider()
    
    # 车辆调度结果
    st.subheader("🚛 Logistics Plan")
    t1, t2, t3, t4 = st.columns(4)
    with t1:
        st.markdown(f"""
        <div class="truck-card">
            <h1>{int(summary['num_trucks'])} 🚛</h1>
            <p>Superlinks Required</p>
        </div>
        """, unsafe_allow_html=True)
    with t2:
        st.metric("Total Weight", f"{summary['total_weight_ton']:,.2f} Tons")
        st.metric("Total Volume", f"{summary['total_volume_cbm']:,.2f} CBM")
    with t3:
        st.metric("Truck Unit Cost", f"${summary['truck_cost_unit']:,.2f}", help=f"{freight_rate} x 34T")
    with t4:
        st.metric("Total Freight", f"${summary['total_freight']:,.2f}")

    st.divider()
    
    # 总价结果
    st.subheader("💰 Final Quotation")
    m1, m2, m3 = st.columns(3)
    m1.markdown(f"<div class='metric-box'><h4>Product Subtotal</h4><h2>${summary['total_product_value']:,.2f}</h2></div>", unsafe_allow_html=True)
    m2.markdown(f"<div class='metric-box'><h4>Freight Cost</h4><h2>${summary['total_freight']:,.2f}</h2></div>", unsafe_allow_html=True)
    m3.markdown(f"<div class='metric-box' style='border-left-color: #d32f2f;'><h4>Grand Total</h4><h2 style='color:#d32f2f'>${summary['grand_total']:,.2f}</h2></div>", unsafe_allow_html=True)

    csv = final_df.to_csv(index=False).encode('utf-8')
    st.download_button("📄 Download Project Quote (CSV)", csv, "Project_Quote.csv")
