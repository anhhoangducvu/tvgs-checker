"""
TVGS Report Checker — Streamlit App
Kiểm tra nhanh báo cáo hoàn thành TVGS thi công xây dựng.

Chạy: streamlit run app.py
"""

import streamlit as st
import json
import tempfile
from pathlib import Path

from extractor import extract_sections
from rule_checker import (
    load_criteria, run_check, get_summary,
    list_available_projects, SectionResult
)

# === Config ===
CRITERIA_DIR = Path(__file__).parent.parent / "criteria"

# Section names for display
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

VERDICT_DISPLAY = {
    "DAT": ("Đạt yêu cầu Tầng 1", "success"),
    "CAN_SUA_NHE": ("Cần sửa nhẹ", "warning"),
    "CAN_SUA_NHIEU": ("Cần sửa nhiều", "error"),
    "KHONG_CO_DU_LIEU": ("Không có dữ liệu", "info"),
}


def render_section_result(sr: SectionResult, sections_data: dict):
    """Render kết quả 1 mục."""
    sec_name = SECTION_NAMES.get(sr.section_key, sr.section_name)

    # Status icon
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
        header += f" ⚠️ {len(sr.warnings)} cảnh báo"

    with st.expander(header, expanded=(sr.pass_count < sr.total_checks or bool(sr.warnings))):
        # Cảnh báo đặc biệt
        if sr.canh_bao:
            st.error(f"⚠️ {sr.canh_bao}")

        # Checks table
        if sr.checks:
            for c in sr.checks:
                if c.status == "PASS":
                    st.markdown(f"- ✓ {c.description}")
                else:
                    st.markdown(f"- **✗ {c.description}** — thiếu pattern `{c.pattern}`")

        # Warnings
        if sr.warnings:
            st.divider()
            st.markdown("**Ghi chú nội bộ chưa xóa:**")
            for w in sr.warnings:
                st.warning(f"Dòng {w.line_number}: \"{w.line_text}\"")

        # Show section text
        text = sections_data.get(sr.section_key, "")
        if text:
            with st.expander("📄 Xem nội dung mục", expanded=False):
                st.text(text[:3000])
                if len(text) > 3000:
                    st.caption(f"... (còn {len(text) - 3000} ký tự)")
        elif sr.section_key != "mo_dau":
            st.info("Mục này không tìm thấy trong file.")


def main():
    st.set_page_config(
        page_title="TVGS Report Checker",
        page_icon="🏗️",
        layout="wide"
    )

    st.title("🏗️ Kiểm tra Báo cáo TVGS")
    st.caption("Tầng 1 — Rule-based: kiểm tra từ khóa, bảng biểu, ghi chú nội bộ")

    # === Sidebar: Settings ===
    with st.sidebar:
        st.header("⚙️ Cài đặt")

        # Criteria directory
        criteria_dir = st.text_input(
            "Thư mục criteria",
            value=str(CRITERIA_DIR),
            help="Đường dẫn tới thư mục chứa tvgs_chung.json"
        )
        criteria_path = Path(criteria_dir)

        # Project selection
        projects = []
        if criteria_path.exists():
            projects = list_available_projects(criteria_path)

        project_options = ["(Chỉ dùng tiêu chí chung)"] + [
            f"{p['ten_cong_trinh']} ({p['project_key']})" for p in projects
        ]
        project_choice = st.selectbox("Dự án", project_options)

        project_name = None
        if project_choice != "(Chỉ dùng tiêu chí chung)" and projects:
            idx = project_options.index(project_choice) - 1
            project_name = projects[idx]["project_key"]

        st.divider()
        st.markdown("**Dự án có sẵn:**")
        if projects:
            for p in projects:
                cap = p.get("cap_cong_trinh", "")
                st.markdown(f"- {p['ten_cong_trinh']} {f'(Cấp: {cap})' if cap else ''}")
        else:
            st.info("Chưa có criteria dự án riêng")

    # === Main: Upload & Check ===
    uploaded = st.file_uploader(
        "Upload file báo cáo TVGS (.docx)",
        type=["docx"],
        help="File .docx báo cáo hoàn thành công tác TVGS"
    )

    if uploaded is not None:
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            tmp.write(uploaded.read())
            tmp_path = tmp.name

        with st.spinner("Đang trích xuất nội dung..."):
            try:
                sections = extract_sections(tmp_path)
            except Exception as e:
                st.error(f"Lỗi đọc file: {e}")
                return

        meta = sections.get("_meta", {})
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Mục tìm thấy", f"{meta.get('total_sections_found', 0)}/12")
        with col2:
            missing = meta.get("sections_missing", [])
            if missing:
                st.warning(f"Thiếu: {', '.join(missing)}")
            else:
                st.success("Đủ 12 mục")

        # Load criteria and run check
        if not criteria_path.exists():
            st.error(f"Không tìm thấy thư mục criteria: {criteria_path}")
            return

        with st.spinner("Đang kiểm tra Tầng 1..."):
            try:
                criteria = load_criteria(criteria_path, project_name)
                results = run_check(sections, criteria)
                summary = get_summary(results)
            except Exception as e:
                st.error(f"Lỗi kiểm tra: {e}")
                return

        # === Summary ===
        st.divider()
        verdict_text, verdict_type = VERDICT_DISPLAY.get(
            summary["verdict"], ("?", "info")
        )

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Keywords/Tables",
                       f"{summary['total_pass']}/{summary['total_checks']} PASS")
        with col2:
            st.metric("Cảnh báo", summary["total_warnings"])
        with col3:
            getattr(st, verdict_type)(f"**{verdict_text}**")

        # === Detail per section ===
        st.divider()
        st.subheader("Chi tiết từng mục")

        for sr in results:
            if sr.total_checks > 0 or sr.warnings:
                render_section_result(sr, sections)

        # === Export JSON ===
        st.divider()
        with st.expander("📊 Export kết quả (JSON)"):
            export_data = {
                "file": meta.get("source_file", uploaded.name),
                "project": project_name,
                "summary": summary,
                "sections": []
            }
            for sr in results:
                export_data["sections"].append({
                    "key": sr.section_key,
                    "name": sr.section_name,
                    "pass": sr.pass_count,
                    "total": sr.total_checks,
                    "warnings": len(sr.warnings),
                    "checks": [
                        {"desc": c.description, "status": c.status}
                        for c in sr.checks
                    ]
                })

            json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
            st.download_button(
                "Tải JSON",
                json_str,
                file_name=f"tvgs-check-{uploaded.name}.json",
                mime="application/json"
            )

    else:
        # Instructions
        st.info(
            "👆 Upload file .docx báo cáo TVGS để bắt đầu kiểm tra.\n\n"
            "**Quy trình:**\n"
            "1. Chọn dự án (nếu có criteria riêng) ở sidebar\n"
            "2. Upload file .docx\n"
            "3. Xem kết quả Tầng 1 (tự động)\n"
            "4. Export JSON nếu cần lưu"
        )


if __name__ == "__main__":
    main()
