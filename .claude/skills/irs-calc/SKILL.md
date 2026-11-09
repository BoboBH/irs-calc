---
name: irs-calc
description: 调用本地利率互换(IRS)计算器服务:估值(NPV/DV01/现金流)、Campisi 归因(theta/carry/roll/curve/spread)、平价利率、FR007/Shibor 3M 行情曲线与定盘查询。当用户要求 IRS 估值、Campisi 归因分析、平价利率、DV01 或查询行情曲线/定盘时使用。需本机服务已启动(http://127.0.0.1:8000)。
---

本技能的正身已移至仓库独立目录(便于 git 管理与复用):**`skills/irs-calc/SKILL.md`**。

先 Read 该文件获取完整调用指南(健康检查、单位口径、4 端点 curl 模板、错误处理),然后严格按其执行。本文件仅为自动发现入口,勿在此维护内容。
