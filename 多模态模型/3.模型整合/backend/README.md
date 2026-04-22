# 多模态网络金融舆情风险监测系统后端

## 启动

```powershell
$env:MODEL_SERVICE_KEY="你的模型服务密钥"
python backend/app.py
```

启动后访问：

```text
http://127.0.0.1:5000/
```

## 接口

- `GET /health`：服务状态检查
- `POST /analyze`：提交微博正文和配图进行多模态风险监测

表单字段：

- `post_text`：微博正文
- `image`：微博配图
