import streamlit as st

st.set_page_config(
    page_title="OONCE Enterprise",
    page_icon="🏭",
    layout="wide"
)

# CSS 美化
st.markdown("""
<style>
    .main-header {
        text-align: center;
        padding: 50px;
        background: linear-gradient(135deg, #0F2027 0%, #203A43 50%, #2C5364 100%);
        color: white;
        border-radius: 15px;
        margin-bottom: 30px;
    }
    .card {
        background-color: white;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        text-align: center;
        border-top: 5px solid #059669;
        transition: transform 0.2s;
        height: 100%; /* 保证卡片高度一致 */
    }
    .card:hover {
        transform: translateY(-5px);
    }
    .card h3 { color: #333; margin-bottom: 10px; }
    .card p { color: #666; font-size: 14px; }
    .card .icon { font-size: 50px; margin-bottom: 10px; display: block; }
</style>
""", unsafe_allow_html=True)

# 头部欢迎区
st.markdown("""
<div class="main-header">
    <h1>🏭 OONCE Enterprise Suite</h1>
    <p>Integrated Intelligent Business Automation System</p>
</div>
""", unsafe_allow_html=True)

# 仪表盘/导航区
c1, c2, c3 = st.columns(3)

with c1:
    st.markdown("""
    <div class="card">
        <span class="icon">💰</span>
        <h3>Invoice Manager</h3>
        <p>OCR Recognition | Auto-Accounting | Deduplication</p>
        <br>
        <p><i>Go to sidebar <b>Page 1</b> to access</i></p>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown("""
    <div class="card" style="border-top-color: #1e3c72;">
        <span class="icon">🚢</span>
        <h3>Import Master</h3>
        <p>Landed Cost | Customs Pricing | Cashflow Analysis</p>
        <br>
        <p><i>Go to sidebar <b>Page 2</b> to access</i></p>
    </div>
    """, unsafe_allow_html=True)

with c3:
    # 这里更新了！从 Construction 变成了正式入口
    st.markdown("""
    <div class="card" style="border-top-color: #ff9800;">
        <span class="icon">🏗️</span>
        <h3>Project Quoter</h3>
        <p>Engineering Quote | Logistics Plan | Profit Calculator</p>
        <br>
        <p><i>Go to sidebar <b>Page 3</b> to access</i></p>
    </div>
    """, unsafe_allow_html=True)

st.divider()
st.caption("System Status: Online | Powered by Gemini AI | Version 3.0")
