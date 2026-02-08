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
    }
    .card:hover {
        transform: translateY(-5px);
    }
    .card h3 { color: #333; }
    .card p { color: #666; }
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
        <h1>💰</h1>
        <h3>Invoice Manager</h3>
        <p>OCR Recognition | Auto-Accounting | Deduplication</p>
        <p><i>Go to sidebar <b>Pag 1</b> to access</i></p>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown("""
    <div class="card" style="border-top-color: #1e3c72;">
        <h1>🚢</h1>
        <h3>Import Master</h3>
        <p>Landed Cost | Customs Pricing | Cashflow</p>
        <p><i>Go to sidebar <b>Page 2</b> to access</i></p>
    </div>
    """, unsafe_allow_html=True)

with c3:
    st.markdown("""
    <div class="card" style="border-top-color: #d32f2f;">
        <h1>🚧</h1>
        <h3>Coming Soon</h3>
        <p>The 3rd Innovation Tool</p>
        <p><i>Under Construction...</i></p>
    </div>
    """, unsafe_allow_html=True)

st.divider()
st.caption("System Status: Online | Powered by Gemini AI | Version 2.0")
