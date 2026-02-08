# ... (前面的 CSS 和 Header 不变)

st.markdown("""
<div class="main-header">
    <h1>🏭 OONCE Enterprise Suite</h1>
    <p>Integrated Intelligent Business Automation System</p>
</div>
""", unsafe_allow_html=True)

# 第一行
c1, c2 = st.columns(2)

with c1:
    st.markdown("""
    <div class="card">
        <span class="icon">💰</span>
        <h3>Invoice Manager</h3>
        <p>OCR Recognition | Auto-Accounting</p>
        <p><i>Go to sidebar <b>Page 1</b></i></p>
    </div>
    """, unsafe_allow_html=True)

with c2:
    st.markdown("""
    <div class="card" style="border-top-color: #1e3c72;">
        <span class="icon">🚢</span>
        <h3>Import Master</h3>
        <p>Landed Cost | Customs Pricing</p>
        <p><i>Go to sidebar <b>Page 2</b></i></p>
    </div>
    """, unsafe_allow_html=True)

st.write("") # 空一行

# 第二行
c3, c4 = st.columns(2)

with c3:
    st.markdown("""
    <div class="card" style="border-top-color: #ff9800;">
        <span class="icon">🏗️</span>
        <h3>Project Quoter</h3>
        <p>Engineering Quote | Superlink Logistics</p>
        <p><i>Go to sidebar <b>Page 3</b></i></p>
    </div>
    """, unsafe_allow_html=True)

with c4:
    st.markdown("""
    <div class="card" style="border-top-color: #07c160;">
        <span class="icon">📰</span>
        <h3>News Agent</h3>
        <p>Viral Article Generator | SA Headlines</p>
        <p><i>Go to sidebar <b>Page 4</b></i></p>
    </div>
    """, unsafe_allow_html=True)

# ... (底部 Footer)
