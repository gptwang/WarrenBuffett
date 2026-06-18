"""巴菲特股东信中译引擎 — DeepSeek 流式翻译

用法:
    cp .env.example .env          # 编辑 .env，填入 DEEPSEEK_API_KEY
    python translate.py           # 翻译全部
    python translate.py --year 1957 1958   # 翻译指定年份
    python translate.py --dry-run         # 预览（不调用 API）
"""

import argparse
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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

    def pick(key: str, default: str = "") -> str:
        return os.environ.get(key) or env.get(key, "") or default

    api_key = pick("DEEPSEEK_API_KEY")
    base_url = pick("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = pick("DEEPSEEK_MODEL", "deepseek-v4-flash")

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
- **比喻是巴菲特行文的灵魂**：农耕、棒球、扑克、婚姻、动物等比喻意象必须保留，用对应中文意象还原，不要直译成抽象概念。如"farming"译为"耕作"而非"农业"；遇到中文读者陌生的美国本土比喻，可在首次出现时加简短括注
- **自嘲与反讽要译出味道**：遇到自嘲/挖苦/双关，用中文对应的幽默方式还原，不要干巴巴字面直译。宁可意译出俏皮感，也不要把玩笑译成陈述句
- **坦诚认错的语气**：巴菲特承认投资失误时直白坦荡、不文过饰非（这是他罕见的品质），译文要保留这种坦诚直接，不要用四平八稳的官腔稀释
- **保留破折号与括号节奏**：巴菲特爱用破折号（—）和括号插入补充说明，制造"边说边补"的口语感，译文应保留这种句式节奏，不要全改成逗号长句

### 金融术语（必须统一使用以下译法）
# —— 合伙企业架构 ——
- partnership → 合伙企业
- Limited Partner → 有限合伙人
- General Partner → 普通合伙人
- fiduciary → 受托人
# —— 巴菲特三大投资分类（"类"字统一，1969年前合伙信核心框架）——
- undervalued securities → 低估类股票（巴菲特合伙信投资分类之一）
- undervalued situations → 低估类标的（同上，原文用 situations 时亦指此分类）
- general issues / Generals → 低估类投资（与"套利类""控制类"并列的投资类别专名，不可译"普通股投资"）
- work-out / workouts → 套利类投资（依赖特定公司行动的套利，对应原文 workouts）
- control situations / Controls → 控制类投资
- arbitrage / arbitrageur → 套利 / 套利者
# —— 巴菲特/格雷厄姆核心投资哲学（全篇高频，必须定译）——
- intrinsic value → 内在价值
- margin of safety → 安全边际
- Mr. Market → 市场先生（格雷厄姆拟人化比喻，巴菲特高频引用）
- circle of competence → 能力圈
- owner earnings → 所有者盈余
- look-through earnings → 透视盈余
- economic goodwill → 经济商誉（区别于 accounting goodwill 会计商誉）
- cigar-butt / cigar butt → 雪茄烟蒂（捡烟蒂式投资）
- moat / economic moat → 护城河 / 经济护城河
- institutional imperative → 机构惯性（企业被惯性驱使做蠢事的倾向）
- headwind / tailwind → 逆风 / 顺风
- skin in the game → 利益绑定（管理层与股东共担风险）
- float → 浮存金
- book value → 账面价值
- retained earnings → 留存收益
- return on equity → 净资产收益率
- share repurchase / buyback → 股份回购
# —— 市场/证券 ——
- Dow / Dow-Jones Industrials / the Averages → 道指
- blue-chip / blue chip → 蓝筹股
- bear market → 熊市
- bull market → 牛市
- mutual fund → 共同基金
- S&P 500 → 标普500
- merger → 并购
- liquidation → 清算
- tender → 要约收购
- preferred stock → 优先股
- common stock → 普通股
- warrants → 认股权证
- convertible → 可转换
- Class A / Class B shares → A类股 / B类股
- proxy → 股东委托书
- operating earnings / operating profit → 经营利润
# —— 会计/保险 ——
- goodwill → 商誉（统称；区别经济/会计商誉时用上条译法）
- amortization → 摊销
- depreciation → 折旧
- underwriting → 承销
- insurance subsidiary → 保险子公司
- reinsurance → 再保险
- catastrophe loss → 巨灾损失
- super-cat / supercatastrophe → 超级巨灾
- combined ratio → 综合成本率
- derivative → 衍生品
- GAAP → 美国通用会计准则

### 反翻译腔（译文地道的关键）
- 避免"被……所……""当……的时候""对于……而言""是……的"等典型翻译腔
- 英文被动句尽量改中文主动句，除非强调承受方
- 英文长从句可适当断句，但保持逻辑层次不丢；不要硬译成冗长欧化长句
- 叙述年度事件的过去式，不必处处加"了"，靠时间状语（"当年""那一年"）体现时态
- 连词不必逐字译：and/but/so 在中文里常用意合（上下文衔接）而非显性连词

### 经典名句处理
巴菲特有许多已成中文定译的金句，遇到时用约定俗成译法，不要自行重译：
- "Be fearful when others are greedy, greedy when others are fearful" → 别人贪婪时我恐惧，别人恐惧时我贪婪
- "Price is what you pay. Value is what you get." → 价格是你支付的，价值是你得到的
- "Our favorite holding period is forever" → 我们最喜欢的持有期是永远
- "Time is the friend of the wonderful business" → 时间是好公司的朋友
- "Only when the tide goes out do you discover who's been swimming naked" → 只有退潮时才知道谁在裸泳
- 其他未列出的金句，按原意自然贴切地译，保留警句的力度

### 格式规则（极其重要）
- **占位符 __BLOCK_N__ 必须原样保留在原位置**，不要翻译、删除或移动。这些占位符代表原文中的代码块/表格，由程序自动恢复
- 原文中的所有数字、金额、百分比绝对不能改动，原样保留
- Markdown 标题（#、##、###）保留原有层级，不可随意升降级
- 脚注编号（(1)、(2) 等）保持对应
- 公司名称首次出现时保留英文原名并附中文译名，如：Berkshire Hathaway（伯克希尔·哈撒韦）
- 人名保留英文原文，如：Warren E. Buffett、Charlie Munger
- 日期格式转为中文：July 9, 1965 → 1965年7月9日
- 百分比原样不变：8.470% → 8.470%
- 点数原样不变：499点、下跌64点
- 金额转中文量级但保留美元：$4 billion → 40亿美元；$1 million → 100万美元；$500,000 → 50万美元

### 翻译策略
- 只输出翻译后的中文，不要添加任何额外说明、注释或元信息
- 不要遗漏任何内容
- 遇到不懂的金融术语，优先查上述术语表，无对应项时保持专业译法，不凭空猜测
- 如果原文有歧义，保持歧义，不要自行解释
- 术语表未覆盖的新术语，首次出现给"中文译名（English原文）"，后续统一用中文译名"""


# ═══════════════════════════════════════════════════════════════════════════════
# 翻译核心：程序管格式，LLM 只翻译纯文本
# ═══════════════════════════════════════════════════════════════════════════════

def _strip_outer_fence(content: str) -> tuple[str, bool]:
    """剥离外层 ``` 包裹，返回 (剥离后内容, 是否有外层围栏)

    只剥离"包裹整封信正文"的外层围栏。
    判断标准：第一个 ``` 的配对（第二个 ```）必须在文件末尾附近（后50行内），
    且两者之间包含 >50% 的行数。否则说明第一个 ``` 只是正文内的小代码块。
    """
    lines = content.splitlines()
    n = len(lines)
    if n < 20:
        return content, False

    # 找前10行内的第一个 ```
    start = None
    for i in range(min(10, n)):
        if lines[i].strip() == "```":
            start = i
            break
    if start is None:
        return content, False

    # 找第二个 ```（start 的配对）
    second = None
    for i in range(start + 1, n):
        if lines[i].strip() == "```":
            second = i
            break
    if second is None:
        return content, False

    # 第二个 ``` 必须在文件末尾附近（后50行内），才是外层围栏
    if second < n - 50:
        return content, False

    # 两者之间必须包含 >50% 的行数
    if second - start < n * 0.5:
        return content, False

    stripped = "\n".join(lines[:start] + lines[start + 1:second] + lines[second + 1:])
    return stripped, True


def _protect_blocks(content: str) -> tuple[str, list[str]]:
    """把 ```代码块``` 替换为占位符，保护 ASCII 表格不被 LLM 破坏

    HTML 表格（<table>）和 Markdown 表格不保护——它们的结构清晰，
    LLM 能正确处理，且程序保护反而增加复杂度。

    返回 (替换后内容, 原始块列表)
    """
    blocks: list[str] = []

    def replace(m):
        idx = len(blocks)
        blocks.append(m.group(0))
        return f"__BLOCK_{idx}__"

    protected = re.sub(r"```.*?```", replace, content, flags=re.DOTALL)
    return protected, blocks


def _restore_blocks(translated: str, blocks: list[str]) -> str:
    """恢复占位符为原始块，用正则容错 LLM 对占位符的轻微改写"""
    for i, block in enumerate(blocks):
        # 容错：LLM 可能加了空格、改了大小写、加了反引号等
        translated = re.sub(
            r"_{0,2}\s*BLOCK\s*" + str(i) + r"\s*_{0,2}",
            lambda _: block,
            translated,
            flags=re.IGNORECASE,
        )
    # 清理未被恢复的残留占位符（删除而非保留）
    translated = re.sub(r"__BLOCK_\d+__", "", translated)
    return translated


def _split_chunks(text: str, max_chars: int = 8000) -> list[str]:
    """将纯文本按段落边界分段，每段不超过 max_chars 字符"""
    if len(text) <= max_chars:
        return [text]

    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = current + "\n\n" + para if current else para
        else:
            if current:
                chunks.append(current)
            if len(para) > max_chars:
                # 单段超长，硬切
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i:i + max_chars])
                current = ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def _call_llm(text: str, cfg: LLMConfig, retries: int = 3) -> str:
    """流式调用 DeepSeek 翻译纯文本块"""
    user_prompt = (
        "请将以下文本翻译为中文。严格遵循系统提示中的术语表与格式规则，只输出译文。\n"
        "文中形如 __BLOCK_N__ 的标记是代码块/表格占位符，原样保留在原位置，不要翻译或删除。\n\n"
        f"---\n\n{text}"
    )

    timeout = httpx.Timeout(300.0, connect=30.0)

    for attempt in range(1, retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                with client.stream(
                    "POST",
                    f"{cfg.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {cfg.api_key}"},
                    json={
                        "model": cfg.model,
                        "messages": [
                            {"role": "system", "content": SYSTEM_PROMPT},
                            {"role": "user", "content": user_prompt},
                        ],
                        "max_tokens": 8192,
                        "temperature": 0.5,
                        "stream": True,
                    },
                ) as resp:
                    resp.raise_for_status()

                    chunks: list[str] = []
                    finish_reason = None
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        obj = json.loads(data)
                        delta = obj["choices"][0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            chunks.append(delta["content"])
                        if obj["choices"][0].get("finish_reason"):
                            finish_reason = obj["choices"][0]["finish_reason"]

                    raw = "".join(chunks)
                    if not raw.strip():
                        raise ValueError("API 返回空内容")
                    if finish_reason == "length":
                        raise ValueError("输出被 max_tokens 截断")
                    return raw.strip()

        except Exception as e:
            if attempt < retries:
                time.sleep(attempt * 3)
            else:
                raise


def translate_letter(content: str, cfg: LLMConfig, retries: int = 3) -> str:
    """翻译单封信：程序管格式，LLM 只翻译纯文本

    流程：剥离外层 ``` → 保护代码块/表格 → 分段 → 并发翻译 → 恢复 → 补回外层 ```
    """
    # 1. 剥离外层 ```（记下来最后补回）
    inner, has_fence = _strip_outer_fence(content)

    # 2. 保护 ``` 代码块和 <table> 表格
    protected, blocks = _protect_blocks(inner)

    # 3. 分段
    chunks = _split_chunks(protected, max_chars=4000)

    # 4. 并发翻译各段
    translated_chunks: list[str] = [""] * len(chunks)
    if chunks:
        with ThreadPoolExecutor(max_workers=min(5, len(chunks))) as pool:
            futures = {
                pool.submit(_call_llm, chunk, cfg, retries): i
                for i, chunk in enumerate(chunks)
            }
            for fut in as_completed(futures):
                idx = futures[fut]
                translated_chunks[idx] = fut.result()

    # 5. 拼接 + 恢复占位符
    translated = "\n".join(translated_chunks)
    translated = _restore_blocks(translated, blocks)

    # 6. 补回外层 ```
    if has_fence:
        translated = "```\n" + translated + "\n```"

    return translated


# ═══════════════════════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════════════════════

def _translate_one(md_path: Path, cfg: LLMConfig, index: int, total: int, lock: threading.Lock) -> tuple[str, str | None, str | None]:
    """翻译单封信，返回 (文件名, 译文或None, 错误或None)"""
    name = md_path.name
    out_path = OUT_DIR / name

    if out_path.exists():
        with lock:
            print(f"[skip {index}/{total}] {name} - exists")
        return name, None, None

    content = md_path.read_text(encoding="utf-8")
    size_kb = len(content.encode("utf-8")) / 1024
    with lock:
        print(f"[trans {index}/{total}] {name} ({size_kb:.0f} KB)...", flush=True)

    try:
        translated = translate_letter(content, cfg)
        out_path.write_text(translated, encoding="utf-8")
        zh_size = len(translated.encode("utf-8")) / 1024
        with lock:
            print(f"  [OK] {name} ({zh_size:.0f} KB)", flush=True)
        return name, translated, None
    except Exception as e:
        with lock:
            print(f"  [FAIL] {name}: {e}", flush=True)
        return name, None, str(e)


def translate_all(years: list[str] | None = None, dry_run: bool = False, workers: int = 5):
    """翻译巴菲特股东信

    Args:
        years: 要翻译的年份列表，None 表示全部
        dry_run: True 只打印计划，不实际翻译
        workers: 并发线程数，默认5
    """
    cfg = get_config()
    if not dry_run and not cfg.api_key:
        print("[ERROR] DEEPSEEK_API_KEY not configured", file=sys.stderr)
        print("  cp .env.example .env  then edit it", file=sys.stderr)
        sys.exit(1)

    if not LETTERS.exists():
        print(f"[ERROR] letters dir not found: {LETTERS}", file=sys.stderr)
        sys.exit(1)

    all_md = sorted(
        LETTERS.glob("*.md"),
        key=lambda x: (int(x.stem[:4]), x.stem),
    )

    if years:
        all_md = [f for f in all_md if f.stem[:4] in years]

    if not all_md:
        print("[info] no files to translate")
        return

    OUT_DIR.mkdir(exist_ok=True)

    print(f"model: {cfg.model}")
    print(f"src: {LETTERS}")
    print(f"out: {OUT_DIR}")
    print(f"todo: {len(all_md)} letters")
    print(f"workers: {workers}")
    print()

    if dry_run:
        for i, md_path in enumerate(all_md, 1):
            size_kb = len(md_path.read_text(encoding="utf-8").encode("utf-8")) / 1024
            print(f"[dry {i}/{len(all_md)}] {md_path.name} ({size_kb:.0f} KB)")
        return

    lock = threading.Lock()
    total = len(all_md)
    done = 0
    failed = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_translate_one, md, cfg, i, total, lock): md
            for i, md in enumerate(all_md, 1)
        }
        for fut in as_completed(futures):
            name, translated, error = fut.result()
            done += 1
            if error:
                failed.append(name)

    print(f"\n[done] {done}/{total} processed, saved to {OUT_DIR.resolve()}")
    if failed:
        print(f"[failed] {len(failed)}: {', '.join(failed)}")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="巴菲特股东信中译")
    ap.add_argument("--year", type=str, nargs="*", help="翻译指定年份，如 --year 1957 1958")
    ap.add_argument("--dry-run", action="store_true", help="仅列出待翻译文件，不调用 API")
    ap.add_argument("--workers", type=int, default=5, help="并发翻译线程数，默认5")
    args = ap.parse_args()
    translate_all(years=args.year or None, dry_run=args.dry_run, workers=args.workers)
