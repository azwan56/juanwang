# YuePaoQuan Coach

YuePaoQuan 自动跑步教练机器人，集成 WeCom 自动化反馈流程。

## 项目结构
- `agent/yuepaoquan_service/`: 核心业务逻辑与数据处理服务
- `gateway/`: 各类平台（WeCom/Discord/等）适配器与回调处理
- `yuepaoquan_design/`: 系统架构设计文档与实现方案

## 功能特性
- OCR 运动数据自动提取
- 自动化运动反馈推送
- 多平台集成支持

## 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 运行服务
python run_agent.py
```
