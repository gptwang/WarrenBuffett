# Warren Buffett Letters

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MinerU](https://img.shields.io/badge/MinerU-document%20extraction-orange)](https://mineru.net)

巴菲特致股东信（1957–2024）：原始文件 + 英文 Markdown + 中文译文。

## 项目简介

- **1957–1976**：合伙信 + 早期年度信，从 PDF 合集切分 → vlm 转换
- **1977–1997**：Berkshire 官网 HTML → crawl 转换
- **1998–2024**：Berkshire 官网 PDF → vlm 转换
- **1957–2024**：DeepSeek 翻译为中文（`letters_zh/`）

## 目录结构

```
letters/          # 英文 Markdown（83 封）
letters_raw/      # 原始文件 PDF/HTML（与 letters/ 同名）
letters_zh/       # 中文译文（与 letters/ 同名）
NAVIGATION.md     # 导航映射表（原始文件名 → 英文 → 中文 → 写信日期 → 性质）
translate.py      # 翻译引擎
scrape_letters.py # 从 Berkshire 官网抓取 1977–2024
split_letters.py  # 从 PDF 合集切分 1957–1976
fix_tables.py     # 修复 crawl 丢失的表格数据
```

## 文件命名规则

文件名 = 信件所报告/总结的年份（与 1977+ 年报逻辑统一）：

| 后缀 | 含义 |
|---|---|
| 无后缀 | 年度信/年报（主信，次年1-3月写） |
| `_h` | 半年报（7月写，总结上半年） |
| `_p` | 预备信/中期信（10-11月写，签协议或预告） |
| `_m` / `_m2` / `_m3` | 专题信（解散公告、债券教育等） |

详见 [NAVIGATION.md](NAVIGATION.md)。

## 翻译

```bash
pip install httpx
cp .env.example .env          # 编辑 .env，填入 DEEPSEEK_API_KEY
python translate.py           # 翻译全部（已存在跳过）
python translate.py --year 1957 1958   # 翻译指定年份
python translate.py --dry-run         # 预览（不调用 API）
python translate.py --workers 5       # 并发翻译（默认5）
```

翻译引擎特性：
- **流式翻译**（stream），避免长文本超时
- **分块翻译**：长信按 ~4000 字符分段，段落级并发
- **格式保护**：` ``` ` 代码块（含 ASCII 表格）用占位符保护，程序保证恢复
- **外层围栏**：HTML→MD 产生的 ` ``` ` 包裹由程序识别并保留
- **金融术语表**：70+ 术语统一译法，巴菲特投资哲学概念定译
- **temperature 0.5**：平衡术语一致性与语气还原

## 抓取与转换

```bash
# 前置要求
pip install requests
npm install -g mineru-open-api

# 抓取 1977–2024
python scrape_letters.py                     # 全部（已存在跳过）
python scrape_letters.py --year 1998         # 单年

# 切分 1957–1976
python split_letters.py                      # 切分 PDF → letters/{year}.pdf

# 修复 HTML 表格
python fix_tables.py --year 1977-1997        # 修复 crawl 丢失的表格数据
```

[MinerU Token](https://mineru.net/apiManage/token)（注册即可免费获取）。

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `translate.py` | DeepSeek 翻译英文→中文 |
| `scrape_letters.py` | 从 Berkshire 官网抓取 1977–2024 |
| `split_letters.py` | 从 PDF 合集切分 1957–1976 |
| `fix_tables.py` | 修复 crawl 丢失的表格数据 |

## 相关项目

- [MinerU](https://github.com/opendatalab/MinerU) — 文档提取工具
- [Berkshire Hathaway](https://www.berkshirehathaway.com/letters/letters.html) — 股东信官方页面
- [DeepSeek](https://platform.deepseek.com) — 翻译 LLM

## License

MIT — 详见 [LICENSE](LICENSE)。
