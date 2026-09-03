# 基于 Scrapy 的起点网站免费小说大规模文本采集
基于 Scrapy 搭建三级异步采集链路，覆盖起点免费榜全站 50 页约 1000 部作品，Pipeline 按"书名文件夹 + 章节 txt"结构化落盘，已归档 3500+ 章节 针对站点 JS 挑战型 WAF，设计"拦截检测 + Selenium 自动续命"方案：中间件识别三种拦截形态后驱动浏览器完成挑战并换发 Cookie，7~30 秒自愈，实现无人值守爬取 修复 Scrapy Cookie 因缺少 domain 被静默丢弃的缺陷；将阻塞调用投入线程池避免阻塞事件循环；设计三级降级策略与断点续爬，保障长时运行稳定
使用方法：
(1)需要自己下载edge浏览器对应的edgedriver,替换cookie_refresher.py里面的edgedriver路径
下载地址为：https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/?form=MA13LH&cs=3114783079
(2)运行runner.py即可启动项目，设置了请求队列，如果爬取时间过长可以随时暂停，下次启动会接着爬取数据，不用担心一旦停止项目会重置爬取进度



## 环境要求
- Python 3.9+
- Chrome 或 Edge（用于自动刷新 cookie）
- Windows（路径与文件名清洗逻辑按 Windows 规则实现）

## 安装
```bash
pip install -r requirements.txt
```
## 使用
```bash
# 全量爬取（50 页），支持 Ctrl+C 中断后原命令续跑
scrapy crawl xiaoshuos -s JOBDIR=crawls/qidian-1
# 小规模试水
scrapy crawl xiaoshuos -s MAX_PAGE=3
# 手动刷新 cookie（一般不需要，被拦截时爬虫会自动处理）
python refresh_cookie.py --check
```

## 输出结构

```
books/
└── 书名/
    ├── 第一章.txt
    └── 第二章.txt
```

## 主要配置（qidian2/settings.py）

| 配置 | 默认 | 说明 |
|---|---|---|
| `MAX_PAGE` | 50 | 列表页抓取页数 |
| `BOOKS_STORE` | books | 输出目录 |
| `COOKIE_AUTO_REFRESH` | True | 被拦截时自动换 cookie |
| `COOKIE_MAX_REFRESH` | 10 | 单次运行最多刷新几次 |
| `COOKIE_BROWSER` | auto | chrome / edge / auto |
