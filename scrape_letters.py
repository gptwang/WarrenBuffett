"""抓取巴菲特致股东信 → 原始文件 + Markdown（MinerU）

目录结构:
    letters/
      1977.html      ← 原始 HTML
      1977.md        ← MinerU 转换
      2004ltr.pdf    ← 原始 PDF
      2004.md        ← MinerU 转换
      ...

用法:
    python scrape_letters.py                     # 抓取所有年份
    python scrape_letters.py --year 1977         # 只抓某一年
    python scrape_letters.py --year 1977-2024    # 抓取年份范围

依赖:
    pip install requests
    npm install -g mineru-open-api

配置:
    复制 .env.example → .env，填入 MINERU_TOKEN
    或设置环境变量: export MINERU_TOKEN=xxx
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import requests

BASE_URL = "https://www.berkshirehathaway.com/letters"
ROOT = Path(__file__).resolve().parent


def load_token() -> str:
    """加载 MinerU token（优先级: 环境变量 > .env）"""
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
    print("[ERROR] 未找到 MINERU_TOKEN，请设置环境变量或在 .env 中配置")
    print("        获取 token: https://mineru.net/apiManage/token")
    sys.exit(1)


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


def download_raw(url: str, save_path: Path) -> bool:
    """下载原始文件"""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        resp.raise_for_status()
        save_path.write_bytes(resp.content)
        return True
    except Exception as e:
        print(f" [下载失败: {e}]")
        return False


def convert_with_mineru(raw_path: Path, url: str, output_dir: Path, ext: str, token: str):
    """MinerU 转换 → Markdown"""
    output_dir.mkdir(parents=True, exist_ok=True)

    if ext == "html":
        cmd = ["mineru-open-api", "crawl", url, "-o", str(output_dir)]
    else:
        cmd = ["mineru-open-api", "flash-extract", str(raw_path), "-o", str(output_dir)]

    env = os.environ.copy()
    env["MINERU_TOKEN"] = token

    result = subprocess.run(
        cmd, env=env, capture_output=True, text=True, timeout=600,
        shell=True if sys.platform == "win32" else False,
    )
    if result.returncode != 0:
        print(f" [FAIL] {result.stderr.strip()}")
        return None

    for f in output_dir.iterdir():
        if f.suffix == ".md":
            return f
    return None


def main():
    parser = argparse.ArgumentParser(description="抓取巴菲特致股东信")
    parser.add_argument("--year", "-y", help="年份，如 1977 或 1977-2024")
    parser.add_argument("--output", "-o", default="letters", help="输出目录")
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
        raw_path = output_dir / raw_name
        md_path = output_dir / f"{year}.md"

        if md_path.exists() and raw_path.exists():
            print(f"[{year}] 跳过（已存在）")
            skip += 1
            continue

        if not raw_path.exists():
            print(f"[{year}] 下载 {raw_name} ...", end=" ", flush=True)
            if not download_raw(url, raw_path):
                fail += 1
                continue

        print(f"[{year}] 转换 {raw_name} ...", end=" ", flush=True)
        result = convert_with_mineru(raw_path, url, output_dir, ext, token)
        if result:
            if result.name != f"{year}.md":
                result.rename(md_path)
            print(f"OK ({md_path.stat().st_size:,} bytes)")
            ok += 1
        else:
            fail += 1

    print(f"\n完成: {ok} 成功, {skip} 跳过, {fail} 失败")


if __name__ == "__main__":
    main()
