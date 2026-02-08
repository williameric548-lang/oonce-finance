import streamlit as st
import pandas as pd
from duckduckgo_search import DDGS
import datetime
import requests
import json
import re

# --- 1. 安全配置 ---
try:
    API_KEY = st.secrets["GEMINI_KEY"].strip()
except Exception:
    st.error("🚨 未检测到 API Key！请配置 Secrets。")
    st.stop()

st.set_page_config(page_title="News Agent", layout="wide", page_icon="📰")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .header-box {
        background: linear-gradient(135deg, #07c160 0%, #059669 100%);
        padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    # 自动寻路：找能用的模型
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 1. 找 Flash
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 2. 找 Pro
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'pro' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 3. 兜底
            for model in data.get('models', []):
                if 'generateContent' in model.get('supportedGenerationMethods', []):
                    return model['name'].replace('models/', '')
    except: pass
    return "gemini-pro"

def get_gemini_response(prompt):
    model_name = get_available_model()
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'], None
        else:
            return None, f"API Error {response.status_code} ({model_name}): {response.text}"
    except Exception as e: return None, str(e)

def search_sa_news(topics):
    results = []
    try:
        ddgs = DDGS()
        for topic in topics:
            query = f"South Africa {topic} news latest"
            # 搜索最近一天
            search_res = list(ddgs.news(keywords=query, region="za-en", timelimit="d", max_results=2))
            for res in search_res:
                results.append({
                    "topic": topic,
                    "title": res['title'],
                    "snippet": res['body'],
                    "source": res['source'],
                    "url": res['url']
                })
    except Exception as e: st.error(f"Search Error: {e}")
    return results

def generate_wechat_article(news_items):
    if not news_items: return None, "没有新闻数据"

    news_text = ""
    for idx, item in enumerate(news_items):
        news_text += f"{idx+1}. [{item['topic']}] {item['title']}: {item['snippet']} (Source: {item['source']})\n"

    prompt = f"""
    You are a professional WeChat Official Account Editor for Chinese expats in South Africa.
    Task: Write a viral daily news summary article.
    
    Requirements:
    1. **Language**: Chinese (Simplified).
    2. **Tone**: Urgent, helpful, slightly sensational (Shocking/Important). Use emojis 🚨💰.
    3. **Structure**:
       - **Headline**: Catchy! (e.g. "Attention! Home Affairs New Rule!").
       - **Intro**: Greeting + Date + Exchange Rate.
       - **Body**: Translate news. Highlight impact on Chinese community.
       - **Fun**: Recommend a random popular SA dish/spot if no food news.
       - **Ending**: "Stay safe, follow OONCE for more."
    
    Input News:
    {news_text}
    """
    return get_gemini_response(prompt)

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>📰 News Agent | 南非头条爆文生成器</h2>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🔍 选题设置")
    topics = st.multiselect(
        "选择关注领域",
        ["Immigration/Home Affairs", "Crime/Safety", "Johannesburg Traffic", "Eskom/Loadshedding", "Exchange Rate", "Food/Lifestyle"],
        default=["Immigration/Home Affairs", "Crime/Safety"]
    )
    st.markdown("---")
    if st.button("🔄 1. 扫描全网新闻"):
        with st.spinner("🕵️‍♂️ 搜索中..."):
            news_data = search_sa_news(topics)
            if news_data:
                st.session_state['news_data'] = news_data
                st.success(f"抓取到 {len(news_data)} 条新闻！")
            else:
                st.warning("暂无相关新闻")

# === 主界面 ===

if 'news_data' in st.session_state:
    st.subheader("📡 原始素材 (Raw Data)")
    with st.expander("点击查看新闻列表", expanded=False):
        for item in st.session_state['news_data']:
            st.markdown(f"**[{item['topic']}]** [{item['title']}]({item['url']})")
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 2. AI 撰写公众号文章"):
            with st.spinner("✍️ Gemini 正在撰写..."):
                article, err = generate_wechat_article(st.session_state['news_data'])
                if article:
                    st.session_state['final_article'] = article
                    st.success("撰写完成！")
                else:
                    st.error("生成失败")
                    if err: st.code(err)

if 'final_article' in st.session_state:
    st.divider()
    st.subheader("📱 微信公众号预览")
    
    # 【核心修复】使用 st.container 来模拟卡片，不再嵌套 Markdown
    with st.container(border=True):
        st.caption(f"OONCE南非资讯 • {datetime.date.today().strftime('%Y-%m-%d')}")
        st.markdown(st.session_state['final_article'])
        
    st.info("💡 提示：点击右上角复制按钮，直接粘贴到微信后台即可！")
