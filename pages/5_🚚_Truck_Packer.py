import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import plotly.graph_objects as go

st.set_page_config(page_title="Multi-Truck Packing System", layout="wide")
st.title("🚛 货物多车连续装载系统 (双层堆叠与混合排布版)")

# =========================================================
# ⚙️ 1. 车型规格与堆叠参数配置
# =========================================================
st.sidebar.header("⚙️ 1. 车队规格与装载限制")
primary_truck_type = st.sidebar.radio("默认首选车型", ["Superlink (双挂)", "Tri-axle (三轴单挂)"])
max_truck_count = st.sidebar.number_input("允许调配的最大总车辆数 (辆)", min_value=1, max_value=20, value=7, step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("🏗️ 堆叠规则控制")

# 核心开关：选择是否开启高度堆叠
enable_stacking = st.sidebar.checkbox("📦 允许货物双层堆叠 (Double Stacking, 最多2层)", value=False)

if enable_stacking:
    st.sidebar.info("💡 **堆叠规则已生效：**\n1. 最多2层，严禁3层\n2. 底层组合高度必须平整\n3. 上层底面不可悬空\n4. 上层允许长宽调换，高度固定\n5. 总高不超过车厢限制")

enable_triaxle_fallback = False
if primary_truck_type == "Superlink (双挂)":
    enable_triaxle_fallback = st.sidebar.checkbox("💡 开启 Tri-axle 补位与前车货物逆向重组", value=True)

st.sidebar.markdown("---")

# Superlink 参数配置
st.sidebar.subheader("🚛 Superlink (双挂) 参数")
f_l = st.sidebar.number_input("前板长 (m)", value=6.0, step=0.1, key="f_l")
f_w = st.sidebar.number_input("前板宽 (m)", value=2.7, step=0.05, key="f_w")
f_h = st.sidebar.number_input("前板高 (m)", value=2.8, step=0.1, key="f_h")
f_m = st.sidebar.number_input("前板载重 (kg)", value=6000, step=500, key="f_m")

r_l = st.sidebar.number_input("后板长 (m)", value=12.0, step=0.1, key="r_l")
r_w = st.sidebar.number_input("后板宽 (m)", value=2.7, step=0.05, key="r_w")
r_h = st.sidebar.number_input("后板高 (m)", value=2.8, step=0.1, key="r_h")
r_m = st.sidebar.number_input("后板载重 (kg)", value=22000, step=500, key="r_m")

superlink_decks = [
    {"name": "前面板", "en_name": "Front Deck", "L": f_l, "W": f_w, "H": f_h, "MaxW": f_m},
    {"name": "后面板", "en_name": "Rear Deck", "L": r_l, "W": r_w, "H": r_h, "MaxW": r_m}
]

# Tri-axle 参数配置
st.sidebar.subheader("🚚 Tri-axle (三轴单挂) 参数")
t_l = st.sidebar.number_input("单挂长 (m)", value=12.0, step=0.1, key="t_l")
t_w = st.sidebar.number_input("单挂宽 (m)", value=2.7, step=0.05, key="t_w")
t_h = st.sidebar.number_input("单挂高 (m)", value=2.8, step=0.1, key="t_h")
t_m = st.sidebar.number_input("单挂载重 (kg)", value=30000, step=500, key="t_m")

triaxle_decks = [
    {"name": "单挂板", "en_name": "Single Deck", "L": t_l, "W": t_w, "H": t_h, "MaxW": t_m}
]

# =========================================================
# 📥 2. 批量导入待装货物总清单
# =========================================================
st.header("📥 2. 全量待装货物清单")

default_data = pd.DataFrame([
    {"货物编码": "ST-A01", "长(m)": 2.5, "宽(m)": 0.8, "高(m)": 1.2, "重量(kg)": 1200, "数量": 8},
    {"货物编码": "ST-B02", "长(m)": 2.0, "宽(m)": 1.2, "高(m)": 1.1, "重量(kg)": 1500, "数量": 6},
    {"货物编码": "ST-C03", "长(m)": 1.2, "宽(m)": 1.0, "高(m)": 1.0, "重量(kg)": 800, "数量": 12},
    {"货物编码": "ST-ERR", "长(m)": 13.0, "宽(m)": 1.0, "高(m)": 3.0, "重量(kg)": 5000, "数量": 1},
])

uploaded_file = st.file_uploader("📂 批量上传 CSV 或 Excel 货物清单", type=["csv", "xlsx"], key="cargo_uploader")

if uploaded_file:
    df_input = pd.read_csv(uploaded_file) if uploaded_file.name.endswith(".csv") else pd.read_excel(uploaded_file)
else:
    df_input = default_data

cargo_df = st.data_editor(df_input, num_rows="dynamic", use_container_width=True, key="cargo_editor")

# =========================================================
# 🧮 3. 核心算法：自适应长宽旋转 + 双层物理堆叠检验
# =========================================================
items_pool = []
seq_counter = 1
for _, row in cargo_df.iterrows():
    l_val = float(row["长(m)"])
    w_val = float(row["宽(m)"])
    h_val = float(row["高(m)"])
    
    # 自动校验单位（如果是mm/cm则转m）
    if l_val > 50: l_val /= 1000.0
    if w_val > 50: w_val /= 1000.0
    if h_val > 50: h_val /= 1000.0
    
    for _ in range(int(row["数量"])):
        items_pool.append({
            "seq": f"#{seq_counter}",
            "code": str(row["货物编码"]),
            "l": l_val,
            "w": w_val,
            "h": h_val,
            "weight": float(row["重量(kg)"])
        })
        seq_counter += 1

global_max_h = max(f_h, r_h, t_h)
global_max_w = max(f_w, r_w, t_w)
global_max_l = max(f_l, r_l, t_l)
global_max_weight = max(f_m, r_m, t_m)

valid_items = []
final_failed_items = []

for item in items_pool:
    if item["h"] > global_max_h:
        final_failed_items.append({**item, "最终拒绝原因": f"高度 ({item['h']}m) 超过限制 ({global_max_h}m)"})
        continue
    fit_normal = (item["l"] <= global_max_l and item["w"] <= global_max_w)
    fit_swapped = (item["w"] <= global_max_l and item["l"] <= global_max_w)
    if not (fit_normal or fit_swapped):
        final_failed_items.append({**item, "最终拒绝原因": f"尺寸 ({item['l']}x{item['w']}m) 超出车厢限制"})
        continue
    if item["weight"] > global_max_weight:
        final_failed_items.append({**item, "最终拒绝原因": f"单重 ({item['weight']}kg) 超过限重"})
        continue

    valid_items.append(item)

valid_items.sort(key=lambda x: (x["l"] * x["w"], max(x["l"], x["w"])), reverse=True)

# 挂板装载核心函数（包含双层堆叠演算）
def pack_deck_with_stacking(deck_info, unpacked_list, truck_name, allow_stack):
    d_l, d_w, d_h, d_max_w = deck_info["L"], deck_info["W"], deck_info["H"], deck_info["MaxW"]
    deck_weight = 0.0
    curr_x = 0.0
    placed_items = []
    items_to_remove = []
    
    while curr_x < d_l and unpacked_list:
        row_items = []
        curr_y = 0.0
        row_max_len = 0.0
        row_removed = []
        
        # 1. 铺设底层（Layer 1）
        for item in unpacked_list:
            if item in items_to_remove or item in row_removed:
                continue
            if item["h"] > d_h or deck_weight + item["weight"] > d_max_w:
                continue
                
            rem_x = d_l - curr_x
            rem_y = d_w - curr_y
            
            candidates = []
            if item["l"] <= rem_x and item["w"] <= rem_y:
                candidates.append({"l": item["l"], "w": item["w"], "swapped": False})
            if item["w"] <= rem_x and item["l"] <= rem_y:
                candidates.append({"l": item["w"], "w": item["l"], "swapped": True})
                
            if candidates:
                best_cand = min(candidates, key=lambda c: (c["l"], abs(rem_y - c["w"])))
                row_items.append({
                    "item_ref": item,
                    "seq": item["seq"],
                    "code": item["code"],
                    "truck_name": truck_name,
                    "deck_name": deck_info["name"],
                    "deck_en_name": deck_info["en_name"],
                    "l": best_cand["l"],
                    "w": best_cand["w"],
                    "h": item["h"],
                    "weight": item["weight"],
                    "swapped": best_cand["swapped"],
                    "rel_y": curr_y,
                    "layer": 1,
                    "z": 0.0
                })
                curr_y += best_cand["w"]
                row_max_len = max(row_max_len, best_cand["l"])
                deck_weight += item["weight"]
                row_removed.append(item)
                
        if not row_items:
            break
            
        y_offset = (d_w - curr_y) / 2.0
        
        # 将底层加入最终列表
        layer1_entries = []
        for r_item in row_items:
            entry = {
                "item_raw": r_item["item_ref"],
                "序号": r_item["seq"],
                "货物编码": r_item["code"],
                "归属车辆": truck_name,
                "分配挂板": r_item["deck_name"],
                "分配挂板英文": r_item["deck_en_name"],
                "摆放长(m)": r_item["l"],
                "摆放宽(m)": r_item["w"],
                "高(m)": r_item["h"],
                "长宽调换": "已调换" if r_item["swapped"] else "正放",
                "swapped_bool": r_item["swapped"],
                "重量(kg)": r_item["weight"],
                "坐标X(m)": round(curr_x, 2),
                "坐标Y(m)": round(r_item["rel_y"] + y_offset, 2),
                "坐标Z(m)": 0.0,
                "层级": "底层 (L1)"
            }
            placed_items.append(entry)
            layer1_entries.append(entry)
            items_to_remove.append(r_item["item_ref"])

        # 2. 堆叠上层（Layer 2，只有在勾选 allow_stack 时执行）
        if allow_stack:
            # 在刚刚排好的底层（layer1_entries）上面尝试寻找符合条件的上层货物
            for base in layer1_entries:
                # 底座允许尺寸与基准高度
                base_x, base_y, base_z = base["坐标X(m)"], base["坐标Y(m)"], base["坐标Z(m)"]
                base_l, base_w, base_h = base["摆放长(m)"], base["摆放宽(m)"], base["高(m)"]
                
                # 寻找能叠在 base 上方的货物
                for top_item in unpacked_list:
                    if top_item in items_to_remove:
                        continue
                    # 规则 4: 总高度检验
                    if base_h + top_item["h"] > d_h or deck_weight + top_item["weight"] > d_max_w:
                        continue
                    
                    # 规则 3: 上层长宽自适应调换且不超过底座限制
                    top_cand = []
                    if top_item["l"] <= base_l and top_item["w"] <= base_w:
                        top_cand.append({"l": top_item["l"], "w": top_item["w"], "swapped": False})
                    if top_item["w"] <= base_l and top_item["l"] <= base_w:
                        top_cand.append({"l": top_item["w"], "w": top_item["l"], "swapped": True})
                        
                    if top_cand:
                        best_top = min(top_cand, key=lambda c: (c["l"] * c["w"]))
                        
                        top_entry = {
                            "item_raw": top_item,
                            "序号": top_item["seq"],
                            "货物编码": top_item["code"],
                            "归属车辆": truck_name,
                            "分配挂板": base["分配挂板"],
                            "分配挂板英文": base["分配挂板英文"],
                            "摆放长(m)": best_top["l"],
                            "摆放宽(m)": best_top["w"],
                            "高(m)": top_item["h"],
                            "长宽调换": "已调换" if best_top["swapped"] else "正放",
                            "swapped_bool": best_top["swapped"],
                            "重量(kg)": top_item["weight"],
                            "坐标X(m)": base_x,
                            "坐标Y(m)": base_y,
                            "坐标Z(m)": round(base_h, 2),
                            "层级": "上层 (L2 堆叠)"
                        }
                        placed_items.append(top_entry)
                        items_to_remove.append(top_item)
                        deck_weight += top_item["weight"]
                        break # 底座已使用，寻找下一个上层堆叠点
            
        curr_x += row_max_len
        
    return placed_items, items_to_remove

truck_results = []
unpacked_items = valid_items.copy()
current_type = primary_truck_type
reallocated_info = []

for truck_idx in range(1, max_truck_count + 1):
    if not unpacked_items:
        break

    if primary_truck_type == "Superlink (双挂)" and enable_triaxle_fallback and current_type == "Superlink (双挂)":
        can_fit_superlink = False
        for item in unpacked_items:
            for d in superlink_decks:
                if item["h"] <= d["H"] and item["weight"] <= d["MaxW"]:
                    if (item["l"] <= d["L"] and item["w"] <= d["W"]) or (item["w"] <= d["L"] and item["l"] <= d["W"]):
                        can_fit_superlink = True
                        break
            if can_fit_superlink:
                break
                
        if not can_fit_superlink:
            current_type = "Tri-axle (三轴单挂)"
            stolen_items = []
            for tr in reversed(truck_results):
                if "Superlink" in tr["truck_name"]:
                    candidate_stolen = [item_entry["item_raw"] for item_entry in tr["items"]]
                    test_combined = unpacked_items + candidate_stolen
                    test_combined.sort(key=lambda x: (x["l"] * x["w"], max(x["l"], x["w"])), reverse=True)
                    
                    test_placed, test_removed = pack_deck_with_stacking(triaxle_decks[0], test_combined, "TestTruck", enable_stacking)
                    
                    if len(test_removed) > len(unpacked_items):
                        stolen_items.extend(candidate_stolen)
                        truck_results.remove(tr)
                        reallocated_info.append(f"成功将前面【{tr['truck_name']}】的货物借调重组，消灭了该 Superlink 车辆！")
                        break

            unpacked_items.extend(stolen_items)
            unpacked_items.sort(key=lambda x: (x["l"] * x["w"], max(x["l"], x["w"])), reverse=True)

    if current_type == "Superlink (双挂)":
        truck_name = f"车辆 #{truck_idx} (Superlink)"
        truck_en_name = f"Truck #{truck_idx} (Superlink)"
        active_decks = superlink_decks
    else:
        truck_name = f"车辆 #{truck_idx} (Tri-axle - 重组优化版)"
        truck_en_name = f"Truck #{truck_idx} (Tri-axle)"
        active_decks = triaxle_decks

    current_truck_success = []
    for d_info in active_decks:
        placed, removed = pack_deck_with_stacking(d_info, unpacked_items, truck_name, enable_stacking)
        current_truck_success.extend(placed)
        for rm in removed:
            unpacked_items.remove(rm)

    if current_truck_success:
        truck_results.append({
            "truck_name": truck_name,
            "truck_en_name": truck_en_name,
            "truck_id": truck_idx,
            "items": current_truck_success,
            "deck_configs": active_decks
        })
    else:
        break

for item in unpacked_items:
    final_failed_items.append({**item, "最终拒绝原因": f"调配的 {max_truck_count} 辆车用尽，仍无法装入"})

# =========================================================
# 📊 4. 结果汇总表格展现
# =========================================================
st.header("📊 3. 多车配载结果汇总")

all_success_items = []
superlink_count = 0
triaxle_count = 0

for tr in truck_results:
    all_success_items.extend(tr["items"])
    if "Superlink" in tr["truck_name"]:
        superlink_count += 1
    else:
        triaxle_count += 1

df_all_success = pd.DataFrame(all_success_items)
df_final_failed = pd.DataFrame(final_failed_items)

col1, col2, col3, col4 = st.columns(4)
col1.metric("已成功调配车辆", f"{len(truck_results)} / {max_truck_count} 辆")
col2.metric("Superlink 数量", f"{superlink_count} 辆")
col3.metric("Tri-axle 数量", f"{triaxle_count} 辆" if triaxle_count == 0 else f"{triaxle_count} 辆 (重组)")
col4.metric("最终无法装载件数", f"{len(df_final_failed)} 件", delta_color="inverse")

if reallocated_info:
    for info in reallocated_info:
        st.success(f"🎯 **全局重组优化成功：** {info}")

st.subheader("🟢 多车成功配载清单 (含层级与堆叠坐标)")
if not df_all_success.empty:
    show_success = df_all_success[["序号", "货物编码", "归属车辆", "分配挂板", "层级", "摆放长(m)", "摆放宽(m)", "高(m)", "长宽调换", "重量(kg)", "坐标X(m)", "坐标Y(m)", "坐标Z(m)"]]
    st.dataframe(show_success.style.apply(lambda s: ['background-color: #d1fae5; color: #065f46; font-weight: bold;'] * len(s), axis=1), use_container_width=True)
else:
    st.warning("⚠️ 没有任何货物成功装载！")

st.subheader("🔴 最终无法装载拒绝清单")
if not df_final_failed.empty:
    show_failed = df_final_failed[["seq", "code", "l", "w", "h", "weight", "最终拒绝原因"]].rename(
        columns={"seq": "序号", "code": "货物编码", "l": "长(m)", "w": "宽(m)", "h": "高(m)", "weight": "重量(kg)"}
    )
    st.dataframe(show_failed.style.apply(lambda s: ['background-color: #fee2e2; color: #991b1b; font-weight: bold;'] * len(s), axis=1), use_container_width=True)
else:
    st.success("🎉 所有货物已全部通过车队分配装载完毕！")

# =========================================================
# 🖼️ 5. 分车辆 2D 与 3D 效果图绘制 (支持双层立体展示)
# =========================================================
st.header("🖼️ 4. 分车辆装载 2D / 3D 效果图")

if truck_results:
    truck_names = [tr["truck_name"] for tr in truck_results]
    selected_truck_name = st.selectbox("🚚 选择要查看的车辆方案：", truck_names)
    
    selected_truck_data = next(tr for tr in truck_results if tr["truck_name"] == selected_truck_name)
    selected_items_df = pd.DataFrame(selected_truck_data["items"])
    
    tab_3d, tab_2d = st.tabs(["🧊 3D 交互式立体视图", "📐 2D 平面俯视图"])

    def add_cube_3d_clean(fig, x, y, z, dx, dy, dz, color, label, opacity=0.85):
        x_pts = [x, x+dx, x+dx, x, x, x+dx, x+dx, x]
        y_pts = [y, y, y+dy, y+dy, y, y, y+dy, y+dy]
        z_pts = [z, z, z, z, z+dz, z+dz, z+dz, z+dz]
        i_pts = [7, 0, 0, 0, 4, 4, 2, 6, 4, 0, 3, 7]
        j_pts = [4, 5, 1, 2, 5, 6, 3, 7, 1, 1, 2, 6]
        k_pts = [0, 1, 2, 3, 6, 7, 6, 5, 5, 4, 7, 3]

        fig.add_trace(go.Mesh3d(
            x=x_pts, y=y_pts, z=z_pts, i=i_pts, j=j_pts, k=k_pts,
            color=color, opacity=opacity, name=label,
            hovertemplate=f"<b>{label}</b><br>尺寸: {dx:.2f} x {dy:.2f} x {dz:.2f}m<br>坐标: X={x:.2f}, Y={y:.2f}, Z={z:.2f}<extra></extra>"
        ))

    colors_palette = ['#2563eb', '#059669', '#d97706', '#7c3aed', '#db2777', '#0891b2']

    with tab_3d:
        for deck in selected_truck_data["deck_configs"]:
            d_name = deck["name"]
            d_l, d_w, d_h = deck["L"], deck["W"], deck["H"]
            
            fig3d = go.Figure()
            add_cube_3d_clean(fig3d, 0, 0, 0, d_l, d_w, d_h, color="#94a3b8", label=f"车厢 ({d_name})", opacity=0.05)

            deck_items = selected_items_df[selected_items_df["分配挂板"] == d_name] if not selected_items_df.empty else pd.DataFrame()
            
            for idx, item in deck_items.iterrows():
                c = colors_palette[int(idx) % len(colors_palette)]
                lbl = f"{item['序号']} ({item['货物编码']}) [{item['层级']}]"
                add_cube_3d_clean(fig3d, item["坐标X(m)"], item["坐标Y(m)"], item["坐标Z(m)"], 
                                  item["摆放长(m)"], item["摆放宽(m)"], item["高(m)"], color=c, label=lbl)

            fig3d.update_layout(
                title=f"{selected_truck_name} - 【{d_name}】 3D 优化装配图 (含双层堆叠高度 Z 轴)",
                scene=dict(
                    xaxis=dict(title='车长 X (m)', range=[-0.5, d_l + 0.5]),
                    yaxis=dict(title='车宽 Y (m)', range=[-0.5, d_w + 0.5]),
                    zaxis=dict(title='车高 Z (m)', range=[0, d_h + 0.5]),
                    aspectmode='data'
                ),
                margin=dict(l=0, r=0, b=0, t=40), height=520
            )
            st.plotly_chart(fig3d, use_container_width=True)

    with tab_2d:
        fig2d, axes = plt.subplots(len(selected_truck_data["deck_configs"]), 1, figsize=(10, 3.8 * len(selected_truck_data["deck_configs"])))
        if len(selected_truck_data["deck_configs"]) == 1:
            axes = [axes]

        for idx, deck in enumerate(selected_truck_data["deck_configs"]):
            ax = axes[idx]
            d_en_name = deck["en_name"]
            d_l, d_w = deck["L"], deck["W"]

            ax.add_patch(patches.Rectangle((0, 0), d_l, d_w, linewidth=2, edgecolor='#1e293b', facecolor='#f8fafc', zorder=1))
            ax.axhline(d_w / 2.0, color='#64748b', linestyle='--', linewidth=1.5, zorder=3, label="Center Line")

            deck_items = selected_items_df[selected_items_df["分配挂板英文"] == d_en_name] if not selected_items_df.empty else pd.DataFrame()

            for item_idx, item in deck_items.iterrows():
                c = colors_palette[int(item_idx) % len(colors_palette)]
                # 上层货物使用虚线边框标注
                line_style = '--' if "L2" in item["层级"] else '-'
                rect = patches.Rectangle((item["坐标X(m)"], item["坐标Y(m)"]), item["摆放长(m)"], item["摆放宽(m)"], 
                                         linewidth=1.5, linestyle=line_style, edgecolor='black', facecolor=c, alpha=0.8, zorder=2)
                ax.add_patch(rect)
                
                box_l, box_w = item["摆放长(m)"], item["摆放宽(m)"]
                calc_font_size = min(box_l * 2.5, box_w * 2.5, 7.0)
                
                if calc_font_size >= 3.5:
                    layer_tag = "L2" if "L2" in item["层级"] else "L1"
                    swap_mark = "R" if item['swapped_bool'] else "N"
                    txt_label = f"{item['序号']}({layer_tag})\n{item['货物编码']}\n({swap_mark})"
                    ax.text(item["坐标X(m)"] + box_l/2, item["坐标Y(m)"] + box_w/2, 
                            txt_label, color='white', weight='bold', fontsize=calc_font_size, ha='center', va='center', zorder=4)

            ax.set_xlim(-0.5, d_l + 0.5)
            ax.set_ylim(-0.5, d_w + 0.5)
            ax.set_aspect('equal')
            ax.set_title(f"Truck #{selected_truck_data['truck_id']} - [{d_en_name}] 2D Layout (W: {d_w}m, L: {d_l}m)")
            ax.legend(loc="upper right", fontsize=8)

        st.pyplot(fig2d)
