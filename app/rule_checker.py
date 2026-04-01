"""
Kiểm tra Tầng 1 (rule-based) cho báo cáo TVGS.
Đọc criteria JSON, chạy regex/keyword matching trên nội dung 12 mục.
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class CheckResult:
    """Kết quả kiểm tra 1 tiêu chí."""
    section: str
    check_type: str  # "keyword" | "table" | "leftover_note"
    description: str
    status: str      # "PASS" | "MISSING" | "WARNING"
    pattern: str = ""
    line_number: int = 0
    line_text: str = ""


@dataclass
class SectionResult:
    """Tổng hợp kết quả kiểm tra 1 mục."""
    section_key: str
    section_name: str
    text_found: bool
    text_length: int
    checks: list[CheckResult] = field(default_factory=list)
    warnings: list[CheckResult] = field(default_factory=list)
    canh_bao: str = ""

    @property
    def pass_count(self):
        return sum(1 for c in self.checks if c.status == "PASS")

    @property
    def total_checks(self):
        return len(self.checks)

    @property
    def score_text(self):
        if self.total_checks == 0:
            return "—"
        return f"{self.pass_count}/{self.total_checks}"


def load_criteria(criteria_dir: str | Path, project_name: str = None) -> dict:
    """
    Load và merge criteria: tvgs_chung.json + (optional) tvgs_{project}.json
    """
    criteria_dir = Path(criteria_dir)
    chung_path = criteria_dir / "tvgs_chung.json"

    with open(chung_path, "r", encoding="utf-8") as f:
        chung = json.load(f)

    if not project_name:
        return chung

    project_path = criteria_dir / f"tvgs_{project_name}.json"
    if not project_path.exists():
        return chung

    with open(project_path, "r", encoding="utf-8") as f:
        project = json.load(f)

    # Deep merge
    import copy
    merged = copy.deepcopy(chung)

    for key in project:
        if not key.startswith("muc_") and key != "mo_dau":
            continue

        proj_sec = project[key]
        if key not in merged:
            merged[key] = {}

        # bo_sung = append
        if "bo_sung" in proj_sec:
            for fld in ["tu_khoa_bat_buoc", "cau_hoi_tu_duy", "loi_thuong_gap", "bang_bieu_bat_buoc"]:
                if fld in proj_sec["bo_sung"] and proj_sec["bo_sung"][fld]:
                    merged[key].setdefault(fld, []).extend(proj_sec["bo_sung"][fld])

        # ghi_de = replace
        if "ghi_de" in proj_sec:
            for fld, val in proj_sec["ghi_de"].items():
                merged[key][fld] = val

        # Copy canh_bao
        if "_canh_bao" in proj_sec:
            merged[key]["_canh_bao"] = proj_sec["_canh_bao"]

    return merged


def check_regex(text: str, pattern: str) -> bool:
    """Kiểm tra regex pattern trên text."""
    try:
        return bool(re.search(pattern, text, re.IGNORECASE))
    except re.error:
        return pattern.lower() in text.lower()


def check_section_keywords(section_key: str, text: str, criteria: dict) -> list[CheckResult]:
    """Kiểm tra từ khóa bắt buộc cho 1 mục."""
    sec_crit = criteria.get(section_key, {})
    results = []

    for kw in sec_crit.get("tu_khoa_bat_buoc", []):
        pat = kw["pattern"] if isinstance(kw, dict) else kw
        desc = kw.get("mo_ta", pat) if isinstance(kw, dict) else pat
        found = check_regex(text, pat)
        results.append(CheckResult(
            section=section_key,
            check_type="keyword",
            description=desc,
            status="PASS" if found else "MISSING",
            pattern=pat
        ))

    for tbl in sec_crit.get("bang_bieu_bat_buoc", []):
        pat = tbl["pattern"] if isinstance(tbl, dict) else tbl
        name = tbl.get("ten", pat) if isinstance(tbl, dict) else pat
        found = check_regex(text, pat)
        results.append(CheckResult(
            section=section_key,
            check_type="table",
            description=name,
            status="PASS" if found else "MISSING",
            pattern=pat
        ))

    return results


def check_leftover_notes(full_text: str, criteria: dict) -> list[CheckResult]:
    """Phát hiện ghi chú nội bộ chưa xóa."""
    config = criteria.get("pattern_ghi_chu_chua_xoa", {})
    if not config or "patterns" not in config:
        return []

    results = []
    lines = full_text.split("\n")

    for pat_item in config["patterns"]:
        pattern = pat_item["pattern"]
        desc = pat_item.get("mo_ta", pattern)
        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            continue

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and len(stripped) < 150 and regex.search(stripped):
                results.append(CheckResult(
                    section="full_text",
                    check_type="leftover_note",
                    description=desc,
                    status="WARNING",
                    line_number=i + 1,
                    line_text=stripped[:100]
                ))

    return results


def run_check(sections: dict, criteria: dict) -> list[SectionResult]:
    """
    Chạy toàn bộ kiểm tra Tầng 1.

    Args:
        sections: dict từ extractor.extract_sections()
        criteria: dict từ load_criteria()

    Returns:
        list[SectionResult] cho mỗi mục
    """
    section_keys = ["mo_dau"] + [f"muc_{i}" for i in range(1, 13)]
    results = []

    # Build full text for leftover notes check
    full_text = "\n".join(sections.get(k, "") for k in section_keys)

    # Check leftover notes globally
    all_warnings = check_leftover_notes(full_text, criteria)

    for sec_key in section_keys:
        text = sections.get(sec_key, "")
        sec_crit = criteria.get(sec_key, {})
        sec_name = sec_crit.get("ten", sec_key)

        checks = check_section_keywords(sec_key, text, criteria)

        # Assign relevant warnings to this section
        sec_warnings = [w for w in all_warnings
                        if sec_key != "mo_dau"]  # simplified assignment

        canh_bao = sec_crit.get("_canh_bao", "")

        sr = SectionResult(
            section_key=sec_key,
            section_name=sec_name,
            text_found=bool(text.strip()),
            text_length=len(text),
            checks=checks,
            warnings=[],  # will assign below
            canh_bao=canh_bao
        )
        results.append(sr)

    # Better warning assignment: match by line content overlap
    for w in all_warnings:
        # Assign to the section whose text contains the warning line
        assigned = False
        for sr in results:
            sec_text = sections.get(sr.section_key, "")
            if w.line_text and w.line_text in sec_text:
                sr.warnings.append(w)
                assigned = True
                break
        if not assigned and results:
            results[0].warnings.append(w)

    return results


def get_summary(results: list[SectionResult]) -> dict:
    """Tạo bảng tổng kết."""
    total_pass = sum(r.pass_count for r in results)
    total_checks = sum(r.total_checks for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    sections_with_issues = [r for r in results
                           if r.pass_count < r.total_checks or r.warnings]

    if total_checks == 0:
        verdict = "KHONG_CO_DU_LIEU"
    elif total_pass == total_checks and total_warnings == 0:
        verdict = "DAT"
    elif (total_checks - total_pass) <= 3:
        verdict = "CAN_SUA_NHE"
    else:
        verdict = "CAN_SUA_NHIEU"

    return {
        "total_pass": total_pass,
        "total_checks": total_checks,
        "total_warnings": total_warnings,
        "verdict": verdict,
        "sections_with_issues": len(sections_with_issues),
    }


def list_available_projects(criteria_dir: str | Path) -> list[dict]:
    """Liệt kê các file criteria dự án có sẵn."""
    criteria_dir = Path(criteria_dir)
    projects = []

    for f in sorted(criteria_dir.glob("tvgs_*.json")):
        if f.name == "tvgs_chung.json":
            continue
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            name = data.get("_meta", {}).get("name", f.stem)
            du_an = data.get("du_an", {})
            projects.append({
                "file": f.name,
                "project_key": f.stem.replace("tvgs_", ""),
                "name": name,
                "ten_cong_trinh": du_an.get("ten_cong_trinh", ""),
                "cap_cong_trinh": du_an.get("cap_cong_trinh", ""),
            })
        except (json.JSONDecodeError, KeyError):
            pass

    return projects
