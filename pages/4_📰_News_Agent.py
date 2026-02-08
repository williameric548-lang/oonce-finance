import streamlit as st
import pandas as pd
from duckduckgo_search import DDGS
import datetime
import requests
import json
import re

# --- 1. 安全配置 ---
try:
    # 自动清洗空格
    API_KEY = st.secrets["GEMINI_KEY"].strip()
except Exception:
    st.error("🚨 未检测到 API Key！请配置 Secrets。")
    st.stop()

st.set_page_config(page_title="News Agent", layout="wide", page_icon="📰")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .wechat-box {
        background-color: white; border: 1px solid #e7e7eb; padding: 20px;
        border-radius: 5px; box-shadow: 0 2px 10px rgba(0,0,0,0.05);
        font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    }
    .wechat-title { font-size: 22px; font-weight: 600; color: #333; margin-bottom: 10px; }
    .wechat-meta { font-size: 14px; color: #666; margin-bottom: 20px; }
    .wechat-content { font-size: 16px; line-height: 1.8; color: #333; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 (自动寻路版) ---

def get_available_model():
    """
    自动雷达：询问 API 到底有哪些模型可用，避免 404 错误。
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 策略 1: 优先找 Flash
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 策略 2: 其次找 Pro
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'pro' in name and 'generateContent' in model.get('supportedGenerationMethods', []):
                    return name
            # 策略 3: 有啥用啥
            for model in data.get('models', []):
                if 'generateContent' in model.get('supportedGenerationMethods', []):
                    return model['name'].replace('models/', '')
    except:
        pass
    return "gemini-pro" # 最后的兜底

def get_gemini_response(prompt):
    # 动态获取模型，不再写死 flash
    model_name = get_available_model()
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={API_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload), timeout=60)
        if response.status_code == 200:
            return response.json()['candidates'][0]['content']['parts'][0]['text'], None
        else:
            # 返回具体错误信息
            return None, f"API Error {response.status_code} ({model_name}): {response.text}"
    except Exception as e:
        return None, str(e)

def search_sa_news(topics):
    results = []
    try:
        ddgs = DDGS()
        for topic in topics:
            query = f"South Africa {topic} news latest"
            # 搜索最近一天的新闻
            search_res = list(ddgs.news(keywords=query, region="za-en", timelimit="d", max_results=2))
            for res in search_res:
                results.append({
                    "topic": topic,
                    "title": res['title'],
                    "snippet": res['body'],
                    "source": res['source'],
                    "url": res['url']
                })
    except Exception as e:
        st.error(f"News Search Error: {e}")
            
    return results

def generate_wechat_article(news_items):
    if not news_items: return None, "没有新闻数据输入"

    news_text = ""
    for idx, item in enumerate(news_items):
        news_text += f"{idx+1}. [{item['topic']}] {item['title']}: {item['snippet']} (Source: {item['source']})\n"

    prompt = f"""
    You are a professional WeChat Official Account Editor for the Chinese community in South Africa.
    Task: Write a viral daily news summary.
    Target: Chinese expats in SA.
    
    Requirements:
    1. **Tone**: Urgent, helpful, slightly sensational (Shocking/Important). Use emojis.
    2. **Language**: Chinese (Simplified).
    3. **Structure**:
       - **Catchy Title**: e.g. "Attention! New Home Affairs rule!".
       - **Intro**: Greetings, Exchange rate check.
       - **Body**: Translate core info to Chinese. Highlight impacts on Chinese people.
       - **Fun**: Recommend a random popular SA dish/spot if no food news.
    
    Input News Data:
    {news_text}
    """
    
    return get_gemini_response(prompt)

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box" style="background: linear-gradient(135deg, #07c160 0%, #059669 100%); padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;">
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
    if st.button("🔄 扫描全网新闻"):
        with st.spinner("🕵️‍♂️ 正在搜索各大南非媒体头条..."):
            news_data = search_sa_news(topics)
            if news_data:
                st.session_state['news_data'] = news_data
                st.success(f"抓取到 {len(news_data)} 条相关新闻！")
            else:
                st.warning("暂未搜到相关新闻，或者搜索服务繁忙。")

# === 主界面 ===

if 'news_data' in st.session_state:
    st.subheader("📡 原始素材 (Raw Data)")
    with st.expander("点击查看新闻列表", expanded=False):
        for item in st.session_state['news_data']:
            st.markdown(f"**[{item['topic']}]** [{item['title']}]({item['url']})")
            st.caption(f"Source: {item['source']}")
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🚀 AI 撰写公众号文章"):
            with st.spinner("✍️ Gemini 正在撰写... (请稍候 10-20秒)"):
                # 调用 AI
                article_content, err_msg = generate_wechat_article(st.session_state['news_data'])
                
                if article_content:
                    st.session_state['final_article'] = article_content
                    st.success("撰写完成！")
                else:
                    st.error("生成失败")
                    if err_msg:
                        st.code(err_msg, language="json")

if 'final_article' in st.session_state:
    st.subheader("📱 公众号预览")
    content = st.session_state['final_article']
    st.markdown(f"""
    <div class="wechat-box">
        <div class="wechat-content">
            {st.markdown(content)}
        </div>
    </div>
    """, unsafe_allow_html=True)
