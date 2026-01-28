# AstrBot Odoo 连接器

连接 AstrBot 与 Odoo 18 Discuss 模块，实现企业内部 AI 机器人功能。

## 功能特性

- 在 Odoo Discuss 中与 AI 机器人对话
- 支持文本和图片消息
- 支持同步 API 调用（用于抖音私信等自动回复场景）
- 支持异步 Webhook 回调
- Markdown 自动转换为 HTML 显示
- 简单配置，开箱即用

## 架构

```
┌─────────────┐     Webhook      ┌─────────────┐
│   Odoo      │ ───────────────> │   AstrBot   │
│   Discuss   │                  │   Server    │
│             │ <─────────────── │             │
└─────────────┘     Callback     └─────────────┘
```

**两种调用模式：**

1. **异步模式**（Discuss 对话）：Odoo 发送消息到 AstrBot Webhook，AstrBot 处理后回调 Odoo
2. **同步模式**（自动回复）：Odoo 发送请求并等待 AstrBot 直接返回回复

## 快速开始

### 1. AstrBot 侧配置

1. 进入 AstrBot Dashboard → `平台管理` → `添加平台`
2. 选择 `Odoo 18` 适配器
3. 配置参数：

| 参数 | 说明 | 示例 |
|------|------|------|
| Odoo 回调地址 | Odoo 接收回复的地址 | `http://your-odoo:8069/astrbot/callback` |
| API Key | 认证密钥（可选） | `your-secret-key` |
| 机器人名称 | 在 Odoo 中显示的名称 | `AstrBot` |

4. 复制生成的 **Webhook URL**（格式：`http://astrbot:6185/api/platform/webhook/{uuid}`）

### 2. Odoo 侧安装

```bash
# 复制模块到 Odoo addons 目录
cp -r odoo_module/astrbot_connector /path/to/odoo/addons/

# 重启 Odoo 并更新应用列表
```

安装模块：设置 → 应用 → 搜索 "AstrBot" → 安装

### 3. Odoo 侧配置

1. 进入 `设置` → `常规设置` → `AstrBot`
2. 勾选 **Enable AstrBot**
3. 填写配置：

| 参数 | 说明 | 示例 |
|------|------|------|
| Webhook URL | AstrBot 生成的 Webhook 地址 | `http://localhost:6185/api/platform/webhook/{uuid}` |
| API Key | 认证密钥（与 AstrBot 端一致） | `your-secret-key` |
| Bot Name | 机器人显示名称 | `AstrBot` |

4. 点击保存

### 4. 测试连接

在设置页面提供了测试按钮：

- **Test Webhook**：测试 Webhook URL 是否可达
- **Test Sync API (Chat)**：打开弹窗发送自定义消息测试 AI 回复

### 5. 开始对话

**方法一：设置页面**
- 点击 `Open Chat with AstrBot` 按钮

**方法二：Discuss 菜单**
- 顶部菜单 Discuss → `Chat with AstrBot`

**方法三：手动搜索**
- 打开 Discuss → 新建对话 → 搜索 "AstrBot"

> **提示**: 首次使用请通过方法一或方法二，系统会自动创建机器人用户。

## 在其他模块中调用 AI

`astrbot_connector` 提供了 `astrbot.service` 服务，其他 Odoo 模块可以直接调用。

### 同步调用（推荐用于自动回复）

```python
def _handle_douyin_message(self, msg):
    """处理抖音私信 - 同步等待 AI 回复"""
    service = self.env['astrbot.service']
    
    reply = service.chat_sync(
        message=msg.content,
        session_id=f"douyin_{msg.sender_open_id}",  # 用于上下文记忆
        user_name=msg.sender_nickname,
        timeout=30,
    )
    
    if reply:
        self._send_douyin_reply(msg, reply)
```

### 异步调用（用于 Discuss 等场景）

```python
def _handle_message(self, msg):
    """异步发送消息 - 不等待回复"""
    service = self.env['astrbot.service']
    
    result = service.chat_async(
        message=msg.content,
        session_id=f"channel_{msg.channel_id}",
        user_id=str(msg.author_id.id),
        user_name=msg.author_id.name,
    )
    # result: {'request_id': 'xxx', 'status': 'pending'}
    # 回复会通过 /astrbot/callback 端点回调
```

## 配置参数详解

### AstrBot 侧

| 参数 | 说明 | 默认值 |
|------|------|--------|
| odoo_callback_url | Odoo 回调地址 | `http://localhost:8069/astrbot/callback` |
| odoo_api_key | API 密钥 | (空) |
| bot_name | 机器人名称 | AstrBot |

### Odoo 侧

| 参数 | 说明 | 默认值 |
|------|------|--------|
| astrbot_enabled | 启用开关 | False |
| astrbot_webhook_url | AstrBot Webhook URL | (空) |
| astrbot_api_key | API 密钥 | (空) |
| astrbot_bot_name | 机器人名称 | AstrBot |

## 通信协议

### Odoo → AstrBot（消息请求）

```json
{
  "type": "message",
  "message_id": "123",
  "content": "你好",
  "user_id": "1",
  "user_name": "张三",
  "session_id": "5",
  "message_type": "private",
  "timestamp": 1706400000,
  "api_key": "your_api_key"
}
```

### Odoo → AstrBot（同步调用）

```json
{
  "type": "sync_chat",
  "message": "你好",
  "session_id": "douyin_123",
  "user_name": "张三",
  "api_key": "your_api_key"
}
```

### AstrBot → Odoo（回调）

```json
{
  "session_id": "5",
  "content": [
    {"type": "text", "data": "你好！有什么可以帮助你的？"},
    {"type": "image", "data": "base64://..."}
  ],
  "reply_to": "123",
  "bot_name": "AstrBot",
  "timestamp": 1706400001
}
```

## HTTP 端点

### Odoo 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/astrbot/callback` | POST | 接收 AstrBot 回复 |
| `/astrbot/ping` | POST | 健康检查 |

### AstrBot 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/platform/webhook/{uuid}` | POST | 接收 Odoo 消息 |

## 故障排查

### 消息发送失败

1. 检查 Odoo 日志中的 `astrbot_connector` 相关错误
2. 确认 Webhook URL 配置正确
3. 确认 API Key 两端一致
4. 检查网络连通性

### 机器人无响应

1. 确认 AstrBot 服务正在运行（`uv run main.py`）
2. 使用 "Test Webhook" 测试连接
3. 检查 AstrBot 日志
4. 确认 Odoo 回调地址可从 AstrBot 服务器访问

### 同步 API 超时

1. 增加 `timeout` 参数值
2. 检查 AstrBot 的 LLM 提供商配置
3. 确认 LLM 服务正常响应

## 目录结构

```
astrbot_plugin_odoo/
├── main.py              # 插件入口
├── odoo_adapter.py      # 平台适配器
├── odoo_event.py        # 消息事件处理
├── metadata.yaml        # 插件元数据
├── requirements.txt     # Python 依赖
├── README.md            # 本文档
└── odoo_module/         # Odoo 模块
    └── astrbot_connector/
        ├── __manifest__.py
        ├── __init__.py
        ├── README.md        # Odoo 模块说明
        ├── models/          # 数据模型
        │   ├── res_config_settings.py  # 配置设置
        │   ├── discuss_channel.py      # Discuss 集成
        │   └── astrbot_service.py      # AI 服务 API
        ├── controllers/     # HTTP 控制器
        │   └── astrbot_connector.py    # 回调处理
        ├── wizard/          # 向导
        │   └── astrbot_test_wizard.py  # 测试向导
        ├── views/           # 视图
        ├── data/            # 初始数据
        └── security/        # 权限配置
```

## 安全建议

- 双向通信使用 API Key 验证
- 生产环境建议使用 HTTPS
- 定期更换 API Key
- 限制 Odoo 回调端点的访问来源

## 许可证

LGPL-3.0
