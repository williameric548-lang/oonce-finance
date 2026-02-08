import streamlit as st
import pandas as pd
from duckduckgo_search import DDGS
import datetime
import requests
import json
import random

# --- 1. 安全配置 ---
try:
    # 自动清洗 Key 前后的空格，防止 400 错误
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
    .stButton>button { width: 100%; border-radius: 5px; height: 50px; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

# --- 3. 核心逻辑 ---

def get_available_model():
    """自动雷达：寻找可用的 Gemini 模型"""
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
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

def safe_search_news(ddgs, query, time_limit, max_results):
    """封装搜索函数，防止报错中断"""
    try:
        return list(ddgs.news(keywords=query, region="za-en", timelimit=time_limit, max_results=max_results))
    except:
        return []

def search_news_smart(topics, selected_media, check_embassy):
    results = []
    ddgs = DDGS()
    
    # 媒体域名映射
    media_map = {
        "Business Day": "site:businesslive.co.za",
        "Sunday Times": "site:timeslive.co.za",
        "Daily Sun": "site:snl24.com",
        "The Star": "site:iol.co.za"
    }
    
    # 构建媒体过滤串
    media_filter = ""
    if selected_media:
        filters = [media_map[m] for m in selected_media if m in media_map]
        if filters:
            media_filter = "(" + " OR ".join(filters) + ")"

    status_text = st.empty()
    status_text.text("🔍 正在启动智能搜索策略...")
    
    # --- 1. 搜索常规新闻 (三级降级策略) ---
    for topic in topics:
        # A. 严格模式 (指定媒体 + 24小时)
        query_a = f"South Africa {topic} news {media_filter}"
        raw_res = safe_search_news(ddgs, query_a, "d", 2)
        
        # B. 降级模式 (指定媒体 + 过去一周) - 如果A没结果
        if not raw_res and media_filter:
            # status_text.text(f"⚠️ {topic} 今日无指定媒体新闻，尝试搜索本周...")
            raw_res = safe_search_news(ddgs, query_a, "w", 2)
            
        # C. 保底模式 (全网媒体 + 过去一周) - 如果B也没结果
        if not raw_res:
            # status_text.text(f"⚠️ {topic} 指定媒体无结果，尝试全网搜索...")
            query_c = f"South Africa {topic} news"
            raw_res = safe_search_news(ddgs, query_c, "w", 2)

        # 存入结果
        for res in raw_res:
            results.append({
                "type": "NEWS",
                "category": topic,
                "title": res['title'],
                "snippet": res['body'],
                "source": res['source'],
                "url": res['url']
            })

    # --- 2. 搜索使领馆公告 ---
    if check_embassy:
        status_text.text("🇨🇳 正在扫描使领馆公告...")
        embassy_queries = [
            "site:za.china-embassy.gov.cn notice",             # 驻南非大使馆
            "site:johannesburg.china-consulate.gov.cn notice", # 约堡总领馆
            "site:durban.china-consulate.gov.cn notice",       # 德班总领馆
            "site:capetown.china-consulate.gov.cn notice"      # 开普敦总领馆
        ]
        for q in embassy_queries:
            try:
                # 搜索过去一个月(m)的文本，因为公告频率较低
                res_list = list(ddgs.text(keywords=q, region="za-en", timelimit="m", max_results=1))
                for res in res_list:
                    results.append({
                        "type": "EMBASSY",
                        "category": "领事提醒",
                        "title": res['title'],
                        "snippet": res['body'],
                        "source": "中国驻南非使领馆",
                        "url": res['href']
                    })
            except: pass
            
    status_text.empty()
    return results

def get_history_fun_fact():
    prompt = """
    Generate a concise, interesting "Fun Fact" or "On This Day" story about South African history.
    It could be about Gold Rush, Nelson Mandela, Zulu Kingdom, or Cape Town history.
    Max 80 words.
    """
    fact, _ = get_gemini_response(prompt)
    return fact if fact else "Did you know? South Africa has 3 capital cities!"

def generate_viral_article(news_data, history_fact):
    if not news_data: return None, "未找到任何数据，AI无法生成文章。请尝试放宽搜索条件或增加话题。"

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
    Task: Write a viral WeChat Official Account article for Chinese expats.
    
    Input Data:
    [EMBASSY NOTICES (TOP PRIORITY)]:
    {embassy_text}
    
    [NEWS]:
    {news_text}
    
    [HISTORY FACT]:
    {history_fact}
    
    Requirements:
    1. **Language**: Chinese (Simplified).
    2. **Headline**: Clickbait/Urgent (e.g., "紧急！" or "注意！").
    3. **Structure**:
       - **Part 1 🚨**: Embassy notices (Priority). If none, say "今日无重要领事提醒".
       - **Part 2 📰**: General News summary. Group by topic.
       - **Part 3 📜**: History story (Translate the fact).
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
    st.header("🛠️ 1. 流量选题 (Topics)")
    
    # 10个华人感兴趣的方面
    topic_options = [
        "Immigration/Visas",       # 内政部/签证
        "Crime/Safety Alerts",     # 治安/预警
        "Rand/RMB Exchange Rate",  # 汇率/金融
        "Eskom/Water Supply",      # 水电/限电
        "Logistics/Port Delays",   # 物流/港口
        "Traffic/Strikes",         # 交通/罢工
        "China-SA Relations",      # 中南关系
        "Real Estate/Property",    # 房产/租房
        "Education/Schools",       # 教育/留学
        "Lifestyle/Food"           # 吃喝玩乐
    ]
    
    topics = st.multiselect(
        "选择您想扫描的领域:",
        topic_options,
        # 默认勾选前三个最核心的
        default=["Immigration/Visas", "Crime/Safety Alerts", "Rand/RMB Exchange Rate"]
    )
    
    st.divider()
    
    st.header("🛠️ 2. 媒体源 (Sources)")
    st.caption("优先搜索以下媒体 (搜不到会自动转全网):")
    target_media = st.multiselect(
        "Select Media",
        ["Business Day", "Sunday Times", "Daily Sun", "The Star"],
        default=["Business Day", "The Star"]
    )
    
    check_embassy = st.checkbox("扫描中国驻南非使领馆公告", value=True)
    
    st.markdown("---")
    
    if st.button("🔄 开始全网扫描 (Scan)"):
        if not topics:
            st.warning("请至少选择一个话题！")
        else:
            with st.spinner("🕵️‍♂️ 正在执行三级智能搜索..."):
                # 1. 搜索
                results = search_news_smart(topics, target_media, check_embassy)
                st.session_state['scan_results'] = results
                
                # 2. 生成趣闻
                st.session_state['history_fact'] = get_history_fun_fact()
                
                if results:
                    st.success(f"扫描完成！获取 {len(results)} 条资讯。")
                else:
                    st.warning("全网搜索结果为 0，请稍后再试。")

# === 主界面 ===

if 'scan_results' in st.session_state:
    # 趣闻展示
    if 'history_fact' in st.session_state:
        with st.container(border=True):
            st.markdown(f"**📜 今日历史趣闻:** {st.session_state['history_fact']}")

    st.write("") 

    # 抓取结果列表
    news_count = len(st.session_state['scan_results'])
    if news_count > 0:
        with st.expander(f"📄 点击展开抓取详情 ({news_count}条)", expanded=True):
            for item in st.session_state['scan_results']:
                icon = "🚨" if item['type'] == 'EMBASSY' else "📰"
                st.markdown(f"{icon} **[{item['category']}]** {item['title']}")
                st.caption(f"Source: {item['source']} | [原文]({item['url']})")
                st.divider()

        st.write("")
        
        if st.button("🚀 生成公众号文章 (Generate Article)"):
            with st.spinner("✍️ AI 正在撰写爆款文章..."):
                article, err = generate_viral_article(
                    st.session_state['scan_results'], 
                    st.session_state.get('history_fact', '')
                )
                if article:
                    st.session_state['final_article_v4'] = article
                    st.balloons()
                else:
                    st.error(f"生成失败: {err}")
    else:
        st.info("⚠️ 扫描完成，但暂无相关新闻。")

# === 结果展示 ===
if 'final_article_v4' in st.session_state:
    st.markdown("### 📱 微信预览")
    with st.container(border=True):
        st.caption(f"OONCE南非资讯 • {datetime.date.today().strftime('%Y-%m-%d')}")
        st.markdown(st.session_state['final_article_v4'])
    
    st.success("✅ 文章已生成！请长按内容复制。")
