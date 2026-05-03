# 多模态微博金融舆情风险监测整合项目

这个目录把原来的多模态分析项目和微博实时爬虫项目合并到同一个 Flask 服务中。

## 功能

- 实时爬取微博搜索数据，保存到 MongoDB。
- 只保留同时具备正文和图片的微博；无正文、无图或图片下载失败的数据会直接丢弃。
- 下载微博配图。
- 每条新微博入库前自动调用多模态分析：正文文本、首张配图、OCR 文本、图文融合网络。
- 前端展示爬取状态、日志、微博正文、图片、风险等级、综合风险分和关键证据。
- 列表页提供关键结构化摘要，完整报告页提供与原多模态前端一致的完整分析内容。
- 支持对历史未分析微博补跑分析。
- 保留 `POST /analyze` 手动上传文本和图片的单条分析接口。

## 启动

```powershell
cd 整合
pip install -r requirements.txt
python backend\app.py
```

后端默认采用演示友好的非严格启动：先检查前端目录、爬虫目录，再尝试连接 MongoDB 和加载多模态模型组件。MongoDB 或深度学习依赖暂时不可用时，页面仍可启动，模型组件会显示为兜底运行；如需恢复严格检查，可设置 `STRICT_RUNTIME=1`。

然后访问：

```text
http://127.0.0.1:5000/
```

## 运行前检查

- MongoDB 需要在本机运行，默认连接 `mongodb://localhost:27017`。
- 爬虫配置在 `crawler/setting.py`，包括 Cookie、关键词、MongoDB 数据库和集合。
- 当前默认写入 `integrated_weibo.posts` 集合，和旧项目数据隔离。
- 爬虫图片保存在 `crawler/result/pic`，手动上传图片保存在 `backend/uploads`，OCR JSON 保存在 `json`。
- OCR 如需调用微信 OCR，需要配置环境变量 `WECHAT_OCR_EXE` 和 `WECHAT_DIR`。当前后端为严格启动模式，不配置或加载失败时后端不会启动。
- 微博 Cookie 失效时，爬虫日志会提示登录或请求失败，需要更新 `crawler/setting.py` 里的 cookie。

## 主要接口

- `GET /health`：模型与服务状态。
- `POST /api/crawl/start`：开始或继续爬取。
- `POST /api/crawl/pause`：暂停爬取。
- `GET /api/crawl/status`：爬取任务状态和日志。
- `GET /api/weibos`：读取微博与分析结果。
- `GET /api/weibos/<id>`：读取单条微博完整分析结果。
- `GET /report?id=<id>`：打开单条完整多模态分析报告。
- `POST /api/analyze/unprocessed?limit=20`：补分析历史未完成数据。
- `POST /analyze`：手动提交 `post_text` 和 `image` 进行单条分析。
