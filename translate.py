"""巴菲特股东信中译引擎 — DeepSeek 翻译，保留金融术语准确性 + 巴氏语气

用法:
    cp .env.example .env          # 编辑 .env，填入 DEEPSEEK_API_KEY
    python translate.py           # 翻译全部
    python translate.py --year 1957 1958 1959 1960   # 翻译指定年份
    python translate.py --dry-run --year 1957        # 预览（不调用 API）
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
LETTERS = ROOT / "letters"
OUT_DIR = ROOT / "letters_zh"


# ═══════════════════════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LLMConfig:
    api_key: str = ""
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"


def _load_env() -> dict[str, str]:
    """读取脚本目录下的 .env 文件（简单 key=value 解析，无外部依赖）"""
    env_path = ROOT / ".env"
    if not env_path.exists():
        return {}
    env = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        env[key] = val
    return env


def get_config() -> LLMConfig:
    """获取 LLM 配置：先读 .env，再读环境变量（环境变量优先级更高）"""
    env = _load_env()

    api_key = os.environ.get("DEEPSEEK_API_KEY") or env.get("DEEPSEEK_API_KEY", "")
    base_url = os.environ.get("DEEPSEEK_BASE_URL") or env.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("DEEPSEEK_MODEL") or env.get("DEEPSEEK_MODEL", "deepseek-v4-flash")

    return LLMConfig(api_key=api_key, base_url=base_url, model=model)


# ═══════════════════════════════════════════════════════════════════════════════
# 翻译提示词
# ═══════════════════════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一位资深金融翻译专家，专精于将沃伦·巴菲特的股东信从英文翻译为中文。

## 你的翻译准则

### 语气风格
- 巴菲特的语言特点是：口语化但不随意，幽默自嘲但不失严谨，善用比喻讲道理
- 中文必须还原这种"老派智慧长者聊天"的感觉——像是在跟合伙人拉家常，但每句话都有分量
- 保持原文的句式节奏：短句有力，长句清晰
- 幽默和自嘲的地方要译出味道，不能干巴巴直译

### 金融术语（必须统一使用以下译法）
- partnership → 合伙企业
- Limited Partner → 有限合伙人
- General Partner → 普通合伙人
- work-out / workouts → 套利交易（依赖特定公司行动的套利型投资）
- undervalued securities → 低估证券
- general issues → 普通股投资
- control situations → 控制型投资
- intrinsic value → 内在价值
- Dow / Dow-Jones Industrials / the Averages → 道指
- blue-chip / blue chip → 蓝筹股
- bear market → 熊市
- bull market → 牛市
- mutual fund → 共同基金
- merger → 并购
- liquidation → 清算
- tender → 要约收购
- arbitrage / arbitrageur → 套利 / 套利者
- fiduciary → 受托人
- float → 浮存金
- underwriting → 承销
- goodwill → 商誉
- amortization → 摊销
- depreciation → 折旧
- retained earnings → 留存收益
- book value → 账面价值
- return on equity → 净资产收益率
- share repurchase / buyback → 股份回购
- derivative → 衍生品
- insurance subsidiary → 保险子公司
- reinsurance → 再保险
- catastrophe loss → 巨灾损失
- combined ratio → 综合成本率
- S&P 500 → 标普500

### 格式规则（极其重要）
- 原文中的 HTML 标签（<table>、<tr>、<td>、<sup> 等）必须原样保留，不可修改结构
- 表格中只翻译文字内容（表头、说明），数字和数据绝对不能改动
- LaTeX 数学公式（$...$）原样保留
- Markdown 标题（##）保留
- 脚注编号（(1)、(2) 等）保持对应
- 公司名称首次出现时保留英文原名并附中文译名，如：Berkshire Hathaway（伯克希尔·哈撒韦）
- 人名保留英文原文，如：Warren E. Buffett、Charlie Munger
- 日期格式转为中文：July 9, 1965 → 1965年7月9日
- 百分比和数字格式不变：8.470% → 8.470%
- 金额保留原格式：$4 billion → 40亿美元

### 翻译策略
- 只输出翻译后的中文 Markdown，不要添加任何额外说明、注释或元信息
- 不要遗漏任何段落
- 遇到不懂的金融术语，优先保持专业译法，不凭空猜测
- 如果原文有歧义，保持歧义，不要自行解释"""


# ═══════════════════════════════════════════════════════════════════════════════
# API 调用
# ═══════════════════════════════════════════════════════════════════════════════

def translate_letter(content: str, cfg: LLMConfig, retries: int = 3) -> str:
    """调用 DeepSeek 翻译单封信，支持重试"""
    timeout = httpx.Timeout(600.0, connect=30.0)

    user_prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        "请将以下巴菲特股东信翻译为中文。\n\n"
        "重要：你的输出必须是合法的 JSON 格式，包含一个 translation 字段：\n"
        '{"translation": "<翻译后的完整 Markdown>"}\n\n'
        f"---\n\n{content}"
    )

    for attempt in range(1, retries + 1):
        try:
            resp = httpx.post(
                f"{cfg.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {cfg.api_key}"},
                json={
                    "model": cfg.model,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "max_tokens": 65536,
                    "response_format": {"type": "json_object"},
                },
                timeout=timeout,
            )
            resp.raise_for_status()
            result = resp.json()
            raw = result["choices"][0]["message"]["content"]
            data = json.loads(raw)
            return data.get("translation", data.get("content", raw))

        except (json.JSONDecodeError, KeyError):
            # JSON 解析失败时，尝试直接返回原始内容
            raw = result["choices"][0]["message"].get("content", "")
            if raw and len(raw) > 100:
                return raw
            raise

        except Exception as e:
            if attempt < retries:
                wait = attempt * 5
                print(f"重试 {attempt}/{retries}...", end=" ", flush=True)
                time.sleep(wait)
            else:
                raise


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def translate_all(years: list[str] | None = None, dry_run: bool = False):
    """翻译巴菲特股东信

    Args:
        years: 要翻译的年份列表，None 表示全部
        dry_run: True 只打印计划，不实际翻译
    """
    cfg = get_config()
    if not cfg.api_key:
        print("[ERROR] 未配置 DEEPSEEK_API_KEY", file=sys.stderr)
        print("  方式一: cp .env.example .env 然后编辑 .env 填入 Key", file=sys.stderr)
        print("  方式二: export DEEPSEEK_API_KEY=sk-xxx", file=sys.stderr)
        sys.exit(1)

    if not LETTERS.exists():
        print(f"[ERROR] 找不到信件目录: {LETTERS}", file=sys.stderr)
        sys.exit(1)

    all_md = sorted(
        [f for f in LETTERS.glob("*.md") if not f.stem.endswith("b")],
        key=lambda x: (int(x.stem[:4]), x.stem),
    )

    if years:
        all_md = [f for f in all_md if f.stem[:4] in years]

    if not all_md:
        print("[提示] 没有找到需要翻译的文件")
        return

    OUT_DIR.mkdir(exist_ok=True)

    print(f"模型: {cfg.model}")
    print(f"源目录: {LETTERS}")
    print(f"输出目录: {OUT_DIR}")
    print(f"待翻译: {len(all_md)} 封")
    print()

    for i, md_path in enumerate(all_md, 1):
        name = md_path.name
        out_path = OUT_DIR / name

        if out_path.exists():
            print(f"[跳过 {i}/{len(all_md)}] {name} — 已存在")
            continue

        content = md_path.read_text(encoding="utf-8")
        size_kb = len(content.encode("utf-8")) / 1024

        if dry_run:
            print(f"[模拟 {i}/{len(all_md)}] {name} ({size_kb:.0f} KB)")
            continue

        print(f"[翻译 {i}/{len(all_md)}] {name} ({size_kb:.0f} KB)...", end=" ", flush=True)

        try:
            translated = translate_letter(content, cfg)
            out_path.write_text(translated, encoding="utf-8")
            zh_size = len(translated.encode("utf-8")) / 1024
            print(f"✓ ({zh_size:.0f} KB)")
        except Exception as e:
            print(f"✗ 失败: {e}")
            continue

    print(f"\n[完成] 翻译结果保存在 {OUT_DIR.resolve()}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="巴菲特股东信中译")
    ap.add_argument("--year", type=str, nargs="*", help="翻译指定年份，如 --year 1957 1958 1959 1960")
    ap.add_argument("--dry-run", action="store_true", help="仅列出待翻译文件，不调用 API")
    args = ap.parse_args()
    translate_all(years=args.year or None, dry_run=args.dry_run)
