"""
TVGS Report Checker — Streamlit App
Kiểm tra nhanh báo cáo hoàn thành TVGS thi công xây dựng.

Chạy local:  streamlit run app.py
Deploy:      Streamlit Cloud — main file: app/app.py
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

# ── Config ──────────────────────────────────────
CRITERIA_DIR = Path(__file__).parent.parent / "criteria"

SECTION_NAMES = {
    "mo_dau": "Mở đầu",
    "muc_1":  "1. Quy mô và thông tin chung",
    "muc_2":  "2. Đánh giá năng lực nhà thầu",
    "muc_3":  "3. Khối lượng, tiến độ, ATLĐ",
    "muc_4":  "4. Thí nghiệm, kiểm tra vật liệu",
    "muc_5":  "5. Kiểm định, quan trắc, TN đối chứng",
    "muc_6":  "6. Nghiệm thu công việc XD",
    "muc_7":  "7. Thay đổi thiết kế",
    "muc_8":  "8. Tồn tại, khiếm khuyết, sự cố",
    "muc_9":  "9. Hồ sơ quản lý chất lượng",
    "muc_10": "10. Tuân thủ pháp luật (MT, PCCC, XD)",
    "muc_11": "11. Quy trình vận hành, bảo trì",
    "muc_12": "12. Kết luận nghiệm thu",
}

# Verdict: (emoji, streamlit method name, short label)
VERDICT_MAP = {
    "DAT":            ("✅", "success", "ĐẠT yêu cầu"),
    "CAN_SUA_NHE":    ("🟡", "warning", "Cần sửa nhẹ"),
    "CAN_SUA_NHIEU":  ("🔴", "error",   "Cần sửa nhiều"),
    "KHONG_CO_DU_LIEU": ("⚪", "info",  "Không có dữ liệu"),
}


# ── Session state ────────────────────────────────
def init_state():
    for key, val in [
        ("files", {}),
        ("project_name", None),
    ]:
        if key not in st.session_state:
            st.session_state[key] = val


def clear_all():
    st.session_state.files = {}


def remove_file(filename):
    st.session_state.files.pop(filename, None)


# ── Processing ───────────────────────────────────
def process_file(uploaded_file, criteria_path, project_name):
    """Đọc file, trích xuất 12 mục, chạy kiểm tra, trả dict kết quả."""
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    try:
        sections  = extract_sections(tmp_path)
        criteria  = load_criteria(criteria_path, project_name)
        results   = run_check(sections, criteria)
        summary   = get_summary(results)
        return {
            "sections":  sections,
            "results":   results,
            "summary":   summary,
            "timestamp": datetime.now().strftime("%H:%M %d/%m/%Y"),
        }
    except Exception as e:
        return {"error": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


# ── Export helpers ────────────────────────────────
def build_txt(filename, data):
    s   = data["summary"]
    v   = VERDICT_MAP.get(s["verdict"], ("", "", "?"))
    out = []
    out.append("=" * 60)
    out.append("BÁO CÁO ĐÁNH GIÁ NHANH — TẦNG 1 (RULE-BASED)")
    out.append("=" * 60)
    out.append(f"File      : {filename}")
    out.append(f"Thời gian : {data.get('timestamp','')}")
    out.append(f"Kết quả   : {v[0]} {v[2]}")
    out.append(f"Điểm      : {s['total_pass']}/{s['total_checks']} PASS")
    out.append(f"Cảnh báo  : {s['total_warnings']}")
    out.append("")
    for sr in data["results"]:
        if sr.total_checks == 0 and not sr.warnings:
            continue
        name   = SECTION_NAMES.get(sr.section_key, sr.section_key)
        status = "PASS" if sr.pass_count == sr.total_checks and not sr.warnings else "CẦN XEM"
        out.append(f"--- {name}  [{sr.score_text}]  {status} ---")
        if sr.canh_bao:
            out.append(f"  !! CẢNH BÁO: {sr.canh_bao}")
        for c in sr.checks:
            out.append(f"  {'[V]' if c.status=='PASS' else '[X]'} {c.description}")
        for w in sr.warnings:
            out.append(f"  [!] Dòng {w.line_number}: \"{w.line_text}\"")
        out.append("")
    out.append("=" * 60)
    out.append("Đây là kiểm tra Tầng 1 (tự động). Cần xem xét thêm nội dung chi tiết.")
    return "\n".join(out)


def build_json(filename, data):
    s = data["summary"]
    export = {
        "file": filename,
        "timestamp": data.get("timestamp", ""),
        "summary": s,
        "sections": [
            {
                "key": sr.section_key,
                "name": SECTION_NAMES.get(sr.section_key, sr.section_key),
                "pass": sr.pass_count,
                "total": sr.total_checks,
                "warnings": len(sr.warnings),
                "checks": [{"desc": c.description, "status": c.status} for c in sr.checks],
                "warning_details": [{"line": w.line_number, "text": w.line_text} for w in sr.warnings],
            }
            for sr in data["results"]
        ],
    }
    return json.dumps(export, ensure_ascii=False, indent=2)


# ── UI: render 1 file result ─────────────────────
def render_file(filename, data):
    if "error" in data:
        st.error(f"Lỗi xử lý file: {data['error']}")
        return

    summary  = data["summary"]
    results  = data["results"]
    sections = data["sections"]
    meta     = sections.get("_meta", {})
    v_icon, v_method, v_label = VERDICT_MAP.get(
        summary["verdict"], ("⚪", "info", "Không xác định")
    )

    # ── Thông tin nhanh ────────────────────────
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Mục tìm thấy", f"{meta.get('total_sections_found', 0)} / 12")
    col_b.metric("Từ khóa PASS",
                 f"{summary['total_pass']} / {summary['total_checks']}")
    col_c.metric("Ghi chú chưa xóa", summary["total_warnings"])

    missing = meta.get("sections_missing", [])
    if missing:
        st.warning(f"Không tìm thấy: {', '.join(m.replace('muc_','Mục ') for m in missing)}")

    # Verdict banner dùng native Streamlit (không dùng HTML)
    getattr(st, v_method)(f"{v_icon}  **{v_label}**  —  {summary['total_pass']}/{summary['total_checks']} tiêu chí PASS")

    if summary["total_warnings"] > 0:
        st.warning(f"⚠️ Phát hiện **{summary['total_warnings']}** ghi chú nội bộ chưa xóa trong file — cần xóa trước khi nộp")

    st.divider()

    # ── Tổng quan 12 mục (grid text) ───────────
    st.subheader("Tổng quan 12 mục")

    # Chia 3 cột
    grid = [results[i::3] for i in range(3)]
    cols = st.columns(3)
    for col, group in zip(cols, grid):
        for sr in group:
            if sr.section_key == "mo_dau":
                continue
            name = SECTION_NAMES.get(sr.section_key, sr.section_key)
            if sr.total_checks == 0:
                icon = "⚪"
            elif sr.pass_count == sr.total_checks and not sr.warnings:
                icon = "✅"
            elif sr.pass_count >= sr.total_checks * 0.7:
                icon = "🟡"
            else:
                icon = "🔴"
            warn_txt = f" ⚠️{len(sr.warnings)}" if sr.warnings else ""
            col.write(f"{icon} **{name}** {sr.score_text}{warn_txt}")

    st.divider()

    # ── Chi tiết từng mục ──────────────────────
    st.subheader("Chi tiết từng mục")

    for sr in results:
        if sr.total_checks == 0 and not sr.warnings:
            continue
        name = SECTION_NAMES.get(sr.section_key, sr.section_name)

        if sr.total_checks == 0:
            icon = "⚪"
        elif sr.pass_count == sr.total_checks and not sr.warnings:
            icon = "✅"
        elif sr.pass_count >= sr.total_checks * 0.7:
            icon = "🟡"
        else:
            icon = "🔴"

        header = f"{icon} {name} — {sr.score_text}"
        if sr.warnings:
            header += f"  ⚠️ {len(sr.warnings)} cảnh báo"

        # Mục có vấn đề thì mở sẵn
        expanded = sr.pass_count < sr.total_checks or bool(sr.warnings)

        with st.expander(header, expanded=expanded):
            if sr.canh_bao:
                st.error(f"⚠️ {sr.canh_bao}")

            if sr.checks:
                for c in sr.checks:
                    if c.status == "PASS":
                        st.write(f"✅ {c.description}")
                    else:
                        st.write(f"❌ **{c.description}** — chưa tìm thấy trong nội dung")

            if sr.warnings:
                st.divider()
                st.write("**Ghi chú nội bộ chưa xóa:**")
                for w in sr.warnings:
                    st.warning(f"Dòng {w.line_number}: \"{w.line_text}\"")

            text = sections.get(sr.section_key, "")
            if text:
                with st.expander("📄 Xem nội dung gốc trong file", expanded=False):
                    st.code(text[:5000], language=None)
                    if len(text) > 5000:
                        st.caption(f"... (còn {len(text)-5000} ký tự)")
            elif sr.section_key != "mo_dau":
                st.info("Mục này không tìm thấy trong file.")

    st.divider()

    # ── Nút tải kết quả ────────────────────────
    st.subheader("Tải kết quả")
    dl1, dl2 = st.columns(2)
    stem = Path(filename).stem
    with dl1:
        st.download_button(
            label="📥 Tải báo cáo văn bản (.txt)",
            data=build_txt(filename, data),
            file_name=f"TVGS-Check-{stem}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with dl2:
        st.download_button(
            label="📥 Tải dữ liệu JSON",
            data=build_json(filename, data),
            file_name=f"TVGS-Check-{stem}.json",
            mime="application/json",
            use_container_width=True,
        )


# ── Main ─────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="TVGS Checker — TEXO",
        page_icon="🏗️",
        layout="wide",
    )

    init_state()

    st.title("🏗️ TVGS Report Checker")
    st.caption("Kiểm tra nhanh báo cáo hoàn thành công tác Tư vấn Giám sát thi công xây dựng | TEXO")

    st.divider()

    # ── Sidebar ────────────────────────────────
    with st.sidebar:
        st.header("⚙️ Cài đặt")

        # Danh sách dự án từ criteria/
        projects = []
        if CRITERIA_DIR.exists():
            projects = list_available_projects(CRITERIA_DIR)

        options = ["Tiêu chí chung (mọi dự án)"] + [
            p["ten_cong_trinh"] or p["project_key"] for p in projects
        ]
        choice = st.selectbox(
            "Chọn dự án",
            options,
            help="Chọn dự án để áp dụng tiêu chí đặc thù. Nếu không chắc, chọn 'Tiêu chí chung'."
        )

        project_name = None
        if choice != options[0] and projects:
            idx = options.index(choice) - 1
            project_name = projects[idx]["project_key"]
        st.session_state.project_name = project_name

        if projects:
            st.divider()
            st.write("**Dự án có trong hệ thống:**")
            for p in projects:
                cap = p.get("cap_cong_trinh", "")
                st.write(f"• {p['ten_cong_trinh']}" + (f" ({cap})" if cap else ""))

        st.divider()
        st.write("**Cách dùng:**")
        st.write("1. Chọn dự án (nếu có)")
        st.write("2. Upload file .docx")
        st.write("3. Xem kết quả tự động")
        st.write("4. Tải báo cáo về")
        st.divider()
        st.caption("TVGS Checker v1.0 · TEXO")

    # ── Upload zone ────────────────────────────
    uploaded_files = st.file_uploader(
        "Kéo thả hoặc chọn file báo cáo TVGS (.docx)",
        type=["docx"],
        accept_multiple_files=True,
        help="Hỗ trợ chọn nhiều file cùng lúc",
    )

    # Nút Xóa tất cả (chỉ hiện khi có file)
    if st.session_state.files:
        st.button("🗑️ Xóa tất cả file", on_click=clear_all)

    # ── Xử lý file mới upload ──────────────────
    if uploaded_files:
        if not CRITERIA_DIR.exists():
            st.error(f"Không tìm thấy thư mục criteria: {CRITERIA_DIR}")
            st.stop()

        new = [(f.name, f) for f in uploaded_files
               if f.name not in st.session_state.files]

        if new:
            bar = st.progress(0, text="Đang phân tích...")
            for i, (fname, uf) in enumerate(new, 1):
                bar.progress(i / len(new), text=f"Đang xử lý: {fname}")
                st.session_state.files[fname] = process_file(
                    uf, CRITERIA_DIR, st.session_state.project_name
                )
            bar.empty()

    # ── Hiển thị kết quả ──────────────────────
    files = st.session_state.files

    if not files:
        st.info(
            "Chưa có file nào. Hãy upload file .docx báo cáo TVGS ở ô phía trên.\n\n"
            "App sẽ tự động kiểm tra và hiển thị kết quả ngay."
        )
        return

    if len(files) == 1:
        # 1 file: hiển thị thẳng
        fname, data = next(iter(files.items()))
        st.subheader(f"📄 {fname}")
        col_rm, _ = st.columns([1, 5])
        if col_rm.button("🗑️ Xóa file này"):
            remove_file(fname)
            st.rerun()
        render_file(fname, data)

    else:
        # Nhiều file: tabs
        tab_labels = []
        for fname, data in files.items():
            if "error" in data:
                tab_labels.append(f"❌ {fname}")
            else:
                v_icon = VERDICT_MAP.get(
                    data["summary"]["verdict"], ("⚪",)
                )[0]
                tab_labels.append(f"{v_icon} {fname}")

        tabs = st.tabs(tab_labels)
        for tab, (fname, data) in zip(tabs, files.items()):
            with tab:
                if st.button(f"🗑️ Xóa file này", key=f"rm_{fname}"):
                    remove_file(fname)
                    st.rerun()
                render_file(fname, data)

        # Bảng so sánh
        st.divider()
        st.subheader("📊 So sánh nhanh các file")
        rows = []
        for fname, data in files.items():
            if "error" in data:
                rows.append({"File": fname, "Điểm": "—", "Tỷ lệ": "—",
                             "Cảnh báo": "—", "Đánh giá": "Lỗi"})
                continue
            s = data["summary"]
            v_icon, _, v_label = VERDICT_MAP.get(s["verdict"], ("⚪","","?"))
            pct = (f"{s['total_pass']/s['total_checks']*100:.0f}%"
                   if s["total_checks"] else "—")
            rows.append({
                "File":      fname,
                "Điểm":     f"{s['total_pass']}/{s['total_checks']}",
                "Tỷ lệ":    pct,
                "Cảnh báo": s["total_warnings"],
                "Đánh giá": f"{v_icon} {v_label}",
            })
        st.table(rows)


if __name__ == "__main__":
    main()
