# 利率互换(IRS)计算器

银行间利率互换单笔合约计算器:FastAPI + 纯 Python 定价内核 + Vue3/Element Plus 前端,无数据库,行情数据来自本地 CSV。

## 环境要求

- Python 3.12(虚拟环境一律用 `D:/Python312` 创建)
- Node.js(仅前端构建用)

## 安装与启动

```bash
# 1) 后端虚拟环境
D:/Python312/python.exe -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt

# 2) 先构建前端(后端启动时才挂载 frontend/dist,顺序反了页面会 404)
cd frontend && npm install && npm run build

# 3) 启动后端
cd ../backend && ./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000
```

浏览器打开 http://127.0.0.1:8000。

## 开发模式

后端 uvicorn(8000)照常启动,前端另开 `cd frontend && npm run dev`(5173,已配置 /api 代理到 8000)。

## 测试

```bash
cd backend && ./.venv/Scripts/python.exe -m pytest
```

## 数据依赖

运行与测试需要 `data/` 目录下两个 CSV 就位(data/ 不入库属有意决策):

- `rate_value.csv`:估值曲线(按基准/日期的期限点零息利率)
- `rate_info.csv`:期限与定盘信息

`FR007ON行情.csv`、`SHIBOR3M定盘行情.csv` 当前 loader 不读取。
