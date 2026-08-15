# Pi² 在线 Demo（Streamlit）

单文件包住 `AgentHarness`，用于快速公开演示（Hugging Face Spaces 免费托管）。

## 本地运行

```bash
pip install -r demo/requirements.txt   # 本地开发可直接在仓库根 pip install -e .
streamlit run demo/app.py
```

## 部署到 Hugging Face Spaces（约 2 分钟）

1. 打开 https://huggingface.co/new-space → 名称如 `pi2-demo` → SDK 选 **Streamlit** → Public
2. 上传本目录三个文件（`app.py`、`requirements.txt`、`README.md`）到 Space 仓库根目录
3. （可选）Space → Settings → Variables and secrets → 添加 `DEEPSEEK_API_KEY`，即可用真实模型；不配则用 faux 离线演示
4. 访问 `https://<你的用户名>-pi2-demo.hf.space`

> Demo 跑在 Spaces 的临时容器沙箱里，默认无需任何 key（faux provider 脚本化演示工具调用链）。
