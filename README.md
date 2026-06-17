# Warren Buffett Letters

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MinerU](https://img.shields.io/badge/MinerU-document%20extraction-orange)](https://mineru.net)

巴菲特致股东信（1957–2024），原始文件 + MinerU Markdown 转换。

## 项目简介

- **1957–1976**：合伙信 + 早期年度信，从 PDF 合集切分 → vlm 转换
- **1977–1997**：Berkshire 官网 HTML → crawl 转换
- **1998–2024**：Berkshire 官网 PDF → vlm 转换

所有表格数据已校验完整。原始文件（PDF/HTML）与 Markdown 并排存放。

## 前置要求

```bash
pip install requests
npm install -g mineru-open-api
```

[MinerU Token](https://mineru.net/apiManage/token)（注册即可免费获取）。

## 抓取 1977–2024

```bash
cp .env.example .env
# 编辑 .env，填入 MINERU_TOKEN

python scrape_letters.py                     # 抓取所有年份（已存在跳过）
python scrape_letters.py --year 1998         # 单年
python scrape_letters.py --year 1998-2024 --force  # 强制重新抓取
```

HTML 年份（1977–1997）用 `mineru crawl`，PDF 年份（1998–2024）用 `mineru extract --model vlm`。

## 切分 1957–1976

1957–1976 来自 PDF 合集，需先按年切分，再 vlm 转换：

```bash
python split_letters.py          # 切分 PDF → letters/{year}.pdf
python _vlm_batch.py             # vlm 转换 → letters/{year}.md（临时批量脚本）
```

## 修复 HTML 表格

MinerU `crawl` 有时丢失 `<PRE>` 块的年份标签。`fix_tables.py` 从原始 HTML 直接复制修复：

```bash
python fix_tables.py --year 1977-1997      # 修复所有 HTML 年份
python fix_tables.py --year 1977-1997 --dry-run  # 先预览
```

## 输出结构

```
letters/
  1957.pdf         # 1957–1976：原始 PDF + vlm Markdown
  1957.md
  1977.html        # 1977–1997：原始 HTML + crawl Markdown
  1977.md
  1998.pdf         # 1998–2003：导航页 PDF + vlm Markdown
  1998.md
  2004ltr.pdf      # 2004–2024：直接 PDF + vlm Markdown
  2004.md
```

## 脚本说明

| 脚本 | 用途 |
|------|------|
| `scrape_letters.py` | 从 Berkshire 官网抓取 1977–2024 |
| `split_letters.py` | 从 PDF 合集切分 1957–1976 |
| `fix_tables.py` | 修复 crawl 丢失的表格数据 |
| `_vlm_batch.py` | 临时：批量 vlm 转换切分后的 PDF |

## 相关项目

- [MinerU](https://github.com/opendatalab/MinerU) — 文档提取工具
- [Berkshire Hathaway](https://www.berkshirehathaway.com/letters/letters.html) — 股东信官方页面

## License

MIT — 详见 [LICENSE](LICENSE)。
