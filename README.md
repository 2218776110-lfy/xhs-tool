# 🎬 视频文案提取工具

> 自媒体博主效率工具 · 一键提取视频逐字稿 · 由小羊老师独立开发

**在线体验** → [xhs-tool.up.railway.app](https://xhs-tool.up.railway.app)

---

## ✨ 功能介绍

| 功能 | 说明 |
|------|------|
| 🔗 链接提取 | 支持小红书、抖音、B站、YouTube 等主流平台 |
| 📦 批量提取 | 一次粘贴多个链接，并行处理，批量导出 Word |
| 💬 高赞评论 | 提取视频高赞评论，按热度排序 |
| ✨ AI 纠错 | 自动修正语音识别中的同音错别字 |
| 📄 导出 Word | 标题与正文自动匹配，格式规范 |
| 📱 多端可用 | 手机、iPad、电脑浏览器均可使用 |

---

## 🛠 技术栈

- **后端**：Python · Flask · Gunicorn
- **语音识别**：SiliconFlow API（FunAudioLLM/SenseVoiceSmall）
- **AI 纠错**：SiliconFlow API（Qwen2.5-72B-Instruct）
- **视频下载**：yt-dlp · ffmpeg
- **部署**：Railway · Docker

---

## 🚀 本地运行

```bash
# 克隆项目
git clone https://github.com/2218776110-lfy/xhs-tool.git
cd xhs-tool

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
export SILICONFLOW_API_KEY=你的密钥

# 启动
python app.py
```

访问 `http://localhost:5000`

> **依赖**：需要本地安装 [ffmpeg](https://ffmpeg.org) 和 [yt-dlp](https://github.com/yt-dlp/yt-dlp)

---

## 📁 项目结构

```
xhs-tool/
├── app.py          # Flask 主程序，路由定义
├── video.py        # 视频下载 + 语音识别
├── analyzer.py     # AI 纠错（SiliconFlow LLM）
├── scraper.py      # 小红书内容抓取
├── templates/
│   ├── landing.html  # 产品落地页
│   └── index.html    # 工具主页面
├── Dockerfile
└── requirements.txt
```

---

## 🌐 部署到 Railway

1. Fork 本仓库
2. 在 [Railway](https://railway.app) 创建项目，连接 GitHub 仓库
3. 添加环境变量 `SILICONFLOW_API_KEY`
4. 自动部署完成

---

## 👤 作者

**小羊老师** · 独立开发者

---

*Built with ❤️ · Powered by SiliconFlow AI*
