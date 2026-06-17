"""临时：按年切分 1957-1976 股东信 PDF

来源: Warren-Buffett-Berkshire-Letters-1957-2012.pdf
输出: letters/{year}.pdf 或 letters/{year}a.pdf / {year}b.pdf（多年信）

检测规则:
- "1957 Letter" ~ "1976 Letter" → 年份边界
- "BUFFETT PARTNERSHIP" + 日期 → 合伙信边界
"""

from pypdf import PdfReader, PdfWriter
from pathlib import Path
import re

PDF_PATH = Path(__file__).parent / "Warren-Buffett-Berkshire-Letters-1957-2012.pdf"
OUT_DIR = Path(__file__).parent / "letters"


def detect_boundaries(reader: PdfReader, max_page: int = 200) -> list[tuple[int, str, int | None]]:
    """扫描页面，返回 [(start_page, label, year), ...] 边界列表"""
    boundaries = []
    seen_pages = set()
    last_year = None  # 继承给无年份的 BP 信

    for i in range(min(max_page, len(reader.pages))):
        text = reader.pages[i].extract_text()
        if not text.strip():
            continue

        lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
        first_line = lines[0] if lines else ""

        # "1957 Letter" / "1960 Letter" etc.
        m = re.match(r"(\d{4})\s+Letter", first_line, re.IGNORECASE)
        if m:
            year = int(m.group(1))
            if 1957 <= year <= 2024 and i not in seen_pages:
                boundaries.append((i, f"{year} Letter", year))
                seen_pages.add(i)
                last_year = year
            continue

        # "BUFFETT PARTNERSHIP, LTD." 信头
        if re.match(r"BUFFETT\s+PARTNERSHIP", first_line.upper()):
            if i not in seen_pages:
                dm = re.search(
                    r"(January|February|March|April|May|June|"
                    r"July|August|September|October|November|December)"
                    r"\s+\d{1,2},\s+(\d{4})",
                    text[:2000])
                if dm:
                    month, yr = dm.group(1), int(dm.group(2))
                    # 1-2月的信是总结上一年的 → 归到 yr-1
                    if month in ("January", "February"):
                        yr -= 1
                else:
                    yr = last_year
                boundaries.append((i, f"BP {yr}", yr))
                seen_pages.add(i)
                if yr:
                    last_year = yr
            continue

    return boundaries


def assign_letters(boundaries: list, total_pages: int) -> list[dict]:
    """将边界组为信件列表，每封信 {"start": int, "end": int, "label": str, "year": int}"""
    letters = []
    for idx, (start, label, year) in enumerate(boundaries):
        end = boundaries[idx + 1][0] if idx + 1 < len(boundaries) else total_pages
        letters.append({"start": start, "end": end, "label": label, "year": year})
    return letters


def name_letter(letters: list[dict]) -> list[dict]:
    """为每封信分配文件名（同年多信用 a/b 后缀）"""
    year_count = {}
    result = []
    for lt in letters:
        y = lt.get("year") or 0
        year_count[y] = year_count.get(y, 0) + 1
        suffix = chr(ord("a") + year_count[y] - 1) if year_count[y] > 1 else ""
        lt["filename"] = f"{y}{suffix}.pdf" if y else f"unknown_{lt['start']:03d}.pdf"
        result.append(lt)
    return result


def main():
    reader = PdfReader(str(PDF_PATH))
    total = len(reader.pages)
    print(f"PDF: {total} 页")

    # 扫描边界
    boundaries = detect_boundaries(reader, max_page=250)
    print(f"检测到 {len(boundaries)} 个边界:")
    for pg, label, year in boundaries:
        print(f"  p{pg:3d}: {label}")

    # 组信件
    letters = assign_letters(boundaries, total)
    letters = name_letter(letters)

    # 只输出 1957-1976
    target = [lt for lt in letters if lt["year"] is not None and 1957 <= lt["year"] <= 1976]
    print(f"\n1957-1976 共 {len(target)} 封信:")

    for lt in target:
        start, end = lt["start"], lt["end"]
        fname = lt["filename"]
        out_path = OUT_DIR / fname

        writer = PdfWriter()
        for pg in range(start, end):
            writer.add_page(reader.pages[pg])

        with open(out_path, "wb") as f:
            writer.write(f)

        print(f"  {fname}: p{start}-{end - 1} ({end - start} 页) [{lt['label']}]")

    print(f"\n完成，输出到 {OUT_DIR}/")


if __name__ == "__main__":
    main()
