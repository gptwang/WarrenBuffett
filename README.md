# Warren Buffett Letters

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MinerU](https://img.shields.io/badge/MinerU-document%20extraction-orange)](https://mineru.net)

巴菲特致股东信（1977–2024），原始文件 + MinerU Markdown 转换。

## 项目简介

自动抓取 [Berkshire Hathaway 官网](https://www.berkshirehathaway.com/letters/letters.html) 历年股东信，保留原始文件（HTML/PDF），并通过 [MinerU](https://github.com/opendatalab/MinerU) 转换为高质量 Markdown。

- **1977–1997**：官网直接提供 HTML 版本
- **1998–2003**：导航页链接到 PDF（脚本自动识别并下载）
- **2004–2024**：官网直接提供 PDF 版本

## 前置要求

```bash
pip install requests
npm install -g mineru-open-api
```

[MinerU Token](https://mineru.net/apiManage/token)（注册即可免费获取，每日有配额）。

## 快速开始

```bash
cp .env.example .env
# 编辑 .env，填入 MINERU_TOKEN

python scrape_letters.py --year 1977        # 单年
python scrape_letters.py --year 1977-2024   # 全部
python scrape_letters.py --year 1998-2024 --force  # 强制重新抓取
```

## 模型选择

| 选项 | 命令 | 效果 | 适用 |
|------|------|------|------|
| **vlm**（默认） | 不加参数 | ⭐⭐⭐ 表格精度最高 | 有 PDF，需要表格准确 |
| pipeline | `--pipeline` | ⭐⭐ 中等 | vlm 配额不足时备用 |
| flash→vlm | `--flash` | ⭐⭐⭐ 小文件快 | ≤20 页的小文件提速 |

```bash
python scrape_letters.py --year 2004       # 默认 vlm，最佳表格解析
python scrape_letters.py --year 2004 --pipeline  # pipeline 模式，省配额
python scrape_letters.py --year 2004 --flash     # flash 优先，≤20页适用
```

## 输出结构

```
letters/
  1977.html        # 原始 HTML（1977–1997 官网版本）
  1977.md          # MinerU crawl → Markdown
  1998.pdf         # 原始 PDF（导航页自动下载）
  1998.md          # MinerU extract → Markdown（vlm）
  2004ltr.pdf      # 原始 PDF（2004+ 官网版本）
  2004.md          # MinerU extract → Markdown（vlm）
```

## 工作原理

1. 访问 /letters/letters.html 索引页
2. 对每年：
   - 1977–1997 → 下载 HTML → `mineru crawl`
   - 1998–2003 → 访问导航页 → 提取 PDF 链接 → 下载 → `mineru extract --model vlm`
   - 2004–2024 → 直接下载 `{year}ltr.pdf` → `mineru extract --model vlm`
3. 已存在的文件自动跳过，除非加 `--force`

## 相关项目

- [MinerU](https://github.com/opendatalab/MinerU) — 文档提取工具
- [Berkshire Hathaway](https://www.berkshirehathaway.com/letters/letters.html) — 股东信官方页面

## License

MIT — 详见 [LICENSE](LICENSE)。
