"""修复 MinerU crawl 丢失的表格数据（HTML PRE → MD code block）

MinerU `crawl` 转换 HTML→MD 时，<PRE> 块的第一列（年份、序号等）
偶尔被丢弃。此脚本检出受影响的表格块，调用 DeepSeek 修复。

用法:
    python fix_tables.py --year 1990               # 修复单年
    python fix_tables.py --year 1977-1997          # 修复所有 HTML 年份
    python fix_tables.py --year 1977-1997 --dry-run  # 只分析，不修改

依赖: pip install httpx python-dotenv
配置: .env 中 DEEPSEEK_API_KEY + DEEPSEEK_BASE_URL
     或环境变量 DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL
"""

import argparse
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).parent
LETTERS = ROOT / "letters"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_env():
    """读取 .env，env var 优先级更高。"""
    env_file = ROOT / ".env"
    if env_file.exists():
        load_dotenv(env_file)
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    if not api_key:
        print("[ERROR] 缺少 DEEPSEEK_API_KEY（请在 .env 中配置）")
        sys.exit(1)
    return api_key, base_url


def strip_html_tags(text: str) -> str:
    """去除 HTML 标签（如 <I> </I> <B> 等）。"""
    return re.sub(r"<[^>]+>", "", text)


def extract_pre_blocks(html: str) -> list[str]:
    """从 HTML 提取所有 <PRE> 块内容（去标签、trim）。"""
    blocks = re.findall(r"<PRE>(.*?)</PRE>", html, re.DOTALL)
    return [strip_html_tags(b).strip() for b in blocks]


def extract_code_blocks(md: str) -> list[tuple[int, int, str]]:
    """从 Markdown 提取所有 ``` 代码块，返回 (start, end, content)。"""
    blocks = []
    for m in re.finditer(r"```\s*\n(.*?)\n```", md, re.DOTALL):
        blocks.append((m.start(), m.end(), m.group(1).strip()))
    return blocks


def is_table_block(text: str) -> bool:
    """判断一个 PRE/code 块是否是数据表格（非纯代码/排版）。"""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 3:
        return False
    numeric_rows = 0
    for line in lines:
        # 统计行内数字 token 个数
        num_count = len(re.findall(r"\b[\d,.$%()+-]+\b", line))
        if num_count >= 2:
            numeric_rows += 1
    # 超过一半的行包含数字 → 表格
    return numeric_rows >= len(lines) * 0.4


def extract_data_lines(text: str) -> list[str]:
    """提取数据行：跳过表头、分隔线、空行、合计行（以 Total 开头）。"""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过分隔线
        if re.match(r"^[-=]+\s*$", stripped):
            continue
        # 跳过表头行（纯文字比例太高）
        words = stripped.split()
        if not words:
            continue
        nums = re.findall(r"\b[\d,.$%()+-]+\b", stripped)
        # 至少 30% 的 token 是数字才算数据行
        if len(nums) / len(words) < 0.3:
            continue
        lines.append(stripped)
    return lines


def count_tokens(text: str) -> int:
    """粗算 token 数（1 token ≈ 3 字符）。"""
    return max(1, len(text) // 3)


def needs_fix(html_block: str, md_block: str) -> bool:
    """比较 HTML PRE 和 MD code 块：行数或数字数不一致则需要修复。"""
    html_lines = extract_data_lines(html_block)
    md_lines = extract_data_lines(md_block)
    if len(html_lines) != len(md_lines):
        return True
    # 逐行比数字 token 数
    for hl, ml in zip(html_lines, md_lines):
        if len(re.findall(r"[\d,.$%()+-]+", hl)) != len(
            re.findall(r"[\d,.$%()+-]+", ml)
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# DeepSeek
# ---------------------------------------------------------------------------

FIX_PROMPT = """你是严谨的数据校对助手。

HTML <PRE> 块包含完整的表格数据。Markdown 代码块是自动转换后的版本，
可能丢失了每行开头的年份或序号。

任务：
1. 对比两个块，找出 Markdown 中缺失的数据
2. 修复 Markdown 代码块，补齐所有缺失数据
3. 不要改变原有格式（对齐、间距、符号）
4. 只返回修复后的代码块内容（纯文本，不要用 ``` 包裹，不要解释）"""


def call_deepseek(api_key: str, base_url: str, html_block: str, md_block: str) -> str:
    """发送 HTML PRE + MD code 块到 DeepSeek，返回修复后的 MD 块。"""
    user_msg = f"""HTML <PRE> 块（完整数据）:
<pre>
{html_block}
</pre>

Markdown 代码块（可能有缺失）:
{md_block}"""

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": FIX_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.1,
        "max_tokens": max(4096, count_tokens(md_block) * 3),
    }

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=120,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return content.strip()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def fix_year(year: int, api_key: str, base_url: str, dry_run: bool = False) -> dict:
    """修复某年的 MD 文件。返回统计 dict。"""
    html_path = LETTERS / f"{year}.html"
    md_path = LETTERS / f"{year}.md"

    if not html_path.exists():
        return {"status": "skip", "reason": "no_html"}
    if not md_path.exists():
        return {"status": "skip", "reason": "no_md"}

    # 读取文件
    html = html_path.read_text(encoding="latin-1", errors="replace")
    md = md_path.read_text(encoding="utf-8")

    pre_blocks = extract_pre_blocks(html)
    code_blocks = extract_code_blocks(md)

    # 筛选表格型 PRE 块
    table_pres = [(i, b) for i, b in enumerate(pre_blocks) if is_table_block(b)]
    table_codes = [(s, e, b) for s, e, b in code_blocks if is_table_block(b)]

    if len(table_pres) != len(table_codes):
        print(
            f"   [WARN] 表格块数量不匹配: HTML {len(table_pres)} vs MD {len(table_codes)}，"
            f"跳过（无法一一对应）"
        )
        return {"status": "skip", "reason": "block_count_mismatch"}

    fixed_count = 0
    skip_count = 0
    new_md = md  # 原地替换

    # 从后往前替换（避免 offset 偏移）
    for (pre_idx, pre_text), (code_start, code_end, code_text) in reversed(
        list(zip(table_pres, table_codes))
    ):
        if not needs_fix(pre_text, code_text):
            skip_count += 1
            continue

        print(
            f"   [FIX] 修复表 #{pre_idx + 1} "
            f"({count_tokens(pre_text)} + {count_tokens(code_text)} tokens)..."
        )

        if dry_run:
            print(f"      [dry-run] 跳过实际调用")
            fixed_count += 1
            continue

        try:
            fixed = call_deepseek(api_key, base_url, pre_text, code_text)
            # 替换
            new_md = new_md[:code_start] + "```\n" + fixed + "\n```" + new_md[code_end:]
            fixed_count += 1
        except Exception as e:
            print(f"      [ERROR] 修复失败: {e}")
            return {"status": "error", "error": str(e)}

    # 写回
    if fixed_count > 0 and not dry_run:
        md_path.write_text(new_md, encoding="utf-8")
        print(f"   [OK] 修复 {fixed_count} 个表，跳过 {skip_count} 个，已写入")
    else:
        print(f"   [OK] 无需修复（{skip_count} 个表完好）")

    return {"status": "ok", "fixed": fixed_count, "skipped": skip_count}


def parse_years(arg: str) -> list[int]:
    """解析 --year 参数：单年 '1990' 或范围 '1977-1997'。"""
    if "-" in arg:
        parts = arg.split("-")
        return list(range(int(parts[0]), int(parts[1]) + 1))
    return [int(arg)]


def main():
    parser = argparse.ArgumentParser(description="修复 MinerU crawl 丢失的表格数据")
    parser.add_argument("--year", required=True, help="年份，如 1990 或 1977-1997")
    parser.add_argument("--dry-run", action="store_true", help="只分析不修改")
    args = parser.parse_args()

    api_key, base_url = load_env()
    years = parse_years(args.year)

    total_fixed, total_skipped = 0, 0
    for y in years:
        print(f"\n{y}:")
        result = fix_year(y, api_key, base_url, args.dry_run)
        if result["status"] == "ok":
            total_fixed += result.get("fixed", 0)
            total_skipped += result.get("skipped", 0)
        elif result["status"] == "skip":
            print(f"   ⏭️ 跳过（{result.get('reason', '')}）")

    print(f"\n{'[dry-run] ' if args.dry_run else ''}总计: "
          f"修复 {total_fixed} 个表，跳过 {total_skipped} 个表")


if __name__ == "__main__":
    main()
