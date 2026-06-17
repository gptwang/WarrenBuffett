# Warren Buffett Letters

巴菲特致股东信（1977-2024），原始文件 + Markdown 格式。

## 抓取

```bash
pip install requests
npm install -g mineru-open-api

cp .env.example .env  # 填入 MINERU_TOKEN

python scrape_letters.py --year 1977        # 单年
python scrape_letters.py --year 1977-2024   # 全部
```

## 目录结构

```
letters/
  1977.html       # 原始 HTML（1977-2003）
  1977.md         # MinerU 转换 Markdown
  2004ltr.pdf     # 原始 PDF（2004-2024）
  2004.md         # MinerU 转换 Markdown
```
