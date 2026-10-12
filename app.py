"""
MalaClaw - AI Agent 平台（精简版）
用于 AI 咨询、Workshop、培训演示
"""

from flask import Flask, render_template, request, jsonify, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from playwright.async_api import async_playwright
import httpx
import asyncio
import logging
from datetime import datetime
import json
import os
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 全局变量存储任务和日志
jobs = {}
execution_logs = []
agents = {}

# 配置文件路径
CONFIG_FILE = "config.json"

# 默认配置
default_config = {
    # 百炼平台配置
    "bailian": {
        "api_key": "",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"
    },
    # 飞书配置
    "feishu": {
        "webhook": "",
        "app_id": "",
        "app_secret": "",
        "app_name": "MalaClaw",
        "encrypt_key": "",
        "verification_token": ""
    },
    # 邮件配置
    "email": {
        "smtp_server": "",
        "smtp_port": 465,
        "username": "",
        "password": ""
    },
    # Qoder CLI 云端配置
    "qoder_cli": {
        "base_url": "",
        "api_key": "",
        "enabled": False
    }
}

# 加载配置
def load_config():
    """从配置文件加载配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
                # 合并默认配置和加载的配置
                config = default_config.copy()
                for key in config:
                    if key in loaded:
                        config[key].update(loaded[key])
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
    return default_config.copy()

# 保存配置
def save_config(config):
    """保存配置到文件"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}")
        return False

# 初始化配置
config = load_config()

# 百炼平台配置
BAILIAN_API_KEY = config["bailian"]["api_key"]
BAILIAN_BASE_URL = config["bailian"]["base_url"]

# 飞书配置
FEISHU_WEBHOOK = config["feishu"]["webhook"]
FEISHU_APP_ID = config["feishu"]["app_id"]
FEISHU_APP_SECRET = config["feishu"]["app_secret"]
FEISHU_TOKEN_CACHE = {}  # 用于缓存 access_token

# 邮件配置
EMAIL_CONFIG = config["email"].copy()

# Qoder CLI 云端配置
QODER_CLI_CONFIG = config["qoder_cli"].copy()

# TODO List 存储（内存存储，重启后重置）
todo_list = []
todo_last_sync = None

# 初始化调度器
scheduler = BackgroundScheduler()


# ==================== 动态配置更新函数 ====================

def reload_feishu_config():
    """重新加载飞书配置（在保存配置后调用）"""
    global FEISHU_WEBHOOK, FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_TOKEN_CACHE
    
    loaded_config = load_config()
    FEISHU_WEBHOOK = loaded_config["feishu"]["webhook"]
    FEISHU_APP_ID = loaded_config["feishu"]["app_id"]
    FEISHU_APP_SECRET = loaded_config["feishu"]["app_secret"]
    FEISHU_TOKEN_CACHE = {}  # 清空 token 缓存
    logger.info("飞书配置已重新加载")


# ==================== Skill 定义 ====================

class Skill:
    """Skill 基类"""
    name = "base_skill"
    description = "基础技能"
    
    async def execute(self, **kwargs):
        raise NotImplementedError


class HelloSkill(Skill):
    """打招呼技能示例"""
    name = "hello"
    description = "发送问候消息"
    
    async def execute(self, message="你好"):
        logger.info(f"执行打招呼技能：{message}")
        return {
            "status": "success",
            "message": message,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }


class ScreenshotSkill(Skill):
    """网页截图技能"""
    name = "screenshot"
    description = "网页截图"
    
    async def execute(self, url="https://www.baidu.com"):
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.goto(url)
                
                # 保存截图
                filename = f"screenshots/{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
                os.makedirs("screenshots", exist_ok=True)
                await page.screenshot(path=filename)
                
                await browser.close()
                
                return {
                    "status": "success",
                    "screenshot": filename,
                    "url": url
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


class APICallSkill(Skill):
    """API 调用技能"""
    name = "api_call"
    description = "调用 REST API"
    
    async def execute(self, method="GET", url="", data=None):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    response = await client.get(url)
                elif method == "POST":
                    response = await client.post(url, json=data)
                else:
                    return {"status": "error", "error": "不支持的方法"}
                
                return {
                    "status": "success",
                    "status_code": response.status_code,
                    "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e)
            }


class BailianLLMSkill(Skill):
    """百炼平台大模型调用技能"""
    name = "bailian_llm"
    description = "调用百炼平台大模型进行对话"
    
    async def execute(self, prompt="", model="qwen-plus", system_message="你是一个有帮助的 AI 助手"):
        try:
            headers = {
                "Authorization": f"Bearer {BAILIAN_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 1024
            }
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{BAILIAN_BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    result = response.json()
                    content = result["choices"][0]["message"]["content"]
                    return {
                        "status": "success",
                        "content": content,
                        "model": model,
                        "usage": result.get("usage", {})
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"API 调用失败：{response.status_code}",
                        "detail": response.text
                    }
        except Exception as e:
            return {
                "status": "error",
                "error": f"调用异常：{str(e)}"
            }


class ContentGenerationSkill(Skill):
    """内容生成技能（基于百炼）"""
    name = "content_generation"
    description = "使用百炼大模型生成各类内容"
    
    async def execute(self, topic="", content_type="article", length="medium"):
        system_prompt = "你是一位专业的内容创作者，擅长撰写高质量的文章。"
        
        length_map = {
            "short": "300 字以内",
            "medium": "800-1000 字",
            "long": "1500 字以上"
        }
        
        type_map = {
            "article": "文章",
            "report": "报告",
            "email": "邮件",
            "summary": "总结"
        }
        
        user_prompt = f"""请以"{topic}"为主题，写一篇{length_map.get(length, '800 字')}的{type_map.get(content_type, '文章')}。

要求：
1. 结构清晰，逻辑连贯
2. 语言生动，有吸引力
3. 包含实际案例或数据支撑
4. 有明确的开头、主体和结尾"""
        
        llm_skill = BailianLLMSkill()
        result = await llm_skill.execute(
            prompt=user_prompt,
            system_message=system_prompt,
            model="qwen-plus"
        )
        
        return result


class DataAnalysisSkill(Skill):
    """数据分析技能（基于百炼）"""
    name = "data_analysis"
    description = "使用百炼大模型分析数据和提供洞察"
    
    async def execute(self, data_description="", analysis_type="insight"):
        system_prompt = "你是一位资深的数据分析师，擅长从数据中发现规律和提供商业洞察。"
        
        analysis_types = {
            "insight": "数据洞察",
            "trend": "趋势分析",
            "comparison": "对比分析",
            "recommendation": "建议方案"
        }
        
        user_prompt = f"""请对以下数据进行分析：

{data_description}

分析类型：{analysis_types.get(analysis_type, '数据洞察')}

请提供：
1. 关键发现（3-5 点）
2. 数据背后的规律或趋势
3. 可行的行动建议
4. 潜在的风险或机会"""
        
        llm_skill = BailianLLMSkill()
        result = await llm_skill.execute(
            prompt=user_prompt,
            system_message=system_prompt,
            model="qwen-plus"
        )
        
        return result


class FeishuMessageSkill(Skill):
    """飞书消息发送技能"""
    name = "feishu_message"
    description = "发送飞书消息（支持群聊和单聊）"
    
    async def _get_tenant_access_token(self):
        """获取飞书 tenant_access_token"""
        global FEISHU_TOKEN_CACHE
        
        # 检查缓存是否有效
        if 'tenant_access_token' in FEISHU_TOKEN_CACHE:
            cache = FEISHU_TOKEN_CACHE['tenant_access_token']
            if cache['expire'] > datetime.now().timestamp() + 300:  # 提前5分钟刷新
                return cache['token']
        
        # 请求新的 token
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": FEISHU_APP_ID,
            "app_secret": FEISHU_APP_SECRET
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload)
            result = response.json()
            
            if result.get('code') == 0:
                token = result['tenant_access_token']
                expire = result['expire']
                FEISHU_TOKEN_CACHE['tenant_access_token'] = {
                    'token': token,
                    'expire': datetime.now().timestamp() + expire
                }
                return token
            else:
                raise Exception(f"获取 token 失败：{result}")
    
    async def _send_message_v2(self, token, receive_id, content, msg_type="text", receive_id_type="open_id"):
        """使用飞书 API v2 发送消息"""
        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        params = {
            "receive_id_type": receive_id_type
        }
        payload = {
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content) if isinstance(content, dict) else content
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, params=params, json=payload)
            return response.json()
    
    async def execute(self, content="", receiver_type="group", receiver_id="", msg_type="text"):
        """
        receiver_type: "group" (群) 或 "user" (个人)
        receiver_id: 群 ID (chat_id) 或用户 ID (open_id)
        msg_type: text, post, image, interactive 等
        """
        try:
            # 方式 1：使用 Webhook（简单，适合群消息）
            if FEISHU_WEBHOOK and not receiver_id:
                payload = {
                    "msg_type": "text",
                    "content": {
                        "text": content
                    }
                }
                
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(FEISHU_WEBHOOK, json=payload)
                    
                    if response.status_code == 200:
                        result = response.json()
                        if result.get('StatusCode') == 0 or result.get('code') == 0:
                            return {"status": "success", "message": "飞书消息发送成功"}
                        else:
                            return {"status": "error", "error": f"飞书 API 返回错误：{result}"}
                    else:
                        return {"status": "error", "error": f"HTTP 错误：{response.status_code}"}
            
            # 方式 2：使用完整 API
            elif FEISHU_APP_ID and FEISHU_APP_SECRET:
                token = await self._get_tenant_access_token()
                
                # 构建消息内容
                if msg_type == "text":
                    message_content = {"text": content}
                elif msg_type == "post":
                    message_content = content if isinstance(content, dict) else json.loads(content)
                else:
                    message_content = content
                
                # 确定接收者类型
                if receiver_type == "group":
                    receive_id_type = "chat_id"
                else:
                    receive_id_type = "open_id"
                
                result = await self._send_message_v2(
                    token=token,
                    receive_id=receiver_id,
                    content=message_content,
                    msg_type=msg_type,
                    receive_id_type=receive_id_type
                )
                
                if result.get('code') == 0:
                    return {
                        "status": "success", 
                        "message": "飞书消息发送成功",
                        "data": result.get('data', {})
                    }
                else:
                    return {
                        "status": "error", 
                        "error": f"飞书 API 错误：{result.get('msg', '未知错误')}"
                    }
            else:
                return {
                    "status": "error",
                    "error": "飞书配置未设置，请在 app.py 中配置 FEISHU_WEBHOOK 或 FEISHU_APP_ID/SECRET"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"发送失败：{str(e)}"
            }


class EmailSendSkill(Skill):
    """邮件发送技能"""
    name = "email_send"
    description = "发送邮件（SMTP）"
    
    async def execute(self, to_address="", subject="", content="", is_html=False):
        try:
            if not EMAIL_CONFIG["smtp_server"]:
                return {
                    "status": "error",
                    "error": "邮件配置未设置，请在 app.py 中配置 EMAIL_CONFIG"
                }
            
            # 创建邮件
            msg = MIMEMultipart() if is_html else MIMEText(content, 'plain', 'utf-8')
            msg['From'] = EMAIL_CONFIG["username"]
            msg['To'] = to_address
            msg['Subject'] = Header(subject, 'utf-8')
            
            if is_html:
                msg.attach(MIMEText(content, 'html', 'utf-8'))
            
            # 发送邮件
            server = smtplib.SMTP_SSL(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"])
            server.login(EMAIL_CONFIG["username"], EMAIL_CONFIG["password"])
            server.sendmail(EMAIL_CONFIG["username"], [to_address], msg.as_string())
            server.quit()
            
            return {"status": "success", "message": "邮件发送成功"}
            
        except Exception as e:
            return {
                "status": "error",
                "error": f"邮件发送失败：{str(e)}"
            }


class ExcelProcessSkill(Skill):
    """Excel 数据处理技能"""
    name = "excel_process"
    description = "处理 Excel 文件（读取、统计、导出）"
    
    async def execute(self, file_path="", operation="read", sheet_name=0):
        """
        operation: "read" (读取), "summary" (统计摘要), "filter" (筛选)
        file_path: Excel 文件路径
        sheet_name: 工作表名称或索引
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "status": "error",
                    "error": f"文件不存在：{file_path}"
                }
            
            # 读取 Excel
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            
            if operation == "read":
                # 返回前 100 行数据
                data = df.head(100).to_dict('records')
                return {
                    "status": "success",
                    "total_rows": len(df),
                    "columns": list(df.columns),
                    "data": data
                }
            
            elif operation == "summary":
                # 统计摘要
                summary = {
                    "总行数": len(df),
                    "列数": len(df.columns),
                    "列名": list(df.columns),
                    "数值列统计": {}
                }
                
                # 数值列统计
                for col in df.select_dtypes(include=['number']).columns:
                    summary["数值列统计"][col] = {
                        "均值": float(df[col].mean()),
                        "中位数": float(df[col].median()),
                        "最小值": float(df[col].min()),
                        "最大值": float(df[col].max()),
                        "标准差": float(df[col].std())
                    }
                
                return {"status": "success", "summary": summary}
            
            elif operation == "filter":
                # 返回空信息，等待进一步指令
                return {
                    "status": "success",
                    "message": "数据已加载，请使用 filter_conditions 参数进行筛选",
                    "columns": list(df.columns),
                    "sample_data": df.head(5).to_dict('records')
                }
            
            else:
                return {
                    "status": "error",
                    "error": f"不支持的操作：{operation}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"Excel 处理失败：{str(e)}"
            }


class AgentCollaborationSkill(Skill):
    """Agent 间协作技能"""
    name = "agent_collaboration"
    description = "协调多个 Agent 完成复杂任务"
    
    async def execute(self, workflow="", params=None):
        """
        workflow: 工作流名称
        params: 参数字典
        """
        if params is None:
            params = {}
        
        try:
            if workflow == "data_to_report":
                # 工作流程：数据分析 → 内容生成 → 发送报告
                # 步骤 1：数据分析
                data_agent = agents.get("data_agent")
                if not data_agent:
                    return {"status": "error", "error": "找不到数据助手"}
                
                data_result = await data_agent.execute_task(
                    "data_analysis",
                    data_description=params.get("data_description", "")
                )
                
                if data_result["status"] != "success":
                    return data_result
                
                # 步骤 2：生成报告
                content_agent = agents.get("content_agent")
                if not content_agent:
                    return {"status": "error", "error": "找不到内容助手"}
                
                content_result = await content_agent.execute_task(
                    "content_generation",
                    topic=params.get("topic", "数据分析报告"),
                    content_type="report",
                    length="medium"
                )
                
                if content_result["status"] != "success":
                    return content_result
                
                # 步骤 3：发送报告（飞书或邮件）
                service_agent = agents.get("service_agent")
                if not service_agent:
                    return {"status": "error", "error": "找不到客服助手"}
                
                send_method = params.get("send_method", "feishu")
                if send_method == "feishu":
                    send_result = await service_agent.execute_task(
                        "feishu_message",
                        content=f"📊 新的数据分析报告已生成\n\n{content_result.get('content', '')[:500]}..."
                    )
                elif send_method == "email":
                    send_result = await service_agent.execute_task(
                        "email_send",
                        to_address=params.get("email_address", ""),
                        subject=params.get("email_subject", "数据分析报告"),
                        content=content_result.get("content", "")
                    )
                else:
                    send_result = {"status": "success", "message": "未发送，仅生成报告"}
                
                return {
                    "status": "success",
                    "workflow": "data_to_report",
                    "steps": {
                        "data_analysis": data_result,
                        "content_generation": content_result,
                        "send_report": send_result
                    },
                    "final_report": content_result.get("content", "")
                }
            
            else:
                return {
                    "status": "error",
                    "error": f"不支持的工作流：{workflow}"
                }
                
        except Exception as e:
            return {
                "status": "error",
                "error": f"协作流程执行失败：{str(e)}"
            }


class QoderCLISkill(Skill):
    """Qoder CLI 云端任务推送技能"""
    name = "qoder_cli"
    description = "推送任务到云端 Qoder CLI 执行"
    
    async def execute(self, task_type="", task_content="", priority="medium", context=None):
        """
        推送任务到云端 Qoder CLI
        task_type: 任务类型 (code_review, generate_code, analysis, etc.)
        task_content: 任务内容描述
        priority: 优先级 (high, medium, low)
        context: 额外上下文信息
        """
        try:
            if not QODER_CLI_CONFIG["enabled"]:
                return {
                    "status": "error",
                    "error": "Qoder CLI 推送未启用，请在配置中开启"
                }
            
            if not QODER_CLI_CONFIG["base_url"]:
                return {
                    "status": "error",
                    "error": "Qoder CLI 地址未配置"
                }
            
            # 构建任务数据
            task_data = {
                "task_type": task_type,
                "task_content": task_content,
                "priority": priority,
                "context": context or {},
                "source": "malaclaw",
                "timestamp": datetime.now().isoformat()
            }
            
            # 发送到云端 Qoder CLI
            headers = {
                "Content-Type": "application/json"
            }
            if QODER_CLI_CONFIG["api_key"]:
                headers["Authorization"] = f"Bearer {QODER_CLI_CONFIG['api_key']}"
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{QODER_CLI_CONFIG['base_url']}/api/tasks",
                    headers=headers,
                    json=task_data
                )
                
                if response.status_code == 200:
                    result = response.json()
                    return {
                        "status": "success",
                        "message": "任务已推送到云端 Qoder CLI",
                        "task_id": result.get("task_id"),
                        "queued_at": result.get("queued_at")
                    }
                else:
                    return {
                        "status": "error",
                        "error": f"推送失败：HTTP {response.status_code}",
                        "detail": response.text
                    }
                    
        except Exception as e:
            return {
                "status": "error",
                "error": f"推送异常：{str(e)}"
            }


class TodoManagerSkill(Skill):
    """TODO List 管理技能"""
    name = "todo_manager"
    description = "管理 TODO List，支持自动决策推送"
    
    async def execute(self, action="list", todo_id=None, title="", description="", 
                      priority="medium", auto_push=False):
        """
        action: list, add, update, delete, sync, auto_decide
        """
        global todo_list, todo_last_sync
        
        try:
            if action == "list":
                return {
                    "status": "success",
                    "todos": todo_list,
                    "count": len(todo_list),
                    "last_sync": todo_last_sync
                }
            
            elif action == "add":
                if not title:
                    return {"status": "error", "error": "标题不能为空"}
                
                todo = {
                    "id": f"todo_{datetime.now().strftime('%Y%m%d%H%M%S')}_{len(todo_list)}",
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "status": "pending",
                    "created_at": datetime.now().isoformat(),
                    "pushed_to_cloud": False,
                    "cloud_task_id": None
                }
                todo_list.append(todo)
                
                # 如果启用自动推送且优先级高，立即推送
                if auto_push and priority == "high" and QODER_CLI_CONFIG["enabled"]:
                    qoder_skill = QoderCLISkill()
                    push_result = await qoder_skill.execute(
                        task_type="auto_task",
                        task_content=f"{title}\n{description}",
                        priority=priority,
                        context={"todo_id": todo["id"]}
                    )
                    if push_result["status"] == "success":
                        todo["pushed_to_cloud"] = True
                        todo["cloud_task_id"] = push_result.get("task_id")
                
                return {
                    "status": "success",
                    "message": "TODO 添加成功",
                    "todo": todo
                }
            
            elif action == "update":
                for todo in todo_list:
                    if todo["id"] == todo_id:
                        if title:
                            todo["title"] = title
                        if description:
                            todo["description"] = description
                        if priority:
                            todo["priority"] = priority
                        todo["updated_at"] = datetime.now().isoformat()
                        return {"status": "success", "todo": todo}
                return {"status": "error", "error": "TODO 不存在"}
            
            elif action == "delete":
                todo_list[:] = [t for t in todo_list if t["id"] != todo_id]
                return {"status": "success", "message": "删除成功"}
            
            elif action == "sync":
                # 模拟从外部同步 TODO List
                todo_last_sync = datetime.now().isoformat()
                return {
                    "status": "success",
                    "message": "同步完成",
                    "sync_time": todo_last_sync,
                    "count": len(todo_list)
                }
            
            elif action == "auto_decide":
                # 自动决策：根据规则决定哪些任务推送到云端
                return await self._auto_decide_push()
            
            else:
                return {"status": "error", "error": f"未知操作：{action}"}
                
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    async def _auto_decide_push(self):
        """自动决策推送逻辑"""
        if not QODER_CLI_CONFIG["enabled"]:
            return {"status": "success", "message": "自动推送未启用", "pushed": []}
        
        pushed = []
        qoder_skill = QoderCLISkill()
        
        for todo in todo_list:
            # 规则1：高优先级未推送任务
            # 规则2：pending 状态超过一定时间的任务
            should_push = (
                not todo.get("pushed_to_cloud") and
                todo["status"] == "pending" and
                (todo["priority"] == "high" or self._is_overdue(todo))
            )
            
            if should_push:
                result = await qoder_skill.execute(
                    task_type="auto_task",
                    task_content=f"{todo['title']}\n{todo.get('description', '')}",
                    priority=todo["priority"],
                    context={"todo_id": todo["id"], "source": "auto_decide"}
                )
                
                if result["status"] == "success":
                    todo["pushed_to_cloud"] = True
                    todo["cloud_task_id"] = result.get("task_id")
                    todo["pushed_at"] = datetime.now().isoformat()
                    pushed.append(todo)
        
        return {
            "status": "success",
            "message": f"自动推送完成，推送了 {len(pushed)} 个任务",
            "pushed": pushed
        }
    
    def _is_overdue(self, todo):
        """检查任务是否超时（超过30分钟未处理）"""
        created = datetime.fromisoformat(todo["created_at"])
        return (datetime.now() - created).total_seconds() > 1800


# 注册所有 Skills
available_skills = {
    "hello": HelloSkill(),
    "screenshot": ScreenshotSkill(),
    "api_call": APICallSkill(),
    "bailian_llm": BailianLLMSkill(),
    "content_generation": ContentGenerationSkill(),
    "data_analysis": DataAnalysisSkill(),
    "feishu_message": FeishuMessageSkill(),
    "email_send": EmailSendSkill(),
    "excel_process": ExcelProcessSkill(),
    "agent_collaboration": AgentCollaborationSkill(),
    "qoder_cli": QoderCLISkill(),
    "todo_manager": TodoManagerSkill()
}


# ==================== Agent 定义 ====================

class Agent:
    """Agent 基类"""
    def __init__(self, name, role, skills):
        self.name = name
        self.role = role
        self.skills = skills  # Skill 名称列表
        self.state = "idle"  # idle, working, error
    
    async def execute_task(self, skill_name, **kwargs):
        """执行任务"""
        if skill_name not in available_skills:
            return {"status": "error", "error": f"未知的技能：{skill_name}"}
        
        self.state = "working"
        skill = available_skills[skill_name]
        
        try:
            result = await skill.execute(**kwargs)
            self.state = "idle"
            return result
        except Exception as e:
            self.state = "error"
            logger.error(f"Agent {self.name} 执行失败：{e}")
            return {"status": "error", "error": str(e)}


# 创建默认 Agents
agents["content_agent"] = Agent("内容助手", "内容创作", ["hello", "screenshot", "content_generation", "bailian_llm"])
agents["data_agent"] = Agent("数据助手", "数据分析", ["hello", "api_call", "data_analysis", "bailian_llm", "excel_process"])
agents["service_agent"] = Agent("客服助手", "客户服务", ["hello", "bailian_llm", "feishu_message", "email_send"])
agents["coordinator"] = Agent("协调员", "任务协调", ["agent_collaboration", "bailian_llm"])
agents["feishu_agent"] = Agent("飞书助手", "飞书消息推送", ["feishu_message", "hello"])
agents["todo_agent"] = Agent("任务管家", "TODO 管理与自动推送", ["todo_manager", "qoder_cli", "bailian_llm"])


# ==================== Web 路由 ====================

@app.route('/')
def index():
    """首页（宣传页面）"""
    return render_template('home_page.html')


@app.route('/home')
def home():
    """官网首页（备用路由）"""
    return render_template('home_page.html')


@app.route('/dashboard')
def dashboard():
    """控制台页面"""
    return render_template('dashboard.html')


@app.route('/logo.svg')
def logo():
    """LOGO 文件"""
    return send_from_directory('.', 'logo.svg')


@app.route('/favicon.svg')
def favicon():
    """Favicon 文件"""
    return send_from_directory('.', 'favicon.svg')


@app.route('/static/<path:filename>')
def static_files(filename):
    """静态文件服务"""
    return send_from_directory('static', filename)


@app.route('/api/agents', methods=['GET'])
def get_agents():
    """获取所有 Agent"""
    agent_list = []
    for key, agent in agents.items():
        agent_list.append({
            "id": key,
            "name": agent.name,
            "role": agent.role,
            "state": agent.state,
            "skills": agent.skills
        })
    return jsonify(agent_list)


@app.route('/api/skills', methods=['GET'])
def get_skills():
    """获取所有可用技能"""
    skill_list = []
    for key, skill in available_skills.items():
        skill_list.append({
            "id": key,
            "name": skill.name,
            "description": skill.description
        })
    return jsonify(skill_list)


@app.route('/api/execute', methods=['POST'])
async def execute_task():
    """立即执行任务"""
    data = request.json
    agent_id = data.get('agent_id')
    skill_id = data.get('skill_id')
    params = data.get('params', {})
    
    if not agent_id or not skill_id:
        return jsonify({"status": "error", "error": "缺少参数"}), 400
    
    if agent_id not in agents:
        return jsonify({"status": "error", "error": "Agent 不存在"}), 400
    
    agent = agents[agent_id]
    result = await agent.execute_task(skill_id, **params)
    
    # 记录日志
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": "manual",
        "agent": agent.name,
        "skill": skill_id,
        "status": result.get("status", "unknown"),
        "result": str(result)[:200]  # 限制长度
    }
    execution_logs.append(log_entry)
    
    return jsonify(result)


@app.route('/api/jobs', methods=['GET'])
def get_jobs():
    """获取所有定时任务"""
    job_list = []
    for job_id, job_info in jobs.items():
        job = job_info['job']
        job_list.append({
            "id": job_id,
            "name": job_info['name'],
            "agent": job_info['agent'],
            "skill": job_info['skill'],
            "cron": job_info['cron'],
            "next_run": str(job.next_run_time) if job.next_run_time else "未知",
            # 此状态表示是否启用调度，不表示技能此刻正在执行。
            "status": "running" if job.next_run_time is not None else "paused"
        })
    return jsonify(job_list)


@app.route('/api/jobs', methods=['POST'])
def create_job():
    """创建定时任务"""
    data = request.json
    job_id = data.get('id')
    job_name = data.get('name')
    agent_id = data.get('agent_id')
    skill_id = data.get('skill_id')
    cron_expr = data.get('cron')
    params = data.get('params', {})
    
    if not all([job_id, job_name, agent_id, skill_id, cron_expr]):
        return jsonify({"status": "error", "error": "缺少参数"}), 400
    
    if agent_id not in agents:
        return jsonify({"status": "error", "error": "Agent 不存在"}), 400
    
    # BackgroundScheduler 在线程中调用同步函数，需要等待异步技能完成。
    def run_task():
        logger.info(f"执行定时任务：{job_name}")
        agent = agents[agent_id]
        result = asyncio.run(agent.execute_task(skill_id, **params))
        
        # 记录日志
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "scheduled",
            "job": job_name,
            "agent": agent.name,
            "skill": skill_id,
            "status": result.get("status", "unknown"),
            "result": str(result)[:200]
        }
        execution_logs.append(log_entry)
    
    trigger = CronTrigger.from_crontab(cron_expr)
    job = scheduler.add_job(run_task, trigger, id=job_id, replace_existing=True)
    
    jobs[job_id] = {
        'job': job,
        'name': job_name,
        'agent': agent_id,
        'skill': skill_id,
        'cron': cron_expr,
        'params': params
    }
    
    return jsonify({"status": "success", "message": "任务创建成功"})


@app.route('/api/jobs/<job_id>/pause', methods=['POST'])
def pause_job(job_id):
    """暂停任务"""
    if job_id in jobs:
        jobs[job_id]['job'].pause()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "error": "任务不存在"}), 404


@app.route('/api/jobs/<job_id>/resume', methods=['POST'])
def resume_job(job_id):
    """恢复任务"""
    if job_id in jobs:
        jobs[job_id]['job'].resume()
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "error": "任务不存在"}), 404


@app.route('/api/jobs/<job_id>', methods=['DELETE'])
def remove_job(job_id):
    """删除任务"""
    if job_id in jobs:
        scheduler.remove_job(job_id)
        del jobs[job_id]
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "error": "任务不存在"}), 404


@app.route('/api/logs', methods=['GET'])
def get_logs():
    """获取执行日志（最近 50 条）"""
    return jsonify(execution_logs[-50:])


@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "agents_count": len(agents),
        "jobs_count": len(jobs),
        "logs_count": len(execution_logs)
    })


@app.route('/daily_push')
def daily_push_page():
    """每日推送页面"""
    return render_template('daily_push.html')


@app.route('/scenarios')
def scenarios_page():
    """场景商城页面"""
    return render_template('scenarios.html')


@app.route('/todos')
def todos_page():
    """任务管理页面"""
    return render_template('todos.html')


@app.route('/config')
def config_page():
    """系统配置页面"""
    return render_template('config.html')


@app.route('/api/feishu/chats', methods=['GET'])
async def get_feishu_chats():
    """获取飞书群列表"""
    try:
        # 检查是否配置了 App ID 和 App Secret
        if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
            return jsonify({
                "status": "error",
                "error": "未配置飞书 App ID 和 App Secret，请使用自建应用方式（Webhook 方式不支持获取群列表）"
            }), 400
        
        skill = FeishuMessageSkill()
        token = await skill._get_tenant_access_token()
        
        url = "https://open.feishu.cn/open-apis/im/v1/chats"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            result = response.json()
            
            if result.get('code') == 0:
                chats = result.get('data', {}).get('items', [])
                return jsonify({
                    "status": "success",
                    "data": chats,
                    "count": len(chats)
                })
            else:
                error_msg = result.get('msg', '获取失败')
                logger.error(f"飞书 API 返回错误：{error_msg}")
                return jsonify({
                    "status": "error",
                    "error": f"飞书 API 错误：{error_msg}"
                }), 400
    except Exception as e:
        logger.error(f"获取飞书群列表异常：{str(e)}")
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/feishu/send', methods=['POST'])
async def send_feishu_message():
    """发送飞书消息 API"""
    try:
        data = request.json
        content = data.get('content', '')
        receiver_type = data.get('receiver_type', 'group')
        receiver_id = data.get('receiver_id', '')
        msg_type = data.get('msg_type', 'text')
        
        if not content:
            return jsonify({"status": "error", "error": "消息内容不能为空"}), 400
        
        if not receiver_id:
            return jsonify({"status": "error", "error": "接收者 ID 不能为空"}), 400
        
        skill = FeishuMessageSkill()
        result = await skill.execute(
            content=content,
            receiver_type=receiver_type,
            receiver_id=receiver_id,
            msg_type=msg_type
        )
        
        # 记录日志
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "manual",
            "job": "feishu_send",
            "agent": "MalaClaw",
            "skill": "feishu_message",
            "status": result.get("status", "unknown"),
            "result": str(result)[:200]
        }
        execution_logs.append(log_entry)
        
        if result.get('status') == 'success':
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/config', methods=['GET'])
def get_config():
    """获取所有配置（敏感信息脱敏）"""
    return jsonify({
        "status": "success",
        "data": {
            "bailian": {
                "api_key": "***" + BAILIAN_API_KEY[-8:] if BAILIAN_API_KEY else "",
                "base_url": BAILIAN_BASE_URL
            },
            "feishu": {
                "webhook": FEISHU_WEBHOOK,
                "app_id": FEISHU_APP_ID,
                "app_secret": "***" + FEISHU_APP_SECRET[-8:] if FEISHU_APP_SECRET else ""
            },
            "email": {
                "smtp_server": EMAIL_CONFIG["smtp_server"],
                "smtp_port": EMAIL_CONFIG["smtp_port"],
                "username": EMAIL_CONFIG["username"]
            },
            "qoder_cli": {
                "base_url": QODER_CLI_CONFIG["base_url"],
                "enabled": QODER_CLI_CONFIG["enabled"]
            }
        }
    })


@app.route('/api/config', methods=['POST'])
def update_config():
    """更新配置"""
    global BAILIAN_API_KEY, BAILIAN_BASE_URL
    global FEISHU_WEBHOOK, FEISHU_APP_ID, FEISHU_APP_SECRET
    global EMAIL_CONFIG, QODER_CLI_CONFIG, config
    
    try:
        data = request.json
        
        # 更新百炼配置
        if "bailian" in data:
            if data["bailian"].get("api_key"):
                BAILIAN_API_KEY = data["bailian"]["api_key"]
                config["bailian"]["api_key"] = BAILIAN_API_KEY
            if data["bailian"].get("base_url"):
                BAILIAN_BASE_URL = data["bailian"]["base_url"]
                config["bailian"]["base_url"] = BAILIAN_BASE_URL
        
        # 更新飞书配置
        if "feishu" in data:
            if data["feishu"].get("webhook") is not None:
                FEISHU_WEBHOOK = data["feishu"]["webhook"]
                config["feishu"]["webhook"] = FEISHU_WEBHOOK
            if data["feishu"].get("app_id"):
                FEISHU_APP_ID = data["feishu"]["app_id"]
                config["feishu"]["app_id"] = FEISHU_APP_ID
            if data["feishu"].get("app_secret"):
                FEISHU_APP_SECRET = data["feishu"]["app_secret"]
                config["feishu"]["app_secret"] = FEISHU_APP_SECRET
        
        # 更新邮件配置
        if "email" in data:
            for key in ["smtp_server", "smtp_port", "username", "password"]:
                if key in data["email"]:
                    EMAIL_CONFIG[key] = data["email"][key]
                    config["email"][key] = data["email"][key]
        
        # 更新 Qoder CLI 配置
        if "qoder_cli" in data:
            for key in ["base_url", "api_key", "enabled"]:
                if key in data["qoder_cli"]:
                    QODER_CLI_CONFIG[key] = data["qoder_cli"][key]
                    config["qoder_cli"][key] = data["qoder_cli"][key]
        
        # 保存到文件
        if save_config(config):
            return jsonify({"status": "success", "message": "配置已保存"})
        else:
            return jsonify({"status": "error", "error": "保存配置文件失败"}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/config/feishu', methods=['GET'])
def get_feishu_config():
    """获取飞书配置（敏感信息脱敏）"""
    return jsonify({
        "status": "success",
        "data": {
            "app_name": config["feishu"].get("app_name", "MalaClaw"),
            "app_id": FEISHU_APP_ID,
            "app_secret": "***" + FEISHU_APP_SECRET[-8:] if FEISHU_APP_SECRET else "",
            "encrypt_key": config["feishu"].get("encrypt_key", ""),
            "verification_token": config["feishu"].get("verification_token", ""),
            "webhook": FEISHU_WEBHOOK
        }
    })


@app.route('/api/config/feishu', methods=['POST'])
def set_feishu_config():
    """设置飞书配置"""
    global FEISHU_APP_ID, FEISHU_APP_SECRET, FEISHU_WEBHOOK, config
    try:
        data = request.json
        
        # 更新配置
        if data.get('webhook') is not None:
            FEISHU_WEBHOOK = data['webhook']
            config["feishu"]["webhook"] = FEISHU_WEBHOOK
        
        if data.get('app_id'):
            FEISHU_APP_ID = data['app_id']
            config["feishu"]["app_id"] = FEISHU_APP_ID
        
        if data.get('app_secret'):
            FEISHU_APP_SECRET = data['app_secret']
            config["feishu"]["app_secret"] = FEISHU_APP_SECRET
        
        if data.get('app_name'):
            config["feishu"]["app_name"] = data['app_name']
        
        if data.get('encrypt_key') is not None:
            config["feishu"]["encrypt_key"] = data['encrypt_key']
        
        if data.get('verification_token') is not None:
            config["feishu"]["verification_token"] = data['verification_token']
        
        # 保存到文件
        if save_config(config):
            # 重新加载配置以确保内存中的值与文件同步
            reload_feishu_config()
            return jsonify({"status": "success", "message": "飞书配置已保存"})
        else:
            return jsonify({"status": "error", "error": "保存配置文件失败"}), 500
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/config/email', methods=['GET'])
def get_email_config():
    """获取邮件配置（不包含密码）- 兼容旧接口"""
    return jsonify({
        "status": "success",
        "data": {
            "smtp_server": EMAIL_CONFIG["smtp_server"],
            "smtp_port": EMAIL_CONFIG["smtp_port"],
            "username": EMAIL_CONFIG["username"]
        }
    })


@app.route('/api/config/email', methods=['POST'])
def set_email_config():
    """设置邮件配置 - 兼容旧接口"""
    global EMAIL_CONFIG, config
    try:
        data = request.json
        EMAIL_CONFIG["smtp_server"] = data.get('smtp_server', '')
        EMAIL_CONFIG["smtp_port"] = data.get('smtp_port', 465)
        EMAIL_CONFIG["username"] = data.get('username', '')
        EMAIL_CONFIG["password"] = data.get('password', '')
        
        # 同步到 config 并保存
        config["email"] = EMAIL_CONFIG.copy()
        save_config(config)
        
        return jsonify({"status": "success", "message": "邮件配置已保存"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/email/test', methods=['POST'])
async def test_email():
    """测试邮件发送"""
    try:
        data = request.json
        to_address = data.get('to_address', '')
        subject = data.get('subject', 'MalaClaw 邮件测试')
        content = data.get('content', '这是一封测试邮件')
        
        if not to_address:
            return jsonify({"status": "error", "error": "收件人地址不能为空"}), 400
        
        skill = EmailSendSkill()
        result = await skill.execute(
            to_address=to_address,
            subject=subject,
            content=content
        )
        
        # 记录日志
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "manual",
            "job": "email_test",
            "agent": "MalaClaw",
            "skill": "email_send",
            "status": result.get("status", "unknown"),
            "result": str(result)[:200]
        }
        execution_logs.append(log_entry)
        
        if result.get('status') == 'success':
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/email/send', methods=['POST'])
async def send_email():
    """发送邮件 API"""
    try:
        data = request.json
        to_address = data.get('to_address', '')
        subject = data.get('subject', '')
        content = data.get('content', '')
        is_html = data.get('is_html', False)
        
        if not to_address:
            return jsonify({"status": "error", "error": "收件人地址不能为空"}), 400
        
        if not subject:
            return jsonify({"status": "error", "error": "邮件主题不能为空"}), 400
        
        skill = EmailSendSkill()
        result = await skill.execute(
            to_address=to_address,
            subject=subject,
            content=content,
            is_html=is_html
        )
        
        # 记录日志
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "manual",
            "job": "email_send",
            "agent": "MalaClaw",
            "skill": "email_send",
            "status": result.get("status", "unknown"),
            "result": str(result)[:200]
        }
        execution_logs.append(log_entry)
        
        if result.get('status') == 'success':
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ==================== TODO List API ====================

@app.route('/api/todos', methods=['GET'])
def get_todos():
    """获取 TODO List"""
    return jsonify({
        "status": "success",
        "todos": todo_list,
        "count": len(todo_list),
        "last_sync": todo_last_sync
    })


@app.route('/api/todos', methods=['POST'])
async def create_todo():
    """创建 TODO"""
    try:
        data = request.json
        title = data.get('title', '')
        description = data.get('description', '')
        priority = data.get('priority', 'medium')
        auto_push = data.get('auto_push', False)
        
        if not title:
            return jsonify({"status": "error", "error": "标题不能为空"}), 400
        
        skill = TodoManagerSkill()
        result = await skill.execute(
            action="add",
            title=title,
            description=description,
            priority=priority,
            auto_push=auto_push
        )
        
        if result["status"] == "success":
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/todos/<todo_id>', methods=['PUT'])
async def update_todo(todo_id):
    """更新 TODO"""
    try:
        data = request.json
        skill = TodoManagerSkill()
        result = await skill.execute(
            action="update",
            todo_id=todo_id,
            title=data.get('title'),
            description=data.get('description'),
            priority=data.get('priority')
        )
        
        if result["status"] == "success":
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/todos/<todo_id>', methods=['DELETE'])
async def delete_todo(todo_id):
    """删除 TODO"""
    try:
        skill = TodoManagerSkill()
        result = await skill.execute(action="delete", todo_id=todo_id)
        
        if result["status"] == "success":
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/todos/sync', methods=['POST'])
async def sync_todos():
    """同步 TODO List"""
    try:
        skill = TodoManagerSkill()
        result = await skill.execute(action="sync")
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/todos/auto-push', methods=['POST'])
async def auto_push_todos():
    """自动决策推送 TODO 到云端"""
    try:
        skill = TodoManagerSkill()
        result = await skill.execute(action="auto_decide")
        
        # 记录日志
        if result.get("pushed"):
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "scheduled",
                "job": "auto_push_todos",
                "agent": "任务管家",
                "skill": "todo_manager",
                "status": "success",
                "result": f"推送了 {len(result['pushed'])} 个任务"
            }
            execution_logs.append(log_entry)
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/qoder-cli/config', methods=['GET'])
def get_qoder_cli_config():
    """获取 Qoder CLI 配置"""
    return jsonify({
        "status": "success",
        "data": {
            "base_url": QODER_CLI_CONFIG["base_url"],
            "enabled": QODER_CLI_CONFIG["enabled"]
            # api_key 不返回
        }
    })


@app.route('/api/qoder-cli/config', methods=['POST'])
def set_qoder_cli_config():
    """设置 Qoder CLI 配置"""
    global QODER_CLI_CONFIG
    try:
        data = request.json
        QODER_CLI_CONFIG["base_url"] = data.get('base_url', '')
        QODER_CLI_CONFIG["api_key"] = data.get('api_key', '')
        QODER_CLI_CONFIG["enabled"] = data.get('enabled', False)
        
        return jsonify({"status": "success", "message": "配置已保存"})
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@app.route('/api/qoder-cli/push', methods=['POST'])
async def push_to_qoder_cli():
    """手动推送任务到 Qoder CLI"""
    try:
        data = request.json
        task_type = data.get('task_type', '')
        task_content = data.get('task_content', '')
        priority = data.get('priority', 'medium')
        context = data.get('context', {})
        
        if not task_content:
            return jsonify({"status": "error", "error": "任务内容不能为空"}), 400
        
        skill = QoderCLISkill()
        result = await skill.execute(
            task_type=task_type,
            task_content=task_content,
            priority=priority,
            context=context
        )
        
        # 记录日志
        log_entry = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "manual",
            "job": "qoder_push",
            "agent": "MalaClaw",
            "skill": "qoder_cli",
            "status": result.get("status", "unknown"),
            "result": str(result)[:200]
        }
        execution_logs.append(log_entry)
        
        if result.get('status') == 'success':
            return jsonify(result)
        else:
            return jsonify(result), 400
            
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


# ==================== 定时任务定义 ====================

async def scheduled_todo_sync():
    """定时同步 TODO List 并自动推送"""
    logger.info("执行定时 TODO 同步任务...")
    
    try:
        # 1. 同步 TODO List
        sync_skill = TodoManagerSkill()
        sync_result = await sync_skill.execute(action="sync")
        logger.info(f"TODO 同步结果: {sync_result}")
        
        # 2. 自动决策推送
        if QODER_CLI_CONFIG["enabled"]:
            push_result = await sync_skill.execute(action="auto_decide")
            logger.info(f"自动推送结果: {push_result}")
            
            # 记录日志
            if push_result.get("pushed"):
                log_entry = {
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "type": "scheduled",
                    "job": "scheduled_todo_sync",
                    "agent": "任务管家",
                    "skill": "todo_manager",
                    "status": "success",
                    "result": f"定时推送了 {len(push_result['pushed'])} 个任务"
                }
                execution_logs.append(log_entry)
    except Exception as e:
        logger.error(f"定时任务执行失败: {e}")


def run_scheduled_sync():
    """运行定时同步（同步包装器）"""
    asyncio.run(scheduled_todo_sync())


# ==================== 启动应用 ====================

if __name__ == '__main__':
    # 启动调度器
    scheduler.start()
    
    # 注册定时任务：每5分钟同步一次 TODO List 并自动推送
    scheduler.add_job(
        run_scheduled_sync,
        'interval',
        minutes=5,
        id='todo_auto_sync',
        replace_existing=True
    )
    logger.info("已注册定时任务：每5分钟同步 TODO List 并自动推送")
    
    logger.info("🚀 OpenClaw 精简版启动中...")
    logger.info("📊 访问地址：http://localhost:5000")
    
    # 运行 Flask 应用
    app.run(host='0.0.0.0', port=5000, debug=True)
