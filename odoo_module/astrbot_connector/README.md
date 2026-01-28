# AstrBot Connector for Odoo 18

将 AstrBot AI 助手集成到 Odoo Discuss 的连接器模块。

## 功能特性

- 在 Odoo Discuss 中与 AstrBot AI 对话
- 支持同步 API 调用（用于自动回复场景）
- 支持异步 Webhook 回调
- Markdown 内容自动转换为 HTML 显示
- 简洁的配置界面

## 安装

1. 将 `astrbot_connector` 文件夹复制到 Odoo addons 目录
2. 更新应用列表：设置 → 应用 → 更新应用列表
3. 搜索 "AstrBot" 并安装

## 配置

### 前置条件

确保 AstrBot 服务已运行，并已添加 Odoo 平台适配器：

1. 打开 AstrBot Dashboard
2. 进入 平台管理 → 添加平台
3. 选择 "Odoo" 适配器
4. 复制生成的 Webhook URL

### Odoo 端配置

1. 进入 设置 → 常规设置
2. 找到 "AstrBot" 配置区域
3. 勾选 "Enable AstrBot"
4. 填写配置：

| 配置项 | 说明 | 示例 |
|--------|------|------|
| Webhook URL | AstrBot 的 Webhook 地址 | `http://localhost:6185/api/platform/webhook/{uuid}` |
| API Key | 认证密钥（可选，需与 AstrBot 端一致） | `your-secret-key` |
| Bot Name | 机器人显示名称 | `AstrBot` |

5. 点击保存

## 使用方法

### 方法一：通过设置页面

1. 进入 设置 → 常规设置 → AstrBot
2. 点击 "Open Chat with AstrBot" 按钮

### 方法二：通过 Discuss 菜单

1. 点击顶部菜单 "Discuss"
2. 点击 "Chat with AstrBot"

### 方法三：直接搜索

1. 进入 Discuss
2. 点击 "开始对话" 或 "+"
3. 搜索 "AstrBot"

## 测试连接

在设置页面提供了两个测试按钮：

- **Test Webhook**: 测试 Webhook URL 是否可达
- **Test Sync API (Chat)**: 打开弹窗发送自定义消息测试 AI 回复

## API 调用

### 同步调用（推荐用于自动回复）

```python
# 在其他 Odoo 模块中调用
service = self.env['astrbot.service']
reply = service.chat_sync(
    message="用户的问题",
    session_id="unique_session_id",  # 用于上下文记忆
    user_name="用户名",
    timeout=60,
)
print(reply)  # AI 的回复文本
```

### 异步调用（用于 Discuss 集成）

```python
result = self.env['astrbot.service'].chat_async(
    message="用户的问题",
    session_id="session_id",
    user_id="user_id",
    user_name="用户名",
)
# result: {'request_id': 'xxx', 'status': 'pending'}
# 回复会通过 /astrbot/callback 端点回调
```

## 回调端点

模块提供以下 HTTP 端点：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/astrbot/callback` | POST | 接收 AstrBot 回复 |
| `/astrbot/ping` | POST | 健康检查 |

## 故障排查

### 机器人不回复

1. 检查 AstrBot 服务是否运行
2. 检查 Webhook URL 是否正确
3. 使用 "Test Webhook" 测试连接
4. 查看 Odoo 日志和 AstrBot 日志

### 消息格式问题

模块会自动将 AstrBot 返回的 Markdown 转换为 HTML。如果显示异常，检查 AstrBot 的回复格式。

### API Key 不匹配

确保 Odoo 端和 AstrBot 端配置的 API Key 完全一致。

## 技术细节

- 兼容 Odoo 18
- 使用 `discuss.channel` 的 `_message_post_after_hook` 拦截消息
- 支持私聊（DM）和群组对话
- 同步 API 使用 Webhook 的 `type=sync_chat` 模式

## 许可证

LGPL-3
