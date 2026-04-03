"""
TVGS Report Checker
Kiểm tra nhanh báo cáo hoàn thành công tác TVGS thi công xây dựng.

Chạy local:  streamlit run app.py
Streamlit Cloud — main file: app/app.py
"""

import streamlit as st
import json
import tempfile
import os
from pathlib import Path
from datetime import datetime

from extractor import extract_sections
from rule_checker import load_criteria, run_check, get_summary, SectionResult

# ── Config ──────────────────────────────────────
CRITERIA_DIR = Path(__file__).parent.parent / "criteria"

SECTION_NAMES = {
    "mo_dau":  "Mở đầu",
    "muc_1":   "1. Quy mô và thông tin chung",
    "muc_2":   "2. Đánh giá năng lực nhà thầu",
    "muc_3":   "3. Khối lượng, tiến độ, ATLĐ",
    "muc_4":   "4. Thí nghiệm, kiểm tra vật liệu",
    "muc_5":   "5. Kiểm định, quan trắc, TN đối chứng",
    "muc_6":   "6. Nghiệm thu công việc XD",
    "muc_7":   "7. Thay đổi thiết kế",
    "muc_8":   "8. Tồn tại, khiếm khuyết, sự cố",
    "muc_9":   "9. Hồ sơ quản lý chất lượng",
    "muc_10":  "10. Tuân thủ pháp luật (MT, PCCC, XD)",
    "muc_11":  "11. Quy trình vận hành, bảo trì",
    "muc_12":  "12. Kết luận nghiệm thu",
}

VERDICT_MAP = {
    "DAT":              ("✅", "success", "ĐẠT yêu cầu"),
    "CAN_SUA_NHE":      ("🟡", "warning", "Cần sửa nhẹ"),
    "CAN_SUA_NHIEU":    ("🔴", "error",   "Cần sửa nhiều"),
    "KHONG_CO_DU_LIEU": ("⚪", "info",    "Không có dữ liệu"),
}


# ── Session state ────────────────────────────────
def init_state():
    if "files" not in st.session_state:
        st.session_state.files = {}


def clear_all():
    st.session_state.files = {}


def remove_file(filename):
    st.session_state.files.pop(filename, None)


# ── Processing ───────────────────────────────────
@st.cache_data(show_spinner=False)
def load_criteria_cached(criteria_dir_str):
    return load_criteria(Path(criteria_dir_str))


def process_file(uploaded_file):
    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    try:
        criteria = load_criteria_cached(str(CRITERIA_DIR))
        sections = extract_sections(tmp_path)
        results  = run_check(sections, criteria)
        summary  = get_summary(results)
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


# ── Export ───────────────────────────────────────
def build_txt(filename, data):
    s = data["summary"]
    v = VERDICT_MAP.get(s["verdict"], ("", "", "?"))
    lines = [
        "=" * 60,
        "BÁO CÁO ĐÁNH GIÁ NHANH — TẦNG 1 (RULE-BASED)",
        "=" * 60,
        f"File      : {filename}",
        f"Thời gian : {data.get('timestamp','')}",
        f"Kết quả   : {v[0]} {v[2]}",
        f"Điểm      : {s['total_pass']}/{s['total_checks']} PASS",
        f"Cảnh báo  : {s['total_warnings']}",
        "",
    ]
    for sr in data["results"]:
        if sr.total_checks == 0 and not sr.warnings:
            continue
        name   = SECTION_NAMES.get(sr.section_key, sr.section_key)
        status = "PASS" if sr.pass_count == sr.total_checks and not sr.warnings else "CẦN XEM"
        lines.append(f"--- {name}  [{sr.score_text}]  {status} ---")
        if sr.canh_bao:
            lines.append(f"  !! CẢNH BÁO: {sr.canh_bao}")
        for c in sr.checks:
            lines.append(f"  {'[V]' if c.status=='PASS' else '[X]'} {c.description}")
        for w in sr.warnings:
            lines.append(f"  [!] Dòng {w.line_number}: \"{w.line_text}\"")
        lines.append("")
    lines += [
        "=" * 60,
        "Kiểm tra Tầng 1 (tự động). Cần xem thêm nội dung chi tiết để đánh giá đầy đủ.",
        f"Công cụ: TVGS Checker — Hoàng Đức Vũ, TEXO",
    ]
    return "\n".join(lines)


def build_json(filename, data):
    s = data["summary"]
    return json.dumps({
        "file": filename,
        "timestamp": data.get("timestamp", ""),
        "summary": s,
        "sections": [
            {
                "key":      sr.section_key,
                "name":     SECTION_NAMES.get(sr.section_key, sr.section_key),
                "pass":     sr.pass_count,
                "total":    sr.total_checks,
                "warnings": len(sr.warnings),
                "checks":   [{"desc": c.description, "status": c.status} for c in sr.checks],
                "warning_details": [{"line": w.line_number, "text": w.line_text} for w in sr.warnings],
            }
            for sr in data["results"]
        ],
    }, ensure_ascii=False, indent=2)


# ── UI: 1 file ───────────────────────────────────
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

    # ── Metrics ──
    c1, c2, c3 = st.columns(3)
    c1.metric("Mục tìm thấy",    f"{meta.get('total_sections_found', 0)} / 12")
    c2.metric("Từ khóa PASS",    f"{summary['total_pass']} / {summary['total_checks']}")
    c3.metric("Ghi chú chưa xóa", summary["total_warnings"])

    missing = meta.get("sections_missing", [])
    if missing:
        st.warning("Không tìm thấy: " + ", ".join(m.replace("muc_", "Mục ") for m in missing))

    getattr(st, v_method)(
        f"{v_icon}  **{v_label}**  —  {summary['total_pass']}/{summary['total_checks']} tiêu chí PASS"
    )

    if summary["total_warnings"] > 0:
        st.warning(
            f"⚠️ Phát hiện **{summary['total_warnings']}** ghi chú nội bộ chưa xóa "
            f"— cần xóa trước khi nộp"
        )

    st.divider()

    # ── Grid tổng quan ──
    st.subheader("Tổng quan 12 mục")
    grid_rows = [results[i::3] for i in range(3)]
    cols = st.columns(3)
    for col, group in zip(cols, grid_rows):
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
            warn = f" ⚠️{len(sr.warnings)}" if sr.warnings else ""
            col.write(f"{icon} **{name}** {sr.score_text}{warn}")

    st.divider()

    # ── Chi tiết từng mục ──
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

        header   = f"{icon} {name} — {sr.score_text}"
        if sr.warnings:
            header += f"  ⚠️ {len(sr.warnings)} cảnh báo"
        expanded = sr.pass_count < sr.total_checks or bool(sr.warnings)

        with st.expander(header, expanded=expanded):
            if sr.canh_bao:
                st.error(f"⚠️ {sr.canh_bao}")
            for c in sr.checks:
                if c.status == "PASS":
                    st.write(f"✅ {c.description}")
                else:
                    st.write(f"❌ **{c.description}**")
            if sr.warnings:
                st.divider()
                st.write("**Ghi chú nội bộ chưa xóa:**")
                for w in sr.warnings:
                    st.warning(f"Dòng {w.line_number}: \"{w.line_text}\"")
            text = sections.get(sr.section_key, "")
            if text:
                with st.expander("📄 Xem nội dung gốc", expanded=False):
                    st.code(text[:5000], language=None)
                    if len(text) > 5000:
                        st.caption(f"... còn {len(text)-5000} ký tự")
            elif sr.section_key != "mo_dau":
                st.info("Mục này không tìm thấy trong file.")

    st.divider()

    # ── Tải kết quả ──
    st.subheader("Tải kết quả")
    stem = Path(filename).stem
    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "📥 Tải báo cáo văn bản (.txt)",
            data=build_txt(filename, data),
            file_name=f"TVGS-Check-{stem}.txt",
            mime="text/plain",
            use_container_width=True,
        )
    with d2:
        st.download_button(
            "📥 Tải dữ liệu JSON",
            data=build_json(filename, data),
            file_name=f"TVGS-Check-{stem}.json",
            mime="application/json",
            use_container_width=True,
        )


# ── Security ──────────────────────────────────────
def check_password():
    """Returns True if the user had the correct password."""
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == "texo2026":
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        # First run, show input for password.
        st.markdown("<h2 style='text-align: center;'>🔐 KHOÁ BẢO MẬT TEXO</h2>", unsafe_allow_html=True)
        st.text_input(
            "Nhập mật khẩu để truy cập hệ thống:", type="password", on_change=password_entered, key="password"
        )
        return False
    elif not st.session_state["password_correct"]:
        # Password incorrect, show input + error.
        st.markdown("<h2 style='text-align: center;'>🔐 KHOÁ BẢO MẬT TEXO</h2>", unsafe_allow_html=True)
        st.text_input(
            "Nhập mật khẩu để truy cập hệ thống:", type="password", on_change=password_entered, key="password"
        )
        st.error("❌ Mật khẩu không chính xác.")
        return False
    else:
        # Password correct.
        return True


# ── Main ─────────────────────────────────────────
def main():
    st.set_page_config(
        page_title="TVGS Checker — TEXO",
        page_icon="🏗️",
        layout="wide",
    )

    if not check_password():
        st.stop()

    init_state()

    st.title("🏗️ TVGS Report Checker")
    st.caption(
        "Kiểm tra nhanh báo cáo hoàn thành công tác Tư vấn Giám sát thi công xây dựng"
    )
    st.divider()

    # ── Sidebar ──
    with st.sidebar:
        st.header("Hướng dẫn sử dụng")
        st.write("**Bước 1:** Kéo thả hoặc chọn file .docx vào ô upload")
        st.write("**Bước 2:** App tự động phân tích — không cần nhấn thêm nút")
        st.write("**Bước 3:** Xem kết quả — các mục có vấn đề sẽ mở sẵn")
        st.write("**Bước 4:** Tải báo cáo .txt hoặc JSON nếu cần lưu")
        st.divider()
        st.write("**Ký hiệu:**")
        st.write("✅ Tìm thấy từ khóa/bảng biểu")
        st.write("❌ Thiếu — cần bổ sung")
        st.write("🟡 Đạt ≥ 70% tiêu chí")
        st.write("🔴 Chưa đạt — cần sửa nhiều")
        st.write("⚠️ Ghi chú nội bộ chưa xóa")
        st.divider()
        st.caption(
            "TVGS Checker v2.0  \n"
            "Tác giả: **Hoàng Đức Vũ**  \n"
            "Trưởng phòng Kỹ thuật  \n"
            "Công ty CP TEXO Tư vấn và Đầu tư"
        )

    # ── Upload ──
    uploaded_files = st.file_uploader(
        "Kéo thả hoặc chọn file báo cáo TVGS (.docx)",
        type=["docx"],
        accept_multiple_files=True,
        help="Có thể chọn nhiều file cùng lúc để so sánh",
    )

    if st.session_state.files:
        st.button("🗑️ Xóa tất cả file", on_click=clear_all)

    # ── Xử lý ──
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
                st.session_state.files[fname] = process_file(uf)
            bar.empty()

    files = st.session_state.files

    if not files:
        st.info(
            "Chưa có file nào. Upload file .docx báo cáo TVGS ở ô phía trên — "
            "app sẽ tự động kiểm tra và hiển thị kết quả ngay."
        )
        return

    # ── Hiển thị ──
    if len(files) == 1:
        fname, data = next(iter(files.items()))
        st.subheader(f"📄 {fname}")
        if st.button("🗑️ Xóa file này"):
            remove_file(fname)
            st.rerun()
        render_file(fname, data)
    else:
        tab_labels = []
        for fname, data in files.items():
            if "error" in data:
                tab_labels.append(f"❌ {fname}")
            else:
                icon = VERDICT_MAP.get(data["summary"]["verdict"], ("⚪",))[0]
                tab_labels.append(f"{icon} {fname}")

        tabs = st.tabs(tab_labels)
        for tab, (fname, data) in zip(tabs, files.items()):
            with tab:
                if st.button("🗑️ Xóa file này", key=f"rm_{fname}"):
                    remove_file(fname)
                    st.rerun()
                render_file(fname, data)

        # So sánh
        st.divider()
        st.subheader("📊 So sánh nhanh")
        rows = []
        for fname, data in files.items():
            if "error" in data:
                rows.append({"File": fname, "Điểm": "—", "Tỷ lệ": "—",
                             "Cảnh báo": "—", "Đánh giá": "Lỗi"})
                continue
            s = data["summary"]
            icon, _, label = VERDICT_MAP.get(s["verdict"], ("⚪", "", "?"))
            pct = f"{s['total_pass']/s['total_checks']*100:.0f}%" if s["total_checks"] else "—"
            rows.append({
                "File":      fname,
                "Điểm":     f"{s['total_pass']}/{s['total_checks']}",
                "Tỷ lệ":    pct,
                "Cảnh báo": s["total_warnings"],
                "Đánh giá": f"{icon} {label}",
            })
        st.table(rows)


if __name__ == "__main__":
    main()
