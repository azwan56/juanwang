# 腾讯云函数 (SCF) 部署指南

## 概述

将 `scf_callback/` 目录部署为腾讯云函数（香港地域），获取自动分配的 HTTPS URL，
填入企业微信「秘书Jack」的回调配置中，**无需 ICP 备案**。

---

## 第一步：准备部署包

在本地打包代码和依赖：

```bash
cd /Users/azwan/Projects/juanwang/scf_callback

# 安装依赖到当前目录
pip install -t . cryptography

# 打包为 zip
zip -r ../scf_callback.zip . -x "*.pyc" "__pycache__/*" ".env*"
```

---

## 第二步：创建腾讯云函数

1. 登录 [腾讯云函数控制台](https://console.cloud.tencent.com/scf)
2. **重要**：左上角地域选择 **「亚太地区 → 中国香港」**
3. 点击「新建」

### 基础配置
| 配置项 | 值 |
|---|---|
| 函数类型 | 事件函数 |
| 函数名称 | `wecom-callback` |
| 运行环境 | Python 3.9 |
| 提交方法 | 本地上传 zip 包 |
| 执行方法 | `index.main_handler` |

### 上传代码
- 选择刚才打包的 `scf_callback.zip`

### 环境变量
在「环境变量」中添加以下键值对：

| Key | Value |
|---|---|
| `WECOM_CORP_ID` | 你的企业ID（管理后台「我的企业」底部） |
| `WECOM_TOKEN` | `tCUTt6eGvU2g1jyfANmelcafsry` |
| `WECOM_ENCODING_AES_KEY` | `DT69uLANA5eed9ZY3fal3zeTjpZaLWLp75IyOAQ5IMc` |
| `WECOM_AGENT_ID` | `1000002` |
| `WECOM_CORP_SECRET` | 秘书Jack 的 Secret（点「查看」获取） |
| `WECOM_WEBHOOK_URL` | 群机器人的新 Webhook URL |

### 高级配置
| 配置项 | 值 |
|---|---|
| 执行超时时间 | 10 秒 |
| 内存 | 128 MB（足够） |

---

## 第三步：创建 API 网关触发器

1. 在函数详情页 → 「触发管理」→ 「创建触发器」
2. 配置如下：

| 配置项 | 值 |
|---|---|
| 触发方式 | API 网关触发 |
| API 服务 | 新建 |
| 请求方法 | ANY |
| 发布环境 | 发布 |
| 鉴权方法 | 免鉴权 |

3. 创建完成后，你会获得一个类似这样的 URL：
```
https://service-xxxxxxxx-xxxxxxxxxx.hk.apigw.tencentcs.com/release/wecom-callback
```

---

## 第四步：配置企业微信回调

1. 回到 [企业微信管理后台](https://work.weixin.qq.com/wework_admin/frame)
2. 进入「秘书Jack」→ 「API接收消息」
3. 填入：
   - **URL**: 上一步获取的 API 网关 URL
   - **Token**: `tCUTt6eGvU2g1jyfANmelcafsry`
   - **EncodingAESKey**: `DT69uLANA5eed9ZY3fal3zeTjpZaLWLp75IyOAQ5IMc`
4. 勾选「用户发送的普通消息」
5. 点击「保存」

**如果保存成功，说明验证通过，整条链路已打通！** 🎉

---

## 第五步：测试

在企业微信中找到「秘书Jack」应用，发送一条消息，例如：
```
今天跑了10公里
```

如果一切正常，群机器人会自动回复反馈。

---

## 故障排查

### 保存时提示 URL 验证失败
1. 检查云函数日志（控制台 → 函数 → 日志查询）
2. 确认环境变量 `WECOM_CORP_ID` 是否正确
3. 确认 Token 和 EncodingAESKey 与配置页面一致

### 收到消息但没有回复
1. 检查 `WECOM_WEBHOOK_URL` 是否为新生成的有效 URL
2. 查看云函数日志中的 `[Webhook]` 相关输出

### 域名备案问题
- 如果 `*.apigw.tencentcs.com` 仍被拒绝，尝试使用 API 网关的「函数 URL」功能
- 函数详情 → 「函数 URL」→ 启用，获取 `*.scf.tencentcs.com` 格式的 URL
