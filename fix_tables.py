"""修复 MinerU crawl 丢失的表格数据

策略：直接复制 HTML 原始内容替换 MD 中对应的块，不用 AI。

- <PRE> 块 → 替换 MD ``` code block（年份标签丢失）
- <TABLE> 块 → 替换 MD <table> 块（结构简化/数据丢失）

用法:
    python fix_tables.py --year 1990               # 修复单年
    python fix_tables.py --year 1977-1997          # 修复所有 HTML 年份
    python fix_tables.py --year 1977-1997 --dry-run  # 只分析，不修改
"""

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).parent
LETTERS = ROOT / "letters"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

def strip_tags(text: str) -> str:
    """去除 HTML 标签（<I> </I> <B> 等），保留内容。"""
    return re.sub(r"<[^>]+>", "", text)


def extract_pre_blocks(html: str) -> list[str]:
    """提取所有 <PRE> 块内容（去标签、去首尾空白）。"""
    blocks = re.findall(r"<PRE>(.*?)</PRE>", html, re.DOTALL)
    return [strip_tags(b).strip() for b in blocks]


def extract_table_blocks(html: str) -> list[str]:
    """提取所有 <TABLE ...>...</TABLE> 原始 HTML。"""
    return re.findall(r"(<TABLE[^>]*>.*?</TABLE>)", html, re.DOTALL | re.IGNORECASE)


def find_code_blocks(md: str) -> list[tuple[int, int, str]]:
    """找到所有 ``` 代码块，返回 (start, end, content)。"""
    blocks = []
    for m in re.finditer(r"```\s*\n(.*?)\n```", md, re.DOTALL):
        blocks.append((m.start(), m.end(), m.group(1).strip()))
    return blocks


def find_md_tables(md: str) -> list[tuple[int, int, str]]:
    """找到 MD 中所有 <table>...</table> 块，返回 (start, end, content)。"""
    return [(m.start(), m.end(), m.group(0)) for m in
            re.finditer(r"<table[^>]*>.*?</table>", md, re.DOTALL | re.IGNORECASE)]


# ---------------------------------------------------------------------------
# Fix
# ---------------------------------------------------------------------------

def fix_pre_blocks(html: str, md: str) -> tuple[str, int, int]:
    """PRE → code block：直接复制原始内容替换。返回 (new_md, fixed, total)。"""
    pre_blocks = extract_pre_blocks(html)
    # 过滤空块（1997 有 <PRE></PRE> 只含空白）
    pre_blocks = [b for b in pre_blocks if len(b) >= 10]
    code_blocks = find_code_blocks(md)

    n = min(len(pre_blocks), len(code_blocks))
    if n == 0:
        return md, 0, 0
    if len(pre_blocks) != len(code_blocks):
        print(f"   [WARN] PRE 块({len(pre_blocks)})与 code 块({len(code_blocks)})数量不一致，"
              f"处理前 {n} 个")

    fixed, total = 0, n
    new_md = md

    # 从后往前替换
    for idx in range(n - 1, -1, -1):
        pre_text = pre_blocks[idx]
        code_start, code_end, code_text = code_blocks[idx]

        if pre_text == code_text:
            continue  # 内容一致，跳过

        print(f"   [FIX] PRE #{idx + 1}/{n} ({len(pre_text)} chars)")
        # 替换：保持 ``` 围栏
        new_md = (new_md[:code_start]
                  + "```\n" + pre_text + "\n```"
                  + new_md[code_end:])
        fixed += 1

    return new_md, fixed, total


def is_data_table(table_html: str) -> bool:
    """判断是否是数据表格（含多行数字数据），排除布局/签名表。"""
    # 先去掉 HTML 标签，只统计内容中的数字（避免匹配到属性值如 width=624）
    text = strip_tags(table_html)
    nums = len(re.findall(r"\b[\d,.]{2,}\b", text))
    rows = len(re.findall(r"<tr[^>]*>", table_html, re.IGNORECASE))
    return nums >= 5 and rows >= 3


def fix_table_blocks(html: str, md: str) -> tuple[str, int, int]:
    """TABLE → table：两边都只取数据表，按顺序一一对应替换。"""
    html_tables = extract_table_blocks(html)
    md_tables = find_md_tables(md)

    # 两边都过滤，只留数据表
    html_data = [(i, t) for i, t in enumerate(html_tables) if is_data_table(t)]
    md_data = [(s, e, t) for s, e, t in md_tables if is_data_table(t)]

    n = min(len(html_data), len(md_data))
    if n == 0:
        return md, 0, 0
    if len(html_data) != len(md_data):
        print(f"   [WARN] HTML 数据表({len(html_data)})与 MD 数据表({len(md_data)})数量不一致，"
              f"处理前 {n} 个")

    fixed, total = 0, n
    new_md = md

    # 按顺序对应（都过滤后数量应一致）
    for k in range(1, n + 1):
        html_idx, html_tbl = html_data[-k]
        html_tbl = html_tbl.strip()
        md_start, md_end, _ = md_data[-k]

        if html_tbl == new_md[md_start:md_end].strip():
            continue

        print(f"   [FIX] TABLE HTML#{html_idx + 1} ({len(html_tbl)} chars)")
        new_md = new_md[:md_start] + html_tbl + new_md[md_end:]
        fixed += 1

    return new_md, fixed, total


def fix_year(year: int, dry_run: bool = False) -> dict:
    """修复某年的 MD 文件。"""
    html_path = LETTERS / f"{year}.html"
    md_path = LETTERS / f"{year}.md"

    if not html_path.exists():
        return {"status": "skip", "reason": "no_html"}
    if not md_path.exists():
        return {"status": "skip", "reason": "no_md"}

    html = html_path.read_text(encoding="cp1252", errors="replace")
    md = md_path.read_text(encoding="utf-8")

    # PRE 块
    new_md, pre_fixed, pre_total = fix_pre_blocks(html, md)

    # TABLE 块
    new_md, tbl_fixed, tbl_total = fix_table_blocks(html, new_md)

    total_fixed = pre_fixed + tbl_fixed
    total_checked = pre_total + tbl_total

    if total_fixed > 0 and not dry_run:
        md_path.write_text(new_md, encoding="utf-8")
        print(f"   [OK] PRE {pre_fixed}/{pre_total}, TABLE {tbl_fixed}/{tbl_total}, 已写入")
    elif dry_run and total_fixed > 0:
        print(f"   [DRY] PRE {pre_fixed}/{pre_total}, TABLE {tbl_fixed}/{tbl_total}（未修改）")
    else:
        print(f"   [OK] 无需修复（{total_checked} 个块完好）")

    return {"status": "ok", "fixed": total_fixed, "checked": total_checked}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_years(arg: str) -> list[int]:
    """--year: '1990' 或 '1977-1997'。"""
    if "-" in arg:
        parts = arg.split("-")
        return list(range(int(parts[0]), int(parts[1]) + 1))
    return [int(arg)]


def main():
    parser = argparse.ArgumentParser(description="修复 MinerU crawl 丢失的表格数据（直接复制原始内容）")
    parser.add_argument("--year", required=True, help="年份，如 1990 或 1977-1997")
    parser.add_argument("--dry-run", action="store_true", help="只分析不修改")
    args = parser.parse_args()

    years = parse_years(args.year)

    total_fixed, total_checked = 0, 0
    for y in years:
        print(f"\n{y}:")
        result = fix_year(y, args.dry_run)
        if result["status"] == "ok":
            total_fixed += result.get("fixed", 0)
            total_checked += result.get("checked", 0)
        elif result["status"] == "skip":
            print(f"   [SKIP] {result.get('reason', '')}")

    print(f"\n{'[dry-run] ' if args.dry_run else ''}总计: "
          f"修复 {total_fixed}/{total_checked} 个块")


if __name__ == "__main__":
    main()
