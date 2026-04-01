"""
Trích xuất nội dung 12 mục từ báo cáo TVGS (.docx).
Hỗ trợ cả heading có đánh số (1. 2. ...) và heading mô tả không số.
"""

import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    from docx import Document as DocxDocument
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# === Heading detection patterns ===

# Numbered patterns: "1.", "1)", "Mục 1", etc.
NUMBERED_PATTERNS = {}
for i in range(1, 13):
    NUMBERED_PATTERNS[i] = [
        re.compile(rf"^\s*{i}\s*[\.)\-:]\s", re.IGNORECASE),
        re.compile(rf"^\s*{i}\s*[\.)\-:]\s*$", re.IGNORECASE),
        re.compile(rf"^\s*Mục\s+{i}\s*[\.:\-]?\s", re.IGNORECASE),
        re.compile(rf"^\s*MỤC\s+{i}\s*[\.:\-]?\s", re.IGNORECASE),
    ]

# Title-based patterns (unnumbered headings)
TITLE_PATTERNS = {
    1:  [r"^Quy mô và thông tin chung", r"^Quy mô công trình"],
    2:  [r"^Đánh giá sự phù hợp về năng lực", r"^Đánh giá.*năng lực.*nhà thầu thi công"],
    3:  [r"^Đánh giá.*khối lượng.*tiến độ", r"^Đánh giá khối lượng"],
    4:  [r"^Đánh giá.*thí nghiệm.*kiểm tra vật liệu", r"^Đánh giá công tác thí nghiệm"],
    5:  [r"^Đánh giá.*kiểm định.*quan trắc", r"^Đánh giá.*công tác tổ chức và kết quả kiểm định"],
    6:  [r"^Đánh giá.*nghiệm thu công việc", r"^Đánh giá.*công tác tổ chức nghiệm thu"],
    7:  [r"^Các thay đổi thiết kế", r"^Thay đổi thiết kế"],
    8:  [r"^Những tồn tại.*khiếm khuyết", r"^Tồn tại.*khiếm khuyết"],
    9:  [r"^Đánh giá.*hồ sơ quản lý chất lượng", r"^Đánh giá.*sự phù hợp của hồ sơ"],
    10: [r"^Đánh giá.*tuân thủ.*pháp luật", r"^Đánh giá.*môi trường.*PCCC"],
    11: [r"^Đánh giá.*quy trình vận hành", r"^Đánh giá.*vận hành.*bảo trì"],
    12: [r"^Kết luận.*điều kiện nghiệm thu", r"^Kết luận.*nghiệm thu"],
}


def detect_section(line: str) -> int | None:
    """Trả về số mục (1-12) nếu dòng là heading, None nếu không."""
    stripped = line.strip()
    if not stripped or len(stripped) > 250:
        return None

    # Numbered headings
    for sec_num, patterns in NUMBERED_PATTERNS.items():
        for pat in patterns:
            if pat.match(stripped):
                return sec_num

    # Title-based headings
    for sec_num, kw_list in TITLE_PATTERNS.items():
        for kw in kw_list:
            if re.match(kw, stripped, re.IGNORECASE):
                return sec_num

    return None


def read_docx_paragraphs(filepath: str | Path) -> list[str]:
    """Đọc tất cả paragraphs từ file .docx."""
    filepath = Path(filepath)

    if HAS_DOCX:
        doc = DocxDocument(str(filepath))
        return [p.text for p in doc.paragraphs]

    # Fallback: đọc XML trực tiếp
    paragraphs = []
    ns = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
    with zipfile.ZipFile(filepath, 'r') as z:
        with z.open('word/document.xml') as f:
            tree = ET.parse(f)
            for para in tree.getroot().iter(f'{{{ns}}}p'):
                texts = [r.text for r in para.iter(f'{{{ns}}}t') if r.text]
                paragraphs.append(''.join(texts))
    return paragraphs


def extract_sections(filepath: str | Path) -> dict:
    """
    Trích xuất 12 mục từ file báo cáo TVGS.

    Returns:
        dict với keys: _meta, mo_dau, muc_1 ... muc_12
        Mỗi mục chứa text đầy đủ. Mục không có sẽ là chuỗi rỗng.
    """
    paragraphs = read_docx_paragraphs(filepath)

    sections = {"mo_dau": []}
    current = "mo_dau"

    for line in paragraphs:
        sec = detect_section(line)
        if sec is not None:
            current = f"muc_{sec}"
            if current not in sections:
                sections[current] = []
        if current not in sections:
            sections[current] = []
        sections[current].append(line)

    # Join and build result
    result = {}
    for key in ["mo_dau"] + [f"muc_{i}" for i in range(1, 13)]:
        lines = sections.get(key, [])
        result[key] = "\n".join(lines).strip()

    found = [k for k in result if k.startswith("muc_") and result[k]]
    result["_meta"] = {
        "source_file": Path(filepath).name,
        "total_sections_found": len(found),
        "sections_found": sorted(found, key=lambda x: int(x.split("_")[1])),
        "sections_missing": [f"muc_{i}" for i in range(1, 13)
                             if f"muc_{i}" not in found]
    }

    return result
