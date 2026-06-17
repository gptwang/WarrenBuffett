"""抓取巴菲特致股东信 → 原始文件 + Markdown（MinerU）

版本选择:
    1977-1997: 直接 HTML（页面即信件内容）→ mineru crawl
    1998-2003: 导航页，下载 PDF 版本 → mineru extract --model vlm
    2004-2024: 直接 PDF → mineru extract --model vlm

用法:
    python scrape_letters.py                 # 抓取所有年份（已存在跳过）
    python scrape_letters.py --year 1998     # 单年
    python scrape_letters.py --year 1977-2024
    python scrape_letters.py --year 1998 --force   # 强制重新下载+转换

依赖: pip install requests
需要: mineru-open-api + MINERU_TOKEN
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import requests

BASE_URL = "https://www.berkshirehathaway.com/letters"
ROOT = Path(__file__).resolve().parent


def load_token() -> str:
    token = os.environ.get("MINERU_TOKEN", "")
    if token:
        return token
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("MINERU_TOKEN="):
                token = line.split("=", 1)[1].strip()
                if token:
                    return token
    return ""


def fetch_letter_list():
    """从 letters.html 解析所有年份链接"""
    resp = requests.get(f"{BASE_URL}/letters.html", headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    links = re.findall(r'href\s*=\s*"(.*?)"', resp.text, re.IGNORECASE)

    letters = []
    for href in links:
        if href.startswith("http") or href.startswith("letters_files/"):
            continue
        m = re.match(r"(\d{4})(ltr)?\.(html|pdf)", href)
        if m:
            year = int(m.group(1))
            ext = m.group(3)
            if 1977 <= year <= 2024:
                letters.append((year, f"{BASE_URL}/{href}", ext, href))
    letters.sort()
    return letters


def fetch_page(url: str) -> str:
    """获取页面 HTML 内容"""
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    return resp.text


def download_file(url: str, save_path: Path) -> bool:
    """下载文件"""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=120)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f" [下载失败: {e}]")
        return False


def resolve_source(year, base_url, ext):
    """
    解析最佳数据源:
    - 1977-1997 HTML: 页面即信件内容
    - 1998-2003 HTML: 导航页 → 下载 PDF 版本
    - 2004+ PDF: 直接使用
    返回: (download_url, raw_name, ext_for_mineru)
    """
    if ext == "pdf":
        return base_url, f"{year}ltr.pdf", "pdf"

    html = fetch_page(base_url)
    # 导航页中的 PDF 链接，格式多样: 1998pdf.pdf / final1999pdf.pdf / 2003ltr.pdf
    pdf_match = re.search(r'href="([^"]*(?:pdf|ltr)\.pdf)"', html, re.IGNORECASE)

    if pdf_match:
        pdf_path = pdf_match.group(1)
        pdf_url = f"{BASE_URL}/{pdf_path}"
        raw_name = f"{year}.pdf"
        return pdf_url, raw_name, "pdf"

    return base_url, f"{year}.html", "html"


def _run_mineru(cmd: list, env: dict, tmp_dir: Path) -> tuple[Path | None, str]:
    """执行 mineru 命令，返回 (md_file_path, error_msg)。error_msg 为空表示成功。"""
    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, timeout=600,
        shell=True if sys.platform == "win32" else False,
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout).strip()
        # 提取关键错误行
        lines = [l for l in err.split("\n") if l.strip()]
        return None, lines[-1] if lines else "unknown error"
    md_files = list(tmp_dir.glob("*.md"))
    if md_files:
        return md_files[0], ""
    return None, "no .md output"


def convert_with_mineru(src_path: Path, url: str, ext: str, token: str,
                        dest_path: Path) -> bool:
    """MinerU 转换 → 写入 dest_path。返回 True 表示成功。

    HTML: crawl（免费，无需 token）
    PDF:  extract --model vlm（高精度表格，需 token）
    """
    tmp_dir = Path(tempfile.mkdtemp(prefix="mineru_"))
    try:
        env = os.environ.copy()

        if ext == "html":
            md_file, err = _run_mineru(
                ["mineru-open-api", "crawl", url, "-o", str(tmp_dir)], env, tmp_dir)
        else:
            if not token:
                print("[FAIL] PDF 转换需要 MINERU_TOKEN")
                return False
            env["MINERU_TOKEN"] = token
            print("vlm ...", end=" ", flush=True)
            md_file, err = _run_mineru(
                ["mineru-open-api", "extract", str(src_path),
                 "-o", str(tmp_dir), "--model", "vlm"],
                env, tmp_dir)

        if err:
            print(f"[FAIL] {err}")
            return False

        shutil.move(str(md_file), str(dest_path))
        return True
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    parser = argparse.ArgumentParser(description="抓取巴菲特致股东信")
    parser.add_argument("--year", "-y", help="年份，如 1998 或 1977-2024")
    parser.add_argument("--output", "-o", default="letters", help="输出目录")
    parser.add_argument("--force", "-f", action="store_true", help="强制重新下载和转换")
    args = parser.parse_args()

    token = load_token()
    output_dir = ROOT / args.output
    output_dir.mkdir(parents=True, exist_ok=True)

    year_min, year_max = 1977, 2024
    if args.year:
        m = re.match(r"(\d{4})(?:-(\d{4}))?", args.year)
        if m:
            year_min = int(m.group(1))
            year_max = int(m.group(2) or m.group(1))

    all_letters = fetch_letter_list()
    targets = [(y, u, e, n) for y, u, e, n in all_letters if year_min <= y <= year_max]
    print(f"找到 {len(targets)} 封信（{year_min}-{year_max}）")

    ok = fail = skip = 0
    for year, url, ext, raw_name in targets:
        md_path = output_dir / f"{year}.md"

        if not args.force and md_path.exists():
            print(f"[{year}] 跳过（已存在）")
            skip += 1
            continue

        # 1) 解析最佳数据源
        dl_url, raw_fname, mineru_ext = resolve_source(year, url, ext)
        raw_path = output_dir / raw_fname

        # 2) 下载原始文件（如需要）
        if not raw_path.exists() or args.force:
            print(f"[{year}] 下载 {raw_fname} ({mineru_ext}) ...", end=" ", flush=True)
            if not download_file(dl_url, raw_path):
                fail += 1
                continue

        # 3) MinerU 转换
        print(f"[{year}] 转换 {raw_fname} ...", end=" ", flush=True)
        if convert_with_mineru(raw_path, dl_url, mineru_ext, token, md_path):
            print(f"OK ({md_path.stat().st_size:,} bytes)")
            ok += 1
        else:
            fail += 1

    print(f"\n完成: {ok} 成功, {skip} 跳过, {fail} 失败")


if __name__ == "__main__":
    main()
