import streamlit as st

# ==========================================
# 1. 基础配置与资费常量定义 (ZAR)
# ==========================================
USD_TO_ZAR = 18.20  # 汇率基准

# TNPA 官方转关规费 (RIT Cargo Dues)
TNPA_TRANS_BREAKBULK_PER_RT = 4.82

# 码头及私营堆场操作费 (Terminal Handling Charges - THC)
MACHINERY_THC_PER_UNIT = 4000.00       # 工程机械/车辆 THC (R 4,000.00 / 台)
BREAKBULK_THC_PER_RT = 467.50          # 散货/零部件大件 THC (R 467.50 / RT，参考发票 THC-P004-IG 标准)

# 私营保税仓 (Private Bonded Warehouse, 如 KHOLD/Vukuzenzele) 其他规费
BONDED_VEHICLE_INOUT_FEE = 2500.00      # 车辆进出仓固定费/台
BONDED_STORAGE_PER_TON_PER_DAY = 30.00  # 堆存费: 吨/天

# 换单及清关固定第三方规费
DO_RELEASE_FEE = 1280.00                # 船代换单 DO + EDI 费 (含税为 R 1,472)
RIT_BOND_AGENCY_FEE = 6500.00           # 转关 Road Bond & 清关代理包干

# ==========================================
# 2. 页面布局与标题
# ==========================================
st.set_page_config(page_title="散货与工程机械转关核算", page_icon="🚜", layout="wide")

st.title("🚜 散货 & 工程机械转关（RIT）港口与私营保税仓核算系统")
st.caption("适用德班港 (Port of Durban) 转关过境赞比亚/津巴布韦等南部非洲国家成本精算")

# ==========================================
# 3. 侧边栏：提货状态与私营保税仓参数设置
# ==========================================
with st.sidebar:
    st.header("⏱️ 提货状态与保税仓设置")
    
    pickup_status = st.radio(
        "选择提货提取模式:",
        ["船边直取/码头免堆期内正常提走 (Normal Direct)", "延误未及时提取 (转入私营 Bonded Warehouse)"]
    )
    is_delayed = "私营 Bonded Warehouse" in pickup_status
    
    delay_days = 0
    if is_delayed:
        st.error("⚠️ 已触发私营堆场流程 (产生短驳、进出库及堆存费)")
        delay_days = st.number_input("私营堆场滞留天数 (Storage Days):", min_value=1, value=5, step=1)
        st.info("注：私营堆场通常扣除 24 小时免费期后按天计算堆存费。")

    st.markdown("---")
    st.subheader("💡 关键参数微调")
    
    # 允许在侧边栏微调 THC 费率
    custom_machinery_thc = st.number_input(
        "工程机械 THC 单价 (ZAR / 台):", 
        value=MACHINERY_THC_PER_UNIT, 
        step=500.0,
        help="工程机械码头/堆场操作包干费，默认为 R 4,000 / 台"
    )
    custom_breakbulk_thc = st.number_input(
        "散货/零部件 THC 单价 (ZAR / RT):", 
        value=BREAKBULK_THC_PER_RT, 
        step=10.0,
        help="散货装卸 Handling 费，参考发票标准 R 467.50 / RT"
    )
    custom_haulage_rate = st.number_input(
        "私营仓短驳单价 (ZAR / 趟):", 
        value=8000.0, 
        step=500.0,
        help="参考 50 吨重件短驳合理价格为 R 8,000 / 趟"
    )
    usd_rate = st.number_input("USD / ZAR 汇率:", value=USD_TO_ZAR, step=0.1)

# ==========================================
# 4. 主界面：货物类型与逐台维度输入
# ==========================================
st.subheader("📦 货物维度与参数输入")

cargo_type = st.selectbox(
    "选择货物类别:",
    ["工程机械 / 车辆设备 (Vehicles & Heavy Machinery)", "散杂货 / 零部件大件 (Breakbulk / Project Cargo)"]
)

total_rt = 0.0
total_weight_tons = 0.0
total_length_meters = 0.0
unit_count = 1
machines_detail = []

if "工程机械" in cargo_type:
    unit_count = st.number_input("工程机械总台数 (Total Units):", min_value=1, value=1, step=1)
    
    st.markdown(f"#### 📝 请分别填写这 {unit_count} 台机械的规格参数：")
    
    for i in range(int(unit_count)):
        with st.expander(f"🔹 第 {i+1} 台机械规格设置", expanded=True):
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                m_name = st.text_input(f"设备名称/型号 #{i+1}:", value=f"机械设备 #{i+1}", key=f"m_name_{i}")
            with col2:
                m_weight = st.number_input(f"重量 (吨/Ton) #{i+1}:", min_value=0.1, value=38.5 if i==0 else 20.0, step=0.5, key=f"m_weight_{i}")
            with col3:
                m_length = st.number_input(f"长度 (米/m) #{i+1}:", min_value=0.1, value=11.4 if i==0 else 7.0, step=0.1, key=f"m_length_{i}")
            with col4:
                m_height = st.number_input(f"高度 (米/m) #{i+1}:", min_value=0.1, value=3.7, step=0.1, key=f"m_height_{i}")
                
            machines_detail.append({
                "name": m_name,
                "weight": m_weight,
                "length": m_length,
                "height": m_height
            })
            
    total_weight_tons = sum(m["weight"] for m in machines_detail)
    total_length_meters = sum(m["length"] for m in machines_detail)
    
    st.success(f"📊 **全部 {unit_count} 台设备汇总：** 总重量 = **{total_weight_tons:.2f} 吨** | 总车长 = **{total_length_meters:.2f} 米**")

else:
    input_mode = st.radio("散货维度输入模式:", ["按单件长宽高输入", "直接输入总重量和总体积"], horizontal=True)
    if input_mode == "按单件长宽高输入":
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            l_mm = st.number_input("单件长 (mm):", value=6000, step=100)
        with c2:
            w_mm = st.number_input("单件宽 (mm):", value=2500, step=100)
        with c3:
            h_mm = st.number_input("单件高 (mm):", value=2800, step=100)
        with c4:
            w_kg = st.number_input("单件重 (kg):", value=15000, step=500)
        with c5:
            unit_count = st.number_input("件数 (Qty):", min_value=1, value=1, step=1)
            
        vol_m3 = (l_mm * w_mm * h_mm) / 1e9 * unit_count
        total_weight_tons = (w_kg / 1000.0) * unit_count
        total_rt = max(vol_m3, total_weight_tons)
        st.info(f"📊 自动计算: 总体积 = {vol_m3:.2f} m³ | 总重量 = {total_weight_tons:.2f} 吨 | **计费吨 (RT) = {total_rt:.2f} RT**")
    else:
        c1, c2 = st.columns(2)
        with c1:
            vol_m3 = st.number_input("总体积 (m³):", value=100.0, step=5.0)
        with c2:
            total_weight_tons = st.number_input("总重量 (Tons):", value=50.0, step=5.0)
        total_rt = max(vol_m3, total_weight_tons)
        st.info(f"📊 **计费吨 (RT) = {total_rt:.2f} RT** (W/M 择大原则)")

# ==========================================
# 5. 核心算账逻辑引擎
# ==========================================
st.markdown("---")
st.subheader("💰 转关费用拆解与核算结果")

tnpa_cargo_dues = 0.0
handling_fee = 0.0
haulage_fee = 0.0
bonded_inout_fee = 0.0
storage_fee = 0.0

# 5.1 TNPA 官方过境规费
if "工程机械" in cargo_type:
    tnpa_cargo_dues = total_weight_tons * TNPA_TRANS_BREAKBULK_PER_RT
else:
    tnpa_cargo_dues = total_rt * TNPA_TRANS_BREAKBULK_PER_RT

# 5.2 码头/私营仓 Handling (THC) 费算账逻辑
if "工程机械" in cargo_type:
    handling_fee = unit_count * custom_machinery_thc
else:
    handling_fee = total_rt * custom_breakbulk_thc

# 5.3 若落私营保税仓，计算额外短驳、进出库费及堆存费
if is_delayed:
    loads_needed = int(unit_count) if "工程机械" in cargo_type else max(1, int(total_weight_tons / 25) + 1)
    haulage_fee = loads_needed * custom_haulage_rate
    
    if "工程机械" in cargo_type:
        bonded_inout_fee = unit_count * BONDED_VEHICLE_INOUT_FEE
        
    storage_fee = total_weight_tons * BONDED_STORAGE_PER_TON_PER_DAY * delay_days

# 汇总费用
total_port_zar = tnpa_cargo_dues + handling_fee + haulage_fee + bonded_inout_fee + storage_fee
total_all_zar = total_port_zar + DO_RELEASE_FEE + RIT_BOND_AGENCY_FEE
total_all_usd = total_all_zar / usd_rate

# ==========================================
# 6. 数据展示看板
# ==========================================
kpi1, kpi2, kpi3 = st.columns(3)
kpi1.metric("TNPA 官方过境规费", f"ZAR {tnpa_cargo_dues:,.2f}", f"${tnpa_cargo_dues/usd_rate:,.2f} USD")
kpi2.metric("THC / 堆场装卸及短驳", f"ZAR {(handling_fee + haulage_fee + bonded_inout_fee):,.2f}", f"${(handling_fee + haulage_fee + bonded_inout_fee)/usd_rate:,.2f} USD")
kpi3.metric("转关全包硬成本总额 (Total)", f"ZAR {total_all_zar:,.2f}", f"${total_all_usd:,.2f} USD")

# 详细清单表格
st.markdown("### 📋 明细对账表 (Breakdown)")

breakdown_data = {
    "费用名目 (Item Description)": [
        "TNPA Cargo Dues (港务局过境规费)",
        "Terminal Handling Charges - THC (码头/堆场操作费)",
        "Internal Haulage (港区至私营堆场短驳费)",
        "Warehouse In/Out Fee (私营仓进出库费)",
        "Bonded Storage Fee (私营堆场超期堆存费)",
        "Shipping Line DO & EDI Fee (船代换单费)",
        "Customs Road Bond & Agency (清关保税与代理包干)"
    ],
    "金额 (ZAR)": [
        f"R {tnpa_cargo_dues:,.2f}",
        f"R {handling_fee:,.2f}",
        f"R {haulage_fee:,.2f}",
        f"R {bonded_inout_fee:,.2f}",
        f"R {storage_fee:,.2f}",
        f"R {DO_RELEASE_FEE:,.2f}",
        f"R {RIT_BOND_AGENCY_FEE:,.2f}"
    ],
    "折合美金 (USD)": [
        f"${tnpa_cargo_dues/usd_rate:,.2f}",
        f"${handling_fee/usd_rate:,.2f}",
        f"${haulage_fee/usd_rate:,.2f}",
        f"${bonded_inout_fee/usd_rate:,.2f}",
        f"${storage_fee/usd_rate:,.2f}",
        f"${DO_RELEASE_FEE/usd_rate:,.2f}",
        f"${RIT_BOND_AGENCY_FEE/usd_rate:,.2f}"
    ],
    "收费属性说明": [
        "TNPA 官方法定硬规费 (过境打折价 R 4.82/t)",
        f"THC 操作费 ({'按台数 R 4,000/台' if '工程机械' in cargo_type else '按计费吨 R 467.50/RT'})",
        f"短驳费用 ({'正常直取为 R0' if not is_delayed else f'按每台 R {custom_haulage_rate:,.0f} 算'})",
        f"私营仓进出库引导 ({'正常直取为 R0' if not is_delayed else 'R 2,500/台'})",
        f"私营仓堆存 ({'正常直取为 R0' if not is_delayed else f'R30/吨/天 x {delay_days} 天'})",
        "船代固定换单费 (未含税面额 R 1,280)",
        "海关 RIT 申报、保税额度担保及销卷服务"
    ]
}

st.table(breakdown_data)
