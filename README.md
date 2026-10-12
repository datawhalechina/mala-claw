# MalaClaw

<div align="center">

![MalaClaw Logo](logo.svg)

# MalaClaw

> **名字来源**：MalaClaw = Mala（麻辣）+ Claw（龙虾），灵感来自"麻辣小龙虾"  
> **定位**：用于演示的轻量级 AI Agent 平台  
> **口号**："麻辣麻辣，AI 到家！"  
> **许可证**：MIT License
>
> 这可能是漏洞最多的小龙虾项目，也可能是最简单的小龙虾项目，目标是快速理解小龙虾场景、快速掌握各模块原理和逻辑。

</div>

---

## 🚀 快速开始

**3 分钟快速上手**：查看 [QUICKSTART.md](QUICKSTART.md)

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 准备配置文件
cp config.example.json config.json

# 3. 启动应用
python app.py

# 4. 访问页面
# http://localhost:5000
```

---

## 📦 完整安装步骤

### 1. 安装 Python 依赖

```bash
cd MalaClaw
pip install -r requirements.txt
```

### 2. 安装 Playwright 浏览器

```bash
playwright install chromium
```

### 3. 启动应用

```bash
python app.py
```

启动成功后，访问：**http://localhost:5000**

---

## 🎯 功能说明

### 智能助手（Agents）

系统预置了 3 个助手：

- **内容助手**：负责内容创作，支持打招呼、网页截图
- **数据助手**：负责数据分析，支持打招呼、API 调用
- **客服助手**：负责客户服务，支持打招呼

### 可用技能（Skills）

#### 1. hello - 打招呼
```json
{
  "message": "你好"
}
```

#### 2. screenshot - 网页截图
```json
{
  "url": "https://www.baidu.com"
}
```

#### 3. api_call - API 调用
```json
{
  "method": "GET",
  "url": "https://api.github.com/events",
  "data": null
}
```

#### 4. bailian_llm - 百炼大模型对话 ⭐
```json
{
  "prompt": "请解释什么是人工智能",
  "model": "qwen-plus",
  "system_message": "你是一个专业的 AI 助手"
}
```

**支持的模型**：
- `qwen-turbo` - 快速响应
- `qwen-plus` - 平衡性能和成本（推荐）
- `qwen-max` - 最强能力

#### 5. content_generation - 内容生成 ⭐
```json
{
  "topic": "AI 技术的发展趋势",
  "content_type": "article",
  "length": "medium"
}
```

**content_type 可选值**：
- `article` - 文章
- `report` - 报告
- `email` - 邮件
- `summary` - 总结

**length 可选值**：
- `short` - 300 字以内
- `medium` - 800-1000 字
- `long` - 1500 字以上

#### 6. data_analysis - 数据分析 ⭐
```json
{
  "data_description": "某产品 Q1 销售额 100 万，Q2 销售额 150 万，Q3 销售额 180 万",
  "analysis_type": "insight"
}
```

**analysis_type 可选值**：
- `insight` - 数据洞察
- `trend` - 趋势分析
- `comparison` - 对比分析
- `recommendation` - 建议方案

#### 7. feishu_message - 飞书消息 ⭐⭐⭐
```json
{
  "content": "大家早上好！今天是周一，记得参加晨会哦",
  "receiver_type": "group",
  "receiver_id": "oc_123456"
}
```

**配置方法**：
在 `app.py` 中设置 `FEISHU_WEBHOOK`（ webhook 方式）或`FEISHU_APP_ID/SECRET`（API 方式）

#### 8. email_send - 邮件发送 ⭐⭐⭐
```json
{
  "to_address": "customer@example.com",
  "subject": "月度销售报告",
  "content": "尊敬的客户，附件是您的月度报告...",
  "is_html": false
}
```

**配置方法**：
在 `app.py` 中设置 `EMAIL_CONFIG` 的 SMTP 信息

#### 9. excel_process - Excel 处理 ⭐⭐⭐
```json
{
  "file_path": "data/sales.xlsx",
  "operation": "summary",
  "sheet_name": 0
}
```

**operation 可选值**：
- `read` - 读取数据（返回前 100 行）
- `summary` - 统计摘要（均值、最大值等）
- `filter` - 筛选数据

#### 10. agent_collaboration - 多 Agent 协作 ⭐⭐⭐⭐⭐
```json
{
  "workflow": "data_to_report",
  "params": {
    "data_description": "Q1 销售额 100 万，Q2 150 万",
    "topic": "季度销售分析报告",
    "send_method": "feishu",
    "email_address": "boss@company.com",
    "email_subject": "Q2 销售报告"
  }
}
```

**工作流说明**：
1. 数据助手分析数据
2. 内容助手生成报告
3. 客服助手发送报告（飞书或邮件）

**支持的工作流**：
- `data_to_report` - 数据分析→报告生成→发送

---

## ⏰ 定时任务示例

### Cron 表达式示例

| 表达式 | 含义 |
|--------|------|
| `0 9 * * 1-5` | 工作日早上 9 点 |
| `0 */2 * * *` | 每 2 小时 |
| `0 8 * * *` | 每天早上 8 点 |
| `0 0 * * 0` | 每周日凌晨 0 点 |
| `*/5 * * * *` | 每 5 分钟 |

### 创建任务示例

**任务 ID**: `morning_hello`  
**任务名称**: 每日晨报问候  
**选择助手**: 内容助手  
**执行技能**: hello  
**Cron 表达式**: `0 9 * * 1-5`  
**技能参数**: `{"message": "大家早上好！新的一天开始了！"}`

---

## 🎨 界面特点

- ✅ **浅色背景**：简洁清爽的视觉体验
- ✅ **实时状态**：每 5 秒刷新助手状态
- ✅ **任务监控**：定时任务执行情况一目了然
- ✅ **日志追踪**：所有执行记录可追溯
- ✅ **10 个核心技能**：覆盖 LLM、飞书、邮件、Excel、多 Agent 协作

---

## 🚀 Workshop 演示场景推荐

### 场景 1：每日晨报自动化（飞书集成）
**演示流程**：
1. 配置定时任务：工作日早上 8:30
2. 选择"客服助手" + "feishu_message"
3. 设置消息内容："大家早上好！..."
4. 第二天展示飞书收到的消息

**效果**：让客户直观看到 AI Agent 的自主沟通能力

### 场景 2：销售数据分析报告（Excel + 大模型）
**演示流程**：
1. 准备一个 Excel 销售数据表
2. 使用"数据助手" + "excel_process"读取数据
3. 使用"数据助手" + "data_analysis"分析趋势
4. 使用"内容助手" + "content_generation"生成报告
5. 使用"客服助手" + "email_send"发送给老板

**效果**：展示完整的数据处理→分析→报告→发送闭环

### 场景 3：多 Agent 协作（核心卖点）⭐⭐⭐
**演示流程**：
1. 选择"协调员" + "agent_collaboration"
2. 设置工作流："data_to_report"
3. 提供销售数据描述
4. 一键执行，观察三个 Agent 协同工作

**效果**：展示"AI 团队"的概念，一个指令，多个 AI 分工完成

### 场景 4：网页截图 + 分析报告
**演示流程**：
1. 使用"内容助手" + "screenshot"截取竞品网站
2. 使用"数据助手" + "bailian_llm"分析页面内容
3. 生成竞争分析报告

**效果**：展示浏览器自动化 + 大模型的组合能力

## 🛠️ 自定义扩展

### 添加新技能

在 `app.py` 中的 `available_skills` 字典后添加：

```python
class MyCustomSkill(Skill):
    name = "my_skill"
    description = "我的自定义技能"
    
    async def execute(self, param1="", param2=""):
        # 你的逻辑
        return {"status": "success", "result": "..."}

# 注册技能
available_skills["my_skill"] = MyCustomSkill()
```

### 添加新助手

在 `agents` 字典初始化后添加：

```python
agents["custom_agent"] = Agent("自定义助手", "自定义角色", ["skill1", "skill2"])
```

---

## 📝 使用场景

### 1. AI 咨询演示
- 展示 AI Agent 的基本概念
- 演示定时任务和自主执行能力
- 对比不同助手的分工协作

### 2. Workshop 实操
- 学员亲手创建定时任务
- 测试不同技能的执行效果
- 观察多助手协同工作

### 3. 培训教学
- 讲解 AI Agent 架构设计
- 演示 Skill 系统的扩展性
- 实践 Cron 表达式配置

---

## ⚠️ 注意事项

1. **首次运行需要下载浏览器**（约 100MB），请确保网络畅通
2. **截图保存在 `screenshots/` 目录**，定期清理
3. **日志默认保留最近 50 条**，避免内存占用过大
4. **开发模式运行**，生产环境请使用 Gunicorn 等 WSGI 服务器
5. **飞书配置**：需要在 app.py 中配置 webhook 或 API 信息
6. **邮件配置**：需要 SMTP 服务器信息（推荐使用企业邮箱）
7. **Excel 文件**：确保文件路径正确，支持.xlsx 格式

---

## 🔧 配置说明

### 飞书配置（二选一）

#### 方式 1：Webhook（简单，推荐）
```python
# 在 app.py 中设置
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
```

获取方法：飞书群 → 群机器人 → 添加自定义机器人 → 获取 Webhook 地址

#### 方式 2：完整 API（功能更强）
```python
FEISHU_APP_ID = "cli_xxxxxxxxxxxxx"
FEISHU_APP_SECRET = "xxxxxxxxxxxxx"
```

获取方法：飞书开放平台 → 创建企业自建应用

### 邮件配置
```python
EMAIL_CONFIG = {
    "smtp_server": "smtp.qq.com",  # QQ 邮箱示例
    "smtp_port": 465,
    "username": "your_email@qq.com",
    "password": "your_auth_code"  # 授权码，不是密码
}
```

常用 SMTP 配置：
- QQ 邮箱：`smtp.qq.com:465`
- 163 邮箱：`smtp.163.com:465`
- 企业邮箱：咨询公司 IT 部门

---

## 📊 与 OpenClaw 对比

| 功能 | OpenClaw | MalaClaw | 说明 |
|------|----------|----------|------|
| 大模型调用 | ✅ | ✅ | 百炼平台 |
| 定时任务 | ✅ | ✅ | APScheduler |
| 多 Agent | ✅ | ✅ | 4 个角色 |
| 浏览器自动化 | ✅ | ✅ | Playwright |
| 飞书集成 | ✅ | ✅ | Webhook/API |
| 邮件发送 | ✅ | ✅ | SMTP |
| Excel 处理 | ✅ | ✅ | Pandas |
| 技能数量 | 3500+ | 10 个 | 核心技能 |
| 学习成本 | 高 | 低 | MalaClaw 更简单 |
| 适用场景 | 生产环境 | Workshop/培训 | 定位不同 |

**MalaClaw 的优势**：
- ✅ 更简单，适合快速演示
- ✅ 模块化设计，易于扩展
- ✅ 中文友好，文档完善
- ✅ 专为 Workshop 优化

---

## 🎯 后续扩展计划

**已实现**：
- ✅ 飞书消息收发
- ✅ 邮件发送
- ✅ Excel 数据处理
- ✅ 多 Agent 协作

**计划中**：
- 🔄 数据库操作（MySQL/PostgreSQL）
- 🔄 更多文件格式（PDF、Word）
- 🔄 文件上传下载
- 🔄 语音消息处理
- 🔄 日历管理
- 🔄 待办事项管理

## 🐛 常见问题

### Q: 端口被占用怎么办？
修改 `app.py` 最后一行：
```python
app.run(host='0.0.0.0', port=5001, debug=True)  # 改为 5001 端口
```

### Q: 如何查看详细日志？
应用日志会输出到控制台，Web 日志通过界面查看

### Q: 如何停止应用？
按 `Ctrl+C` 终止 Flask 进程

---

## 🧪 定时任务回归测试

安装 `requirements.txt` 后，在项目根目录运行：

```bash
python -m unittest discover -s tests -p test_scheduled_agents.py -v
```

测试使用真实的 Flask 路由、后台调度器和本地 HTTP 服务，不需要模型密钥或第三方服务。任务列表中的“已启用”表示任务未暂停且已安排下次触发，不表示技能正在执行。

---

## 📞 技术支持

如有问题，请查看：
- Flask 文档：https://flask.palletsprojects.com/
- APScheduler 文档：https://apscheduler.readthedocs.io/
- Playwright 文档：https://playwright.dev/python/

---

**版本**: v1.0  
**更新日期**: 2026 年 3 月 16 日
