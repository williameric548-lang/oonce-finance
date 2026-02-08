import streamlit as st
import pandas as pd
from duckduckgo_search import DDGS
import datetime
import requests
import json
import random

# --- 1. 安全配置 ---
try:
    # 自动清洗空格，防止 400 错误
    API_KEY = st.secrets["GEMINI_KEY"].strip()
except Exception:
    st.error("🚨 未检测到 API Key！请在 Streamlit 后台 Secrets 里配置 GEMINI_KEY。")
    st.stop()

st.set_page_config(page_title="News Agent", layout="wide", page_icon="📰")

# --- 2. CSS 美化 ---
st.markdown("""
<style>
    .header-box {
        background: linear-gradient(135deg, #07c160 0%, #059669 100%);
        padding: 20px; border-radius: 10px; color: white; margin-bottom: 20px;
    }
    .tag-official { background-color: #d32f2f; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
    .tag-media { background-color: #1976d2; color: white; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    """自动寻找可用的 Gemini 模型"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            # 策略：优先找 flash，找不到用 pro
            for model in data.get('models', []):
                name = model['name'].replace('models/', '')
                if 'flash' in name: return name
            return "gemini-pro"
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
            return None, f"API Error {response.status_code}: {response.text}"
    except Exception as e: return None, str(e)

def search_news_comprehensive(topics, selected_media, check_embassy):
    results = []
    ddgs = DDGS()
    
    # --- A. 搜索主流媒体新闻 ---
    # 媒体域名映射表
    media_map = {
        "Business Day": "site:businesslive.co.za",
        "Sunday Times": "site:timeslive.co.za",
        "Daily Sun": "site:snl24.com",
        "The Star": "site:iol.co.za"
    }
    
    # 构建 site:xxx OR site:yyy 的查询字符串
    media_filter = ""
    if selected_media:
        filters = [media_map[m] for m in selected_media if m in media_map]
        if filters:
            media_filter = "(" + " OR ".join(filters) + ")"

    status_text = st.empty()
    status_text.text("🔍 正在扫描主流媒体...")
    
    for topic in topics:
        try:
            # 查询词示例：South Africa Crime news (site:iol.co.za OR site:businesslive.co.za)
            query = f"South Africa {topic} news {media_filter}"
            # 搜索最近 24 小时
            search_res = list(ddgs.news(keywords=query, region="za-en", timelimit="d", max_results=2))
            for res in search_res:
                results.append({
                    "type": "NEWS",
                    "category": topic,
                    "title": res['title'],
                    "snippet": res['body'],
                    "source": res['source'],
                    "url": res['url']
                })
        except: pass

    # --- B. 搜索使领馆公告 (官方雷达) ---
    if check_embassy:
        status_text.text("🇨🇳 正在扫描中国驻南非使领馆公告...")
        # 针对四个主要使领馆的域名进行精准搜索
        embassy_queries = [
            "site:za.china-embassy.gov.cn notice",             # 驻南非大使馆
            "site:johannesburg.china-consulate.gov.cn notice", # 约堡总领馆
            "site:durban.china-consulate.gov.cn notice",       # 德班总领馆
            "site:capetown.china-consulate.gov.cn notice"      # 开普敦总领馆
        ]
        
        for q in embassy_queries:
            try:
                # 搜索过去一周 (w) 的变动，因为公告频率较低
                # 使用 text 搜索以获得更精准的网页匹配
                search_res = list(ddgs.text(keywords=q, region="za-en", timelimit="w", max_results=1))
                for res in search_res:
                    results.append({
                        "type": "EMBASSY",
                        "category": "领事提醒",
                        "title": res['title'],
                        "snippet": res['body'],
                        "source": "中国驻南非使领馆",
                        "url": res['href']
                    })
            except: pass
            
    status_text.empty() # 清空提示
    return results

def get_history_fun_fact():
    """生成历史趣闻"""
    prompt = """
    Generate a concise, interesting "Fun Fact" or "On This Day" story about South African history.
    It could be about Gold Rush, Nelson Mandela, Zulu Kingdom, or Cape Town history.
    Max 80 words.
    """
    fact, _ = get_gemini_response(prompt)
    return fact if fact else "Did you know? South Africa is the only country in the world to have hosted the Soccer, Cricket and Rugby World Cup!"

def generate_viral_article(news_data, history_fact):
    if not news_data: return None, "未找到任何数据，无法生成文章。"

    # 数据分拣：将使馆公告提取出来
    news_text = ""
    embassy_text = ""
    
    for idx, item in enumerate(news_data):
        line = f"[{item['category']}] {item['title']}: {item['snippet']} (Source: {item['source']})\n"
        if item['type'] == 'EMBASSY':
            embassy_text += "🚨 " + line
        else:
            news_text += f"• " + line

    prompt = f"""
    You are the Chief Editor of "OONCE South Africa Daily" (OONCE南非日报).
    Task: Write a viral WeChat Official Account article for Chinese expats in SA.
    
    Input Data:
    [OFFICIAL EMBASSY NOTICES (MUST BE TOP PRIORITY)]:
    {embassy_text}
    
    [GENERAL NEWS]:
    {news_text}
    
    [HISTORY FUN FACT]:
    {history_fact}
    
    Requirements:
    1. **Language**: Chinese (Simplified).
    2. **Tone**: Professional yet engaging, Helpful, Alert. Use emojis appropriately.
    3. **Structure**:
       - **Headline**: Must be Clickbait/Urgent (e.g., "紧急！使馆发布最新提醒！" or "约堡今日大堵车？").
       - **Part 1: 🚨 官方通告 (Priority)**: Summarize embassy notices first. If none, explicitly say "今日无重要领事提醒".
       - **Part 2: 📰 南非要闻**: Summarize general news. Group by topic.
       - **Part 3: 📜 历史上的今天**: Translate the fun fact into a short interesting story.
       - **Ending**: "关注OONCE，南非生活不迷路。"
    """
    
    return get_gemini_response(prompt)

# --- 4. 页面布局 ---

st.markdown("""
<div class="header-box">
    <h2>📰 News Agent | 南非华人日报生成器</h2>
    <p>集成主流媒体 + 使领馆公告 + 历史趣闻</p>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🛠️ 配置控制台")
    
    st.subheader("1. 关注话题")
    topics = st.multiselect(
        "Topics",
        ["Immigration/Visa", "Crime/Safety", "Joburg Traffic", "Loadshedding", "Rand/Exchange Rate", "Lifestyle/Food"],
        default=["Immigration/Visa", "Crime/Safety"]
    )
    
    st.subheader("2. 重点媒体源 (Media)")
    st.info("将优先搜索以下媒体:")
    target_media = st.multiselect(
        "Select Media",
        ["Business Day", "Sunday Times", "Daily Sun", "The Star"],
        default=["Business Day", "The Star"]
    )
    
    st.subheader("3. 官方雷达 (Official)")
    check_embassy = st.checkbox("扫描中国驻南非使领馆公告", value=True)
    
    st.markdown("---")
    
    if st.button("🔄 开始全网扫描 (Scan)"):
        with st.spinner("🕵️‍♂️ 正在连接 DuckDuckGo 搜索网络..."):
            # 1. 搜新闻 + 公告
            results = search_news_comprehensive(topics, target_media, check_embassy)
            st.session_state['scan_results'] = results
            
            # 2. 生成历史趣闻
            history = get_history_fun_fact()
            st.session_state['history_fact'] = history
            
            if results:
                st.success(f"扫描完成！获取 {len(results)} 条资讯。")
            else:
                st.warning("未搜索到相关资讯，请检查网络或放宽条件。")

# === 主界面 ===

if 'scan_results' in st.session_state:
    st.subheader("📡 数据源概览 (Data Source)")
    
    # 历史趣闻卡片
    if 'history_fact' in st.session_state:
        with st.container(border=True):
            st.markdown(f"**📜 今日历史趣闻素材:** {st.session_state['history_fact']}")

    st.write("") # 空行

    # 新闻列表
    with st.expander("📄 查看抓取到的详细新闻列表", expanded=True):
        for item in st.session_state['scan_results']:
            col1, col2 = st.columns([1, 4])
            with col1:
                if item['type'] == 'EMBASSY':
                    st.markdown('<span class="tag-official">🏛️ 官方公告</span>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<span class="tag-media">📰 {item["category"]}</span>', unsafe_allow_html=True)
            with col2:
                st.markdown(f"**{item['title']}**")
                st.caption(f"Source: {item['source']} | [原文链接]({item['url']})")
                st.divider()

    st.write("")
    
    if st.button("🚀 生成公众号文章 (Generate Article)"):
        with st.spinner("✍️ AI 正在排版、翻译、润色..."):
            article, err = generate_viral_article(
                st.session_state['scan_results'], 
                st.session_state.get('history_fact', '')
            )
            
            if article:
                st.session_state['final_article_v4'] = article
                st.balloons() # 成功撒花
            else:
                st.error(f"生成失败: {err}")

# === 结果展示 ===
if 'final_article_v4' in st.session_state:
    st.markdown("### 📱 微信预览模式")
    
    with st.container(border=True):
        # 模拟微信公众号头部
        st.caption(f"OONCE南非资讯 • {datetime.date.today().strftime('%Y-%m-%d')}")
        st.markdown(st.session_state['final_article_v4'])
    
    st.success("✅ 文章已生成！请长按或全选上方内容，直接复制到微信公众号编辑器。")
