import streamlit as st
import pandas as pd
import sqlite3
import datetime
import numpy as np

# --- 1. 数据库配置与初始化 ---
DB_FILE = 'warehouse.db'


def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS inventory
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  name TEXT NOT NULL,
                  model TEXT,
                  spec TEXT,
                  color TEXT,
                  unit TEXT,
                  quantity INTEGER,
                  location TEXT,
                  remark TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS logs
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  applicant TEXT,
                  action_type TEXT,
                  name TEXT,
                  model TEXT,
                  spec TEXT,
                  color TEXT,
                  unit TEXT,
                  quantity INTEGER,
                  location TEXT,
                  remark TEXT,
                  status TEXT,
                  timestamp DATETIME)''')
    conn.commit()
    conn.close()


# --- 2. 核心功能函数 ---
def run_query(query, params=()):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute(query, params)
    if query.strip().upper().startswith("SELECT"):
        data = c.fetchall()
        cols = [description[0] for description in c.description]
        conn.close()
        return pd.DataFrame(data, columns=cols)
    else:
        conn.commit()
        conn.close()


# 用于显示日志的中文映射
def format_df_for_display(df):
    if df.empty: return df
    column_mapping = {
        'id': '序号', 'applicant': '申请人', 'action_type': '操作类型',
        'name': '物品名称', 'model': '型号', 'spec': '规格',
        'color': '颜色', 'unit': '单位', 'quantity': '数量',
        'location': '位置', 'remark': '备注', 'status': '当前状态',
        'timestamp': '提交时间'
    }
    df_display = df.rename(columns=column_mapping)
    if '操作类型' in df_display.columns:
        type_map = {
            'IN': '入库/更新',
            'OUT': '领用',
            'ADMIN_EDIT': '管理员修改',
            'ADMIN_ADD': '管理员新增',
            'ADMIN_DEL': '管理员删除'
        }
        df_display['操作类型'] = df_display['操作类型'].map(type_map).fillna(df_display['操作类型'])
    if '当前状态' in df_display.columns:
        status_map = {'PENDING': '⏳ 待审核', 'APPROVED': '✅ 已通过', 'REJECTED': '❌ 已拒绝', 'DONE': '🆗 完成'}
        df_display['当前状态'] = df_display['当前状态'].map(status_map).fillna(df_display['当前状态'])
    return df_display


# 用于显示库存的中文映射字典 (只读模式用)
INVENTORY_COL_MAP = {
    'id': '序号', 'name': '名称', 'model': '型号', 'spec': '规格',
    'color': '颜色', 'unit': '单位', 'quantity': '数量',
    'location': '位置', 'remark': '备注'
}


def login_system():
    st.sidebar.title("🔐 仓管系统登录")
    # 从保险箱读取密码，如果没有配置则使用空字典防止报错
    if "passwords" in st.secrets:
        users = st.secrets["passwords"]
    else:
        st.error("未配置密码！请检查 .streamlit/secrets.toml")
        users = {}

    if 'logged_in' not in st.session_state:
        st.session_state.logged_in = False
        st.session_state.user_role = None
        st.session_state.username = None

    if not st.session_state.logged_in:
        username = st.sidebar.text_input("账号")
        password = st.sidebar.text_input("密码", type="password")
        if st.sidebar.button("登录"):
            if username in users and users[username] == password:
                st.session_state.logged_in = True
                st.session_state.username = username
                st.session_state.user_role = "admin" if username == "admin" else "user"
                st.rerun()
            else:
                st.sidebar.error("账号或密码错误")
    else:
        st.sidebar.success(f"用户: {st.session_state.username}")
        if st.sidebar.button("退出登录"):
            st.session_state.logged_in = False
            st.rerun()


# --- 3. 界面主逻辑 ---
def main():
    st.set_page_config(page_title="仓管系统", layout="wide")
    init_db()
    login_system()

    if not st.session_state.logged_in: return

    # 提醒逻辑
    pending_count = 0
    approval_menu_name = "✅ 审批中心"
    if st.session_state.user_role == 'admin':
        res = run_query("SELECT COUNT(*) as cnt FROM logs WHERE status='PENDING'")
        if not res.empty: pending_count = res.iloc[0]['cnt']
        if pending_count > 0:
            approval_menu_name = f"✅ 审批中心 (🔴 {pending_count} 待办)"
            st.sidebar.error(f"🔔 提示：有 {pending_count} 条申请待审批！")

    menu = ["🏭 仓库作业中心", approval_menu_name]
    if st.session_state.user_role != 'admin': menu = ["🏭 仓库作业中心"]
    choice = st.sidebar.radio("导航", menu)

    # ================= 核心功能区 =================
    if choice == "🏭 仓库作业中心":
        if st.session_state.user_role == 'admin' and pending_count > 0:
            st.warning(f"⚠️ 注意：有 {pending_count} 条申请需要审批！")

        st.markdown("### 🛠️ 物品操作区")

        df_inventory = run_query("SELECT * FROM inventory")
        options = ["(新商品 / 手动输入)"]
        if not df_inventory.empty:
            df_inventory['label'] = df_inventory['name'] + " | " + df_inventory['model'] + " | " + df_inventory[
                'location']
            options += df_inventory['label'].tolist()

        col_type, col_select = st.columns([1, 3])
        with col_type:
            action_type = st.radio("操作类型", ["入库/更新 (IN)", "领用 (OUT)"], horizontal=True)
        with col_select:
            selected_item = st.selectbox("📦 快速选择库存", options)

        default_val = {k: "" for k in ['name', 'model', 'spec', 'color', 'unit', 'location', 'remark']}
        if selected_item != "(新商品 / 手动输入)":
            row = df_inventory[df_inventory['label'] == selected_item].iloc[0]
            for k in default_val.keys(): default_val[k] = row[k]

        with st.form("op_form"):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                name = st.text_input("名称", value=default_val['name'])
                color = st.text_input("颜色", value=default_val['color'])
            with c2:
                model = st.text_input("型号", value=default_val['model'])
                unit = st.text_input("单位", value=default_val['unit'])
            with c3:
                spec = st.text_input("规格", value=default_val['spec'])
                is_user_in = (st.session_state.user_role == 'user' and "入库" in action_type)
                if is_user_in:
                    st.info("📍 位置将由管理员分配")
                    location = ""
                else:
                    location = st.text_input("位置", value=default_val['location'])
            with c4:
                quantity = st.number_input("数量", min_value=1, step=1, value=1)
                remark = st.text_input("备注", value=default_val['remark'])

            submit_btn = st.form_submit_button("提交执行")

            if submit_btn:
                name = name.strip().lower()
                model = model.strip().lower()
                spec = spec.strip().lower()
                color = color.strip().lower()
                unit = unit.strip().lower()
                if not is_user_in: location = location.strip().lower()

                valid = True
                if not (name and model and spec and color and unit): valid = False
                if not is_user_in and not location: valid = False

                if not valid:
                    st.error("❌ 必填项不完整！")
                else:
                    act_code = 'IN' if "入库" in action_type else 'OUT'
                    if st.session_state.user_role == 'admin':
                        check_sql = "SELECT id, quantity FROM inventory WHERE name=? AND model=? AND spec=? AND location=? AND color=?"
                        existing = run_query(check_sql, (name, model, spec, location, color))
                        if act_code == 'IN':
                            if not existing.empty:
                                new_qty = existing.iloc[0]['quantity'] + quantity
                                run_query("UPDATE inventory SET quantity=?, remark=? WHERE id=?",
                                          (int(new_qty), remark, int(existing.iloc[0]['id'])))
                                st.success(f"✅ 库存更新成功，现数量: {new_qty}")
                            else:
                                run_query(
                                    "INSERT INTO inventory (name, model, spec, color, unit, quantity, location, remark) VALUES (?,?,?,?,?,?,?,?)",
                                    (name, model, spec, color, unit, quantity, location, remark))
                                st.success(f"✅ 新物品入库成功")
                            run_query(
                                "INSERT INTO logs (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                ('admin', 'IN', name, model, spec, color, unit, quantity, location, remark, 'APPROVED',
                                 datetime.datetime.now()))
                        else:  # OUT
                            if existing.empty or existing.iloc[0]['quantity'] < quantity:
                                st.error("❌ 库存不足")
                            else:
                                new_qty = existing.iloc[0]['quantity'] - quantity
                                if new_qty == 0:
                                    run_query("DELETE FROM inventory WHERE id=?", (int(existing.iloc[0]['id']),))
                                else:
                                    run_query("UPDATE inventory SET quantity=? WHERE id=?",
                                              (int(new_qty), int(existing.iloc[0]['id'])))
                                st.success(f"✅ 领用成功")
                                run_query(
                                    "INSERT INTO logs (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                                    ('admin', 'OUT', name, model, spec, color, unit, quantity, location, remark,
                                     'APPROVED', datetime.datetime.now()))
                        st.rerun()
                    else:
                        run_query("""INSERT INTO logs 
                                  (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) 
                                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                  (st.session_state.username, act_code, name, model, spec, color, unit, quantity,
                                   location, remark, 'PENDING', datetime.datetime.now()))
                        st.success("✅ 申请提交成功！")
                        st.rerun()

        if st.session_state.user_role == 'user':
            st.markdown("---")
            st.subheader("📋 我的提交记录")
            my_logs = run_query(
                "SELECT id, action_type, name, spec, quantity, location, status, timestamp, remark FROM logs WHERE applicant=? ORDER BY id DESC",
                (st.session_state.username,))
            if not my_logs.empty:
                st.dataframe(format_df_for_display(my_logs), use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- B. 库存明细 (汉化版) ---
        st.subheader("📊 库存明细表")

        # 获取原始数据
        original_df = run_query("SELECT * FROM inventory ORDER BY location")

        if st.session_state.user_role == 'admin':
            st.info("💡 管理员提示：双击单元格修改，+号新增，选中行删除。操作后请点击【保存表格修改】。")

            # 🟢 汉化关键点：使用 column_config 将英文字段映射为中文显示
            edited_df = st.data_editor(
                original_df,
                key="inventory_editor",
                column_config={
                    "id": st.column_config.NumberColumn("序号", disabled=True),
                    "name": st.column_config.TextColumn("名称"),
                    "model": st.column_config.TextColumn("型号"),
                    "spec": st.column_config.TextColumn("规格"),
                    "color": st.column_config.TextColumn("颜色"),
                    "unit": st.column_config.TextColumn("单位"),
                    "quantity": st.column_config.NumberColumn("数量"),
                    "location": st.column_config.TextColumn("位置"),
                    "remark": st.column_config.TextColumn("备注")
                },
                use_container_width=True,
                num_rows="dynamic"
            )

            col_save, col_del = st.columns([1, 6])
            with col_save:
                if st.button("💾 保存表格修改"):
                    try:
                        # 日志与保存逻辑 (保持英文列名进行处理，因为edited_df的数据结构未变)
                        old_dict = original_df.set_index('id').to_dict('index') if not original_df.empty else {}
                        old_ids = set(old_dict.keys())
                        current_ids = set(edited_df['id'].dropna().astype(int))

                        # 删除检测
                        deleted_ids = old_ids - current_ids
                        for did in deleted_ids:
                            row = old_dict[did]
                            msg = f"删除了物品: {row['name']} (位置: {row['location']}, 数量: {row['quantity']})"
                            run_query("""INSERT INTO logs 
                                      (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) 
                                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                      ('admin', 'ADMIN_DEL', row['name'], row['model'], row['spec'], row['color'],
                                       row['unit'], row['quantity'], row['location'], msg, 'DONE',
                                       datetime.datetime.now()))

                        # 新增与修改检测
                        for index, new_row in edited_df.iterrows():
                            if pd.isna(new_row['id']):
                                msg = f"新增了物品: {new_row['name']} (位置: {new_row['location']})"
                                n_name = new_row['name'] if new_row['name'] else "未知"
                                run_query("""INSERT INTO logs 
                                          (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) 
                                          VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                          ('admin', 'ADMIN_ADD', n_name, new_row['model'], new_row['spec'],
                                           new_row['color'], new_row['unit'], new_row['quantity'], new_row['location'],
                                           msg, 'DONE', datetime.datetime.now()))
                            else:
                                rid = int(new_row['id'])
                                if rid in old_dict:
                                    old_row = old_dict[rid]
                                    changes = []
                                    if old_row['quantity'] != new_row['quantity']: changes.append(
                                        f"数量 {old_row['quantity']}->{new_row['quantity']}")
                                    if old_row['location'] != new_row['location']: changes.append(
                                        f"位置 {old_row['location']}->{new_row['location']}")
                                    if old_row['name'] != new_row['name']: changes.append(f"名称变动")
                                    if old_row['remark'] != new_row['remark']: changes.append(f"备注变动")

                                    if changes:
                                        change_msg = "管理员修改: " + ", ".join(changes)
                                        run_query("""INSERT INTO logs 
                                                  (applicant, action_type, name, model, spec, color, unit, quantity, location, remark, status, timestamp) 
                                                  VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                                                  ('admin', 'ADMIN_EDIT', new_row['name'], new_row['model'],
                                                   new_row['spec'], new_row['color'], new_row['unit'],
                                                   new_row['quantity'], new_row['location'], change_msg, 'DONE',
                                                   datetime.datetime.now()))

                        # 保存
                        df_existing = edited_df.dropna(subset=['id'])
                        df_new = edited_df[edited_df['id'].isna()].drop(columns=['id'])
                        conn = sqlite3.connect(DB_FILE)
                        c = conn.cursor()
                        c.execute("DELETE FROM inventory")
                        df_existing.to_sql('inventory', conn, if_exists='append', index=False)
                        df_new.to_sql('inventory', conn, if_exists='append', index=False)
                        conn.commit()
                        conn.close()
                        st.success("✅ 保存成功！")
                        st.rerun()
                    except Exception as e:
                        st.error(f"保存失败: {e}")

        else:
            # 普通用户：直接翻译表头
            df_display = original_df.rename(columns=INVENTORY_COL_MAP)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

        st.markdown("---")

        # --- C. 全局日志管理 ---
        st.subheader("📝 全局操作日志")
        all_logs = run_query("SELECT * FROM logs ORDER BY id DESC")

        if not all_logs.empty:
            display_logs = format_df_for_display(all_logs)
            st.dataframe(display_logs, use_container_width=True, hide_index=True)

            col1, col2 = st.columns([1, 4])
            with col1:
                st.download_button(
                    label="📥 导出日志",
                    data=display_logs.to_csv(index=False).encode('utf-8_sig'),
                    file_name=f'logs_{datetime.datetime.now().strftime("%Y%m%d")}.csv',
                    mime='text/csv'
                )
            with col2:
                if st.session_state.user_role == 'admin':
                    with st.expander("⚠️ 清理日志"):
                        if st.button("🔴 确认清空"):
                            run_query("DELETE FROM logs")
                            st.success("日志已清空")
                            st.rerun()

    # ================= 审批中心 =================
    elif choice == approval_menu_name:
        st.title("审批中心")
        if pending_count > 0:
            st.warning(f"🔔 待处理: {pending_count} 条")
        else:
            st.success("✨ 无待办任务")

        pending = run_query("SELECT * FROM logs WHERE status='PENDING' ORDER BY id DESC")

        if not pending.empty:
            for i, row in pending.iterrows():
                with st.container(border=True):
                    cols = st.columns([4, 2, 1])
                    with cols[0]:
                        type_str = "🟢 申请入库" if row['action_type'] == 'IN' else "🔴 申请领用"
                        st.markdown(f"**{type_str}** | 申请人: {row['applicant']}")
                        st.write(f"物品: **{row['name']}** | 数量: **{row['quantity']} {row['unit']}**")
                        st.text(f"详情: {row['model']} | {row['spec']} | {row['color']}")
                        if row['action_type'] == 'OUT': st.text(f"领用位置: {row['location']}")
                        st.text(f"备注: {row['remark']}")

                    with cols[1]:
                        final_location = row['location']
                        if row['action_type'] == 'IN':
                            final_location = st.text_input(f"📍 分配入库位置 (必填)", key=f"loc_{row['id']}")

                        if st.button("批准", key=f"ok_{row['id']}"):
                            if final_location: final_location = final_location.strip().lower()
                            if not final_location:
                                st.error("❌ 必须分配一个位置")
                            else:
                                if row['action_type'] == 'IN':
                                    check_sql = "SELECT id, quantity FROM inventory WHERE name=? AND model=? AND spec=? AND location=? AND color=?"
                                    existing = run_query(check_sql,
                                                         (row['name'], row['model'], row['spec'], final_location,
                                                          row['color']))
                                    if not existing.empty:
                                        new_qty = existing.iloc[0]['quantity'] + row['quantity']
                                        run_query("UPDATE inventory SET quantity=?, remark=? WHERE id=?",
                                                  (int(new_qty), row['remark'], int(existing.iloc[0]['id'])))
                                    else:
                                        run_query(
                                            "INSERT INTO inventory (name, model, spec, color, unit, quantity, location, remark) VALUES (?,?,?,?,?,?,?,?)",
                                            (row['name'], row['model'], row['spec'], row['color'], row['unit'],
                                             row['quantity'], final_location, row['remark']))
                                else:
                                    check_sql = "SELECT id, quantity FROM inventory WHERE name=? AND model=? AND spec=? AND location=? AND color=?"
                                    existing = run_query(check_sql,
                                                         (row['name'], row['model'], row['spec'], final_location,
                                                          row['color']))
                                    if existing.empty or existing.iloc[0]['quantity'] < row['quantity']:
                                        st.error(f"库存不足！")
                                        continue
                                    else:
                                        new_qty = existing.iloc[0]['quantity'] - row['quantity']
                                        if new_qty == 0:
                                            run_query("DELETE FROM inventory WHERE id=?",
                                                      (int(existing.iloc[0]['id']),))
                                        else:
                                            run_query("UPDATE inventory SET quantity=? WHERE id=?",
                                                      (int(new_qty), int(existing.iloc[0]['id'])))
                                run_query("UPDATE logs SET status='APPROVED', location=? WHERE id=?",
                                          (final_location, row['id']))
                                st.success("已批准")
                                st.rerun()

                    with cols[2]:
                        st.write("")
                        if st.button("拒绝", key=f"no_{row['id']}"):
                            run_query("UPDATE logs SET status='REJECTED' WHERE id=?", (row['id'],))
                            st.error("已拒绝")
                            st.rerun()


if __name__ == '__main__':
    main()