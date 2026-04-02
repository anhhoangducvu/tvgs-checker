"""
TVGS Report Checker — Streamlit App
Kiểm tra nhanh báo cáo hoàn thành TVGS thi công xây dựng.

Chạy local:  streamlit run app.py
Deploy:      Streamlit Cloud / streamlit run app.py --server.port 8501
"""

import streamlit as st
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime

from extractor import extract_sections
from rule_checker import (
    load_criteria, run_check, get_summary,
    list_available_projects, SectionResult
)

# === Config ===
CRITERIA_DIR = Path(__file__).parent.parent / "criteria"

SECTION_NAMES = {
    "mo_dau": "Mở đầu",
    "muc_1": "1. Quy mô và thông tin chung",
    "muc_2": "2. Đánh giá năng lực nhà thầu",
    "muc_3": "3. Khối lượng, tiến độ, ATLĐ",
    "muc_4": "4. Thí nghiệm, kiểm tra vật liệu",
    "muc_5": "5. Kiểm định, quan trắc, TN đối chứng",
    "muc_6": "6. Nghiệm thu công việc XD",
    "muc_7": "7. Thay đổi thiết kế",
    "muc_8": "8. Tồn tại, khiếm khuyết, sự cố",
    "muc_9": "9. Hồ sơ quản lý chất lượng",
    "muc_10": "10. Tuân thủ pháp luật (MT, PCCC, XD)",
    "muc_11": "11. Quy trình vận hành, bảo trì",
    "muc_12": "12. Kết luận nghiệm thu",
}

VERDICT_MAP = {
    "DAT": {"label": "ĐẠT yêu cầu", "color": "#28a745", "icon": "✅"},
    "CAN_SUA_NHE": {"label": "Cần sửa nhẹ", "color": "#ffc107", "icon": "🟡"},
    "CAN_SUA_NHIEU": {"label": "Cần sửa nhiều", "color": "#dc3545", "icon": "🔴"},
    "KHONG_CO_DU_LIEU": {"label": "Không có dữ liệu", "color": "#6c757d", "icon": "⚪"},
}


# ──────────────────────────────────────────────
# Session state helpers
# ──────────────────────────────────────────────
def init_state():
    """Khởi tạo session state."""
    defaults = {
        "files": {},          # {filename: {"sections": ..., "results": ..., "summary": ...}}
        "project_name": None,
        "active_file": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def clear_all():
    """Xóa toàn bộ file đã upload."""
    st.session_state.files = {}
    st.session_state.active_file = None


def remove_file(filename):
    """Xóa 1 file."""
    if filename in st.session_state.files:
        del st.session_state.files[filename]
    if st.session_state.active_file == filename:
        remaining = list(st.session_state.files.keys())
        st.session_state.active_file = remaining[0] if remaining else None


# ──────────────────────────────────────────────
# Processing
# ──────────────────────────────────────────────
def process_file(uploaded_file, criteria_path, project_name):
    """Trích xuất + kiểm tra 1 file."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name

    try:
        sections = extract_sections(tmp_path)
        criteria = load_criteria(criteria_path, project_name)
        results = run_check(sections, criteria)
        summary = get_summary(results)
        return {
            "sections": sections,
            "results": results,
            "summary": summary,
            "criteria": criteria,
            "timestamp": datetime.now().strftime("%H:%M:%S %d/%m/%Y"),
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def build_export_text(filename, data):
    """Tạo báo cáo đánh giá dạng text."""
    summary = data["summary"]
    results = data["results"]
    sections = data["sections"]
    v = VERDICT_MAP.get(summary["verdict"], {})

    lines = []
    lines.append("=" * 60)
    lines.append("BÁO CÁO ĐÁNH GIÁ NHANH - TẦNG 1 (RULE-BASED)")
    lines.append("=" * 60)
    lines.append(f"File:       {filename}")
    lines.append(f"Thời gian:  {data.get('timestamp', '')}")
    lines.append(f"Kết quả:    {v.get('label', '?')}")
    lines.append(f"Điểm:       {summary['total_pass']}/{summary['total_checks']} PASS")
    lines.append(f"Cảnh báo:   {summary['total_warnings']}")
    lines.append("")

    for sr in results:
        if sr.total_checks == 0 and not sr.warnings:
            continue
        sec_name = SECTION_NAMES.get(sr.section_key, sr.section_name)
        status = "PASS" if sr.pass_count == sr.total_checks and not sr.warnings else "CẦN XEM"
        lines.append(f"--- {sec_name} [{sr.score_text}] {status} ---")

        if sr.canh_bao:
            lines.append(f"  !! CẢNH BÁO: {sr.canh_bao}")

        for c in sr.checks:
            icon = "[V]" if c.status == "PASS" else "[X]"
            lines.append(f"  {icon} {c.description}")

        for w in sr.warnings:
            lines.append(f"  [!] Ghi chú chưa xóa, dòng {w.line_number}: \"{w.line_text}\"")

        lines.append("")

    lines.append("=" * 60)
    lines.append("Lưu ý: Đây là kiểm tra tự động Tầng 1 (regex/keyword).")
    lines.append("Cần kiểm tra thêm nội dung chi tiết (Tầng 2) để đánh giá đầy đủ.")
    lines.append("=" * 60)

    return "\n".join(lines)


def build_export_json(filename, data):
    """Tạo JSON export."""
    summary = data["summary"]
    results = data["results"]
    export = {
        "file": filename,
        "timestamp": data.get("timestamp", ""),
        "summary": summary,
        "sections": [
            {
                "key": sr.section_key,
                "name": SECTION_NAMES.get(sr.section_key, sr.section_name),
                "pass": sr.pass_count,
                "total": sr.total_checks,
                "warnings": len(sr.warnings),
                "checks": [{"desc": c.description, "status": c.status} for c in sr.checks],
                "warning_details": [
                    {"line": w.line_number, "text": w.line_text} for w in sr.warnings
                ]
            }
            for sr in results
        ]
    }
    return json.dumps(export, ensure_ascii=False, indent=2)


# ──────────────────────────────────────────────
# UI Components
# ──────────────────────────────────────────────
def render_score_bar(passed, total):
    """Thanh tiến trình điểm."""
    if total == 0:
        return
    pct = int(passed / total * 100)
    color = "#28a745" if pct >= 80 else "#ffc107" if pct >= 50 else "#dc3545"
    st.markdown(
        f'<div style="background:#e9ecef;border-radius:8px;height:24px;margin:4px 0">'
        f'<div style="background:{color};width:{pct}%;height:24px;border-radius:8px;'
        f'display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;'
        f'font-weight:600;min-width:40px">{passed}/{total}</div></div>',
        unsafe_allow_html=True
    )


def render_verdict_badge(verdict):
    """Badge kết quả lớn."""
    v = VERDICT_MAP.get(verdict, VERDICT_MAP["KHONG_CO_DU_LIEU"])
    st.markdown(
        f'<div style="background:{v["color"]};color:#fff;padding:12px 20px;'
        f'border-radius:10px;text-align:center;font-size:20px;font-weight:700;'
        f'margin:8px 0">{v["icon"]} {v["label"]}</div>',
        unsafe_allow_html=True
    )


def render_section_detail(sr: SectionResult, sections_data: dict):
    """Render chi tiết 1 mục."""
    sec_name = SECTION_NAMES.get(sr.section_key, sr.section_name)

    if sr.total_checks == 0:
        icon = "⚪"
    elif sr.pass_count == sr.total_checks and not sr.warnings:
        icon = "✅"
    elif sr.pass_count >= sr.total_checks * 0.7:
        icon = "🟡"
    else:
        icon = "🔴"

    header = f"{icon} {sec_name} — {sr.score_text}"
    if sr.warnings:
        header += f"  ⚠️ {len(sr.warnings)} cảnh báo"

    is_problem = sr.pass_count < sr.total_checks or bool(sr.warnings)

    with st.expander(header, expanded=is_problem):
        if sr.canh_bao:
            st.error(f"⚠️ {sr.canh_bao}")

        if sr.checks:
            cols_kw = st.columns([1, 12])
            for c in sr.checks:
                with cols_kw[0]:
                    st.markdown("✓" if c.status == "PASS" else "**✗**")
                with cols_kw[1]:
                    if c.status == "PASS":
                        st.markdown(c.description)
                    else:
                        st.markdown(f"**{c.description}**")

        if sr.warnings:
            st.divider()
            st.markdown("**Ghi chú nội bộ chưa xóa:**")
            for w in sr.warnings:
                st.warning(f"Dòng {w.line_number}: \"{w.line_text}\"")

        text = sections_data.get(sr.section_key, "")
        if text:
            with st.expander("📄 Xem nội dung gốc", expanded=False):
                st.code(text[:5000], language=None)
                if len(text) > 5000:
                    st.caption(f"... (còn {len(text) - 5000} ký tự)")
        elif sr.section_key != "mo_dau":
            st.info("Mục này không tìm thấy trong file.")


def render_file_tab(filename, data):
    """Render toàn bộ kết quả cho 1 file."""
    if "error" in data:
        st.error(f"Lỗi xử lý file: {data['error']}")
        return

    summary = data["summary"]
    results = data["results"]
    sections = data["sections"]
    meta = sections.get("_meta", {})

    # ── Thông tin file ──
    col_info, col_score, col_verdict = st.columns([2, 1, 2])
    with col_info:
        found = meta.get("total_sections_found", 0)
        missing = meta.get("sections_missing", [])
        st.markdown(f"**Mục tìm thấy:** {found}/12")
        if missing:
            st.caption(f"Thiếu: {', '.join(m.replace('muc_', 'Mục ') for m in missing)}")
    with col_score:
        st.markdown(f"**Điểm:**")
        render_score_bar(summary["total_pass"], summary["total_checks"])
    with col_verdict:
        render_verdict_badge(summary["verdict"])

    if summary["total_warnings"] > 0:
        st.warning(f"⚠️ Phát hiện **{summary['total_warnings']}** ghi chú nội bộ chưa xóa trong file")

    st.divider()

    # ── Bảng tổng quan 12 mục ──
    st.subheader("Tổng quan 12 mục")
    overview_cols = st.columns(4)
    for idx, sr in enumerate(results):
        if sr.section_key == "mo_dau":
            continue
        col = overview_cols[(idx - 1) % 4]
        sec_name_short = sr.section_key.replace("muc_", "M")
        if sr.total_checks == 0:
            icon = "⚪"
        elif sr.pass_count == sr.total_checks and not sr.warnings:
            icon = "✅"
        elif sr.pass_count >= sr.total_checks * 0.7:
            icon = "🟡"
        else:
            icon = "🔴"
        col.markdown(f"{icon} **{sec_name_short}** {sr.score_text}")

    st.divider()

    # ── Chi tiết từng mục ──
    st.subheader("Chi tiết từng mục")
    for sr in results:
        if sr.total_checks > 0 or sr.warnings:
            render_section_detail(sr, sections)

    # ── Nút tải kết quả ──
    st.divider()
    dl_col1, dl_col2, dl_col3 = st.columns(3)
    with dl_col1:
        txt_report = build_export_text(filename, data)
        st.download_button(
            "📥 Tải báo cáo (.txt)",
            txt_report,
            file_name=f"TVGS-Check-{Path(filename).stem}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with dl_col2:
        json_report = build_export_json(filename, data)
        st.download_button(
            "📥 Tải JSON",
            json_report,
            file_name=f"TVGS-Check-{Path(filename).stem}.json",
            mime="application/json",
            use_container_width=True,
        )
    with dl_col3:
        # Placeholder for future features
        st.button("🔄 Phân tích lại", key=f"rerun_{filename}",
                   on_click=lambda fn=filename: rerun_file(fn),
                   use_container_width=True)


def rerun_file(filename):
    """Re-run analysis cho 1 file (flag để rerun)."""
    if filename in st.session_state.files:
        st.session_state.files[filename]["_rerun"] = True


# ──────────────────────────────────────────────
# Main App
# ──────────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="TVGS Checker",
        page_icon="🏗️",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    init_state()

    # ── Custom CSS ──
    st.markdown("""
    <style>
    /* Compact header */
    .block-container { padding-top: 2rem; }
    /* File chip style */
    .file-chip {
        display: inline-block;
        background: #f0f2f6;
        border-radius: 16px;
        padding: 4px 12px;
        margin: 2px 4px;
        font-size: 14px;
    }
    .file-chip-active {
        background: #4A90D9;
        color: white;
    }
    /* Hide default streamlit elements */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

    # ── Header ──
    h_col1, h_col2 = st.columns([5, 2])
    with h_col1:
        st.markdown("## 🏗️ TVGS Report Checker")
        st.caption("Kiểm tra nhanh báo cáo hoàn thành TVGS — Tầng 1 Rule-based | TEXO")
    with h_col2:
        st.markdown("")  # spacer

    st.divider()

    # ── Sidebar: Cài đặt dự án ──
    with st.sidebar:
        st.header("⚙️ Cài đặt")
        criteria_path = CRITERIA_DIR

        projects = []
        if criteria_path.exists():
            projects = list_available_projects(criteria_path)

        project_options = ["Tiêu chí chung (mọi dự án)"] + [
            f"{p['ten_cong_trinh']}" for p in projects
        ]
        choice = st.selectbox("Chọn dự án", project_options,
                              help="Chọn dự án để áp dụng tiêu chí kiểm tra riêng")

        project_name = None
        if choice != "Tiêu chí chung (mọi dự án)" and projects:
            idx = project_options.index(choice) - 1
            project_name = projects[idx]["project_key"]
        st.session_state.project_name = project_name

        if projects:
            st.divider()
            st.markdown("**Dự án có sẵn:**")
            for p in projects:
                cap = p.get("cap_cong_trinh", "")
                label = p["ten_cong_trinh"]
                if cap:
                    label += f" — {cap}"
                st.markdown(f"- {label}")

        st.divider()
        st.markdown("**Hướng dẫn:**")
        st.markdown(
            "1. Kéo thả file .docx vào ô upload\n"
            "2. Có thể upload nhiều file cùng lúc\n"
            "3. Xem kết quả từng file ở tab\n"
            "4. Tải báo cáo .txt hoặc .json"
        )
        st.divider()
        st.caption("TVGS Checker v1.0 — TEXO")

    # ── Upload Zone ──
    upload_col, action_col = st.columns([4, 1])

    with upload_col:
        uploaded_files = st.file_uploader(
            "Kéo thả file báo cáo TVGS vào đây",
            type=["docx"],
            accept_multiple_files=True,
            help="Hỗ trợ file .docx — có thể chọn nhiều file cùng lúc",
            label_visibility="visible",
        )

    with action_col:
        st.markdown("")  # spacer for alignment
        st.markdown("")
        if st.session_state.files:
            st.button("🗑️ Xóa tất cả", on_click=clear_all, use_container_width=True,
                      type="secondary")

    # ── Process uploaded files ──
    if uploaded_files:
        criteria_path_resolved = CRITERIA_DIR
        if not criteria_path_resolved.exists():
            st.error(f"Không tìm thấy thư mục criteria: {criteria_path_resolved}")
            st.stop()

        new_files = []
        for uf in uploaded_files:
            fname = uf.name
            needs_run = fname not in st.session_state.files
            if fname in st.session_state.files and st.session_state.files[fname].get("_rerun"):
                needs_run = True
            if needs_run:
                new_files.append((fname, uf))

        if new_files:
            progress = st.progress(0, text="Đang phân tích...")
            for i, (fname, uf) in enumerate(new_files):
                progress.progress(
                    (i + 1) / len(new_files),
                    text=f"Đang phân tích {fname}..."
                )
                result = process_file(uf, criteria_path_resolved,
                                      st.session_state.project_name)
                st.session_state.files[fname] = result
                if st.session_state.active_file is None:
                    st.session_state.active_file = fname
            progress.empty()

    # ── Results ──
    files = st.session_state.files

    if not files:
        # Empty state
        st.markdown("")
        st.markdown("")
        col_empty = st.columns([1, 2, 1])[1]
        with col_empty:
            st.markdown(
                '<div style="text-align:center;padding:40px 0;color:#aaa">'
                '<p style="font-size:48px;margin:0">📄</p>'
                '<p style="font-size:18px">Chưa có file nào</p>'
                '<p>Kéo thả file .docx báo cáo TVGS vào ô upload phía trên</p>'
                '</div>',
                unsafe_allow_html=True
            )
        return

    # File tabs
    if len(files) == 1:
        fname = list(files.keys())[0]
        render_file_tab(fname, files[fname])
    else:
        # Multiple files: use tabs
        tab_names = []
        for fname, data in files.items():
            if "error" in data:
                tab_names.append(f"❌ {fname}")
            else:
                v = data.get("summary", {}).get("verdict", "")
                icon = VERDICT_MAP.get(v, {}).get("icon", "📄")
                tab_names.append(f"{icon} {fname}")

        tabs = st.tabs(tab_names)
        for tab, (fname, data) in zip(tabs, files.items()):
            with tab:
                # Remove button per file
                if st.button(f"🗑️ Xóa file này", key=f"rm_{fname}"):
                    remove_file(fname)
                    st.rerun()
                render_file_tab(fname, data)

        # ── Bảng so sánh nhiều file ──
        if len(files) > 1:
            st.divider()
            st.subheader("📊 So sánh tổng quan")

            compare_data = []
            for fname, data in files.items():
                if "error" in data:
                    continue
                s = data["summary"]
                v = VERDICT_MAP.get(s["verdict"], {})
                compare_data.append({
                    "File": fname,
                    "Điểm": f"{s['total_pass']}/{s['total_checks']}",
                    "Tỷ lệ": f"{int(s['total_pass']/s['total_checks']*100)}%" if s['total_checks'] > 0 else "—",
                    "Cảnh báo": s["total_warnings"],
                    "Đánh giá": v.get("label", "?"),
                })

            if compare_data:
                st.table(compare_data)


if __name__ == "__main__":
    main()
