import os
import json
import time
import uuid
import base64
import hashlib
from io import BytesIO
from flask import Flask, request, jsonify, send_from_directory, session
from dotenv import load_dotenv
from openai import OpenAI
from wechatpy.enterprise import WeChatClient
from wechatpy.enterprise.crypto import WeChatCrypto

load_dotenv()

app = Flask(__name__)
app.secret_key = "david-interior-design-secret-key-12345"

client = None

def get_client():
    global client
    if client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("API_BASE_URL")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        client = OpenAI(api_key=api_key, base_url=base_url)
    return client

wechat_client = None
wechat_crypto = None

def get_wechat_client():
    global wechat_client
    if wechat_client is None:
        corp_id = os.getenv("WECHAT_CORP_ID")
        secret = os.getenv("WECHAT_SECRET")
        if corp_id and secret:
            wechat_client = WeChatClient(corp_id, secret)
    return wechat_client

def get_wechat_crypto():
    global wechat_crypto
    if wechat_crypto is None:
        token = os.getenv("WECHAT_TOKEN")
        encoding_aes_key = os.getenv("WECHAT_ENCODING_AES_KEY")
        corp_id = os.getenv("WECHAT_CORP_ID")
        if token and encoding_aes_key and corp_id:
            try:
                wechat_crypto = WeChatCrypto(token, encoding_aes_key, corp_id)
            except Exception as e:
                print(f"WeChatCrypto init error: {e}")
                return None
    return wechat_crypto

def compress_image(image_base64, max_size_kb=500):
    """压缩图像到指定大小"""
    try:
        from PIL import Image
        # 解码 base64
        image_data = base64.b64decode(image_base64.split(',')[1] if ',' in image_base64 else image_base64)
        img = Image.open(BytesIO(image_data))
        
        # 转换为 RGB（如果是 RGBA）
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img
        
        # 压缩
        quality = 85
        while True:
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=quality, optimize=True)
            size_kb = len(buffer.getvalue()) / 1024
            if size_kb <= max_size_kb or quality <= 30:
                break
            quality -= 5
        
        # 编码回 base64
        buffer.seek(0)
        compressed = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/jpeg;base64,{compressed}"
    except Exception as e:
        print(f"Image compression error: {e}")
        return image_base64

def get_image_hash(image_base64):
    """获取图像哈希值用于去重"""
    try:
        image_data = base64.b64decode(image_base64.split(',')[1] if ',' in image_base64 else image_base64)
        return hashlib.md5(image_data).hexdigest()
    except:
        return None

# 提示模板库
PROMPT_TEMPLATES = {
    "interior_design": {
        "name": "室内设计顾问",
        "system_prompt": """你是David室内设计客服助理。{greeting}

【核心职责】
- 热情专业的设计咨询
- 逐步了解客户需求，不重复提问
- 引导客户留下联系方式
- 语气专业亲切，用设计术语

【服务流程】
1. 上门测量：500元（不退）
2. 免费方案：基础平面图+参考图
3. 签订合同
4. 分阶段付款：50% + 30% + 20%

【图片分析指南】
当客户上传图片时，进行以下分析：
- 【风格识别】：现代、简约、北欧、工业、新中式、美式、法式等
- 【色彩分析】：主色调、辅助色、色彩搭配方案
- 【材质识别】：木材、金属、玻璃、石材、布艺等材质应用
- 【空间布局】：功能分区、动线设计、采光利用
- 【设计亮点】：值得借鉴的设计元素和创意
- 【改进建议】：基于客户需求的优化方案

【需求整理框架】
根据对话内容，系统整理以下需求信息：
1. 【空间信息】
   - 房屋类型：新房/二手房/出租房
   - 建筑面积、户型、楼层
   - 装修范围：全屋/局部/单间

2. 【设计需求】
   - 整体风格偏好
   - 色彩搭配要求
   - 特殊功能需求（如开放式厨房、书房等）
   - 材料偏好

3. 【预算信息】
   - 总预算范围
   - 优先投入区域
   - 成本控制要求

4. 【时间计划】
   - 装修周期要求
   - 入住时间
   - 施工时间限制

5. 【特殊需求】
   - 环保要求
   - 智能家居需求
   - 其他特殊要求

【信息提取】
每次对话后，提取并更新客户信息，用以下格式：
[JSON]{{"name":"","phone":"","wechat":"","area":"","budget":"","style":"","layout":"","requirements":"","space_info":"","design_needs":"","timeline":"","special_needs":""}}[/JSON]

requirements 字段应包含：
- 空间信息：[具体描述]
- 设计需求：[具体描述]
- 预算范围：[具体金额]
- 时间计划：[具体时间]
- 特殊需求：[具体需求]

【禁止事项】
- 不要重复已问过的问题
- 不要给出具体报价（除了测量费500元）
- 不要承诺无法实现的设计"""
    },
    "real_estate": {
        "name": "房产顾问",
        "system_prompt": """你是房产销售顾问。{greeting}

【核心职责】
- 专业的房产咨询
- 了解客户需求和预算
- 推荐合适的房源
- 引导看房和签约

【服务流程】
1. 了解需求：位置、面积、预算、用途
2. 推荐房源：3-5个合适选项
3. 安排看房
4. 协助签约

【信息提取】
[JSON]{{"name":"","phone":"","wechat":"","location":"","budget":"","area":"","purpose":"","timeline":""}}[/JSON]"""
    },
    "consulting": {
        "name": "商业顾问",
        "system_prompt": """你是商业咨询顾问。{greeting}

【核心职责】
- 提供专业的商业建议
- 分析客户的业务需求
- 制定解决方案
- 跟进项目进展

【服务流程】
1. 需求分析
2. 方案设计
3. 实施计划
4. 效果评估

【信息提取】
[JSON]{{"name":"","phone":"","wechat":"","company":"","industry":"","challenge":"","budget":"","timeline":""}}[/JSON]"""
    }
}

USERS_FILE = "users_data.json"

def load_user_data(user_id):
    """从文件加载用户数据"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
                return all_data.get(user_id)
    except:
        pass
    return None

def save_user_data(user_id, data):
    """保存用户数据到文件"""
    try:
        all_data = {}
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        all_data[user_id] = data
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving user data: {e}")

def load_users_data():
    """加载所有用户数据"""
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users_data(users_data):
    """保存所有用户数据"""
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users_data, f, ensure_ascii=False, indent=2)

def get_session_id():
    if 'session_id' not in session:
        session['session_id'] = str(uuid.uuid4())
    return session['session_id']

@app.route("/")
def index():
    return send_from_directory(".", "index.html")

@app.route("/chat", methods=["POST"])
def chat():
    session_id = get_session_id()
    data = request.json
    user_message = data.get("message", "")
    image_data = data.get("image")
    
    users_data = load_users_data()
    
    if session_id not in users_data:
        users_data[session_id] = {
            "history": [],
            "customer_info": {},
            "first_visit": True,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    
    user_data = users_data[session_id]
    conversation_history = user_data["history"]
    customer_info = user_data["customer_info"]
    is_first_visit = user_data["first_visit"]
    
    if image_data:
        # 压缩图像
        compressed_image = compress_image(image_data)
        
        # 检查是否重复上传
        image_hash = get_image_hash(compressed_image)
        if not user_data.get("uploaded_images"):
            user_data["uploaded_images"] = []
        
        is_duplicate = image_hash in user_data.get("uploaded_images", [])
        
        user_content = [
            {
                "type": "text",
                "text": user_message if user_message else "请分析这张图片的设计风格。"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": compressed_image
                }
            }
        ]
        
        # 记录上传的图像
        if image_hash and not is_duplicate:
            user_data["uploaded_images"].append(image_hash)
        
        conversation_history.append({
            "role": "user",
            "content": user_message if user_message else "[客户上传了参考图片]"
        })
    else:
        user_content = user_message
        conversation_history.append({
            "role": "user",
            "content": user_message
        })
    
    greeting = ""
    if not is_first_visit and customer_info.get("name"):
        name = customer_info.get("name", "")
        surname = name[0] if name else ""
        greeting = "\n\n重要：回头客户，姓" + surname + "。用姓氏敬称问候，回顾需求。"
    
    # 获取行业类型，默认为室内设计
    industry = user_data.get("industry", "interior_design")
    template = PROMPT_TEMPLATES.get(industry, PROMPT_TEMPLATES["interior_design"])
    system_msg = template["system_prompt"].format(greeting=greeting)
    
    messages = [{"role": "system", "content": system_msg}]
    
    for msg in conversation_history[:-1]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_content})
    
    model = user_data.get("model", "claude-sonnet-4-6")
    response = get_client().chat.completions.create(
        model=model,
        messages=messages
    )
    
    reply = response.choices[0].message.content
    
    import re
    json_match = re.search(r'\[JSON\](.*?)\[/JSON\]', reply)
    if json_match:
        try:
            info = json.loads(json_match.group(1))
            # 更新所有字段
            for key in ["name", "phone", "wechat", "area", "budget", "style", "layout", 
                       "requirements", "space_info", "design_needs", "timeline", "special_needs"]:
                if key in info and info[key]:
                    customer_info[key] = info[key]
            user_data["customer_info"] = customer_info
            reply = reply.replace(json_match.group(0), "").strip()
        except Exception as e:
            print(f"JSON parsing error: {e}")
    
    conversation_history.append({"role": "assistant", "content": reply})
    user_data["first_visit"] = False
    user_data["history"] = conversation_history
    user_data["customer_info"] = customer_info
    users_data[session_id] = user_data
    save_users_data(users_data)
    
    return jsonify({"reply": reply, "customer_info": customer_info})



@app.route("/get-history", methods=["GET"])
def get_history():
    session_id = get_session_id()
    users_data = load_users_data()
    if session_id in users_data:
        user_data = users_data[session_id]
        return jsonify({"history": user_data["history"], "customer_info": user_data["customer_info"], "first_visit": user_data["first_visit"]})
    return jsonify({"history": [], "customer_info": {}, "first_visit": True})

@app.route("/save", methods=["POST"])
def save():
    session_id = get_session_id()
    users_data = load_users_data()
    if session_id in users_data:
        customer_info = users_data[session_id]["customer_info"]
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = "customer_" + session_id + "_" + timestamp + ".json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(customer_info, f, ensure_ascii=False, indent=2)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"})

@app.route("/reset", methods=["POST"])
def reset():
    session_id = get_session_id()
    users_data = load_users_data()
    if session_id in users_data:
        del users_data[session_id]
        save_users_data(users_data)
    return jsonify({"status": "ok"})

@app.route("/set-industry", methods=["POST"])
def set_industry():
    session_id = get_session_id()
    data = request.json
    industry = data.get("industry", "interior_design")
    users_data = load_users_data()
    if session_id not in users_data:
        users_data[session_id] = {"history": [], "customer_info": {}, "first_visit": True}
    users_data[session_id]["industry"] = industry
    save_users_data(users_data)
    return jsonify({"status": "ok", "industry": industry})

@app.route("/api/customers", methods=["GET"])
def get_customers():
    users_data = load_users_data()
    customers = []
    for user_id, user_data in users_data.items():
        customer_info = user_data.get("customer_info", {})
        if customer_info.get("name") or customer_info.get("phone"):
            customers.append({
                "id": user_id,
                "name": customer_info.get("name", ""),
                "phone": customer_info.get("phone", ""),
                "wechat": customer_info.get("wechat", ""),
                "area": customer_info.get("area", ""),
                "budget": customer_info.get("budget", ""),
                "style": customer_info.get("style", ""),
                "layout": customer_info.get("layout", ""),
                "requirements": customer_info.get("requirements", ""),
                "space_info": customer_info.get("space_info", ""),
                "design_needs": customer_info.get("design_needs", ""),
                "timeline": customer_info.get("timeline", ""),
                "special_needs": customer_info.get("special_needs", ""),
                "history": user_data.get("history", []),
                "created_at": user_data.get("created_at", "")
            })
    return jsonify({"customers": customers})

@app.route("/admin", methods=["GET"])
def admin_page():
    return send_from_directory(".", "admin.html")

@app.route("/crm", methods=["GET"])
def crm_page():
    return send_from_directory(".", "crm.html")

@app.route("/workflow", methods=["GET"])
def workflow_page():
    return send_from_directory(".", "workflow.html")

@app.route("/api/generate-quote", methods=["POST"])
def generate_quote():
    data = request.json
    customer_id = data.get("customer_id")
    users_data = load_users_data()
    
    if customer_id not in users_data:
        return jsonify({"error": "Customer not found"}), 404
    
    customer_info = users_data[customer_id].get("customer_info", {})
    
    # 使用 AI 生成报价
    prompt = f"""基于以下客户信息，生成一份专业的室内设计报价单：

客户名称：{customer_info.get('name', '未知')}
预算范围：{customer_info.get('budget', '未知')}
设计风格：{customer_info.get('style', '未知')}
空间信息：{customer_info.get('space_info', '未知')}
设计需求：{customer_info.get('design_needs', '未知')}

请生成包含以下内容的报价单：
1. 项目概述
2. 设计方案说明
3. 费用明细（测量费、设计费、施工监理费等）
4. 总报价金额
5. 有效期（7天）
6. 付款方式（50%+30%+20%）

格式要求：清晰、专业、易于理解"""

    response = get_client().chat.completions.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": prompt}]
    )
    
    quote_content = response.choices[0].message.content
    
    return jsonify({
        "quote": {
            "customer_name": customer_info.get("name", ""),
            "content": quote_content,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    })

@app.route("/api/generate-contract", methods=["POST"])
def generate_contract():
    data = request.json
    customer_id = data.get("customer_id")
    quote_content = data.get("quote_content", "")
    users_data = load_users_data()
    
    if customer_id not in users_data:
        return jsonify({"error": "Customer not found"}), 404
    
    customer_info = users_data[customer_id].get("customer_info", {})
    
    # 使用 AI 生成符合上海市2025版标准的装修合同
    prompt = f"""请根据以下客户信息，生成一份完全符合上海市2025版《室内装饰装修施工合同》标准的装修合同。

【客户信息】
甲方（业主）名称：{customer_info.get('name', '未知')}
甲方联系电话：{customer_info.get('phone', '未知')}
甲方地址：{customer_info.get('area', '未知')}
项目地址：{customer_info.get('area', '未知')}

【项目信息】
设计风格：{customer_info.get('style', '未知')}
空间信息：{customer_info.get('space_info', '未知')}
设计需求：{customer_info.get('design_needs', '未知')}
预算范围：{customer_info.get('budget', '未知')}

【合同生成要求】
请严格按照上海市2025版《室内装饰装修施工合同》示范文本的格式和内容生成合同，包含以下部分：

【合同头部】
- 标题：上海市室内装饰装修施工合同
- 发包人（甲方）信息
- 承包人（乙方）信息
- 法律依据说明

【第一条 工程概况和造价】
- 工程地址、小区名称
- 房型信息
- 施工承包方式：包工包料
- 合同总价：根据预算计算合理的装修总价
- 工期：建议30-60个工作日
- 开工日期和竣工日期（留空供填写）

【第二条 材料供应】
- 材料符合国家强制性标准
- 材料送达现场确认
- 甲方提供材料的使用范围
- 质量责任承担

【第三条 工程质量及验收】
- 按照《住宅装饰装修质量验收规范》验收
- 隐蔽工程验收流程
- 竣工验收流程
- 验收合格后交付

【第四条 安全生产和消防】
- 不改变房屋承重结构
- 安全防护措施
- 消防要求
- 事故责任划分

【第五条 合同付款及结算】
- 付款方式：分阶段付款
  * 合同签订时：30%
  * 水电隐蔽工程验收合格后：30%
  * 泥工、木工基础完工后：30%
  * 竣工验收合格后：10%
- 付款账户信息（留空供填写）
- 发票开具要求
- 结算单签署

【第六条 甲方权利义务】
- 知情权和选择权
- 按时支付款项
- 参加验收
- 提供施工条件
- 协调邻里关系
- 承担装修押金和水电费

【第七条 乙方权利义务】
- 知识产权所有
- 拒绝不安全施工
- 办理开工手续
- 遵守施工规定
- 组织技术交底
- 遵守施工时间
- 指派施工负责人

【第八条 保修和售后】
- 保修期：整体工程2年，防渗漏5年
- 保修范围说明
- 产品保修以产品凭证为准

【第九条 合同的变更和解除】
- 变更需双方协商
- 解除合同的违约金规定
- 逾期支付和开工的处理

【第十条 违约责任】
- 质量不符合的处理
- 逾期交付的赔偿
- 假冒伪劣产品的赔偿
- 甲方延期开工的赔偿
- 甲方未按时付款的赔偿

【第十一条 争议处理方式】
- 协商解决
- 调解
- 仲裁或诉讼

【第十二条 其他约定】
- 留空供双方补充

【第十三条 附则】
- 合同生效条件
- 合同份数

【第十四条 合同附件】
- 附件一：工程项目报价单
- 附件二：甲方提供的主材、设备及预计进场时间汇总表
- 附件三：工程项目变更单
- 附件四：工程质量验收单
- 附件五：工程结算单
- 附件六：工程保修单

【签署部分】
- 甲方签名/盖章、身份证号、代理人、联系方式
- 乙方盖章、统一社会信用代码、签约代表、联系方式
- 签约日期和地址

【重要说明】
1. 合同中间部分只需要显示总价、付款方式等关键信息
2. 报价单详情作为附件一放在合同最后
3. 所有空白处用"___"表示供填写
4. 保持原文本的法律严谨性和完整性
5. 不要删减任何重要条款"""

    response = get_client().chat.completions.create(
        model="claude-sonnet-4-6",
        messages=[{"role": "user", "content": prompt}]
    )
    
    contract_content = response.choices[0].message.content
    
    # 在合同末尾添加报价单作为附件
    full_contract = f"""{contract_content}

{'='*80}
附件一：工程项目报价单
{'='*80}

{quote_content}"""
    
    return jsonify({
        "contract": {
            "customer_name": customer_info.get("name", ""),
            "content": full_contract,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
    })

@app.route("/wechat", methods=["GET", "POST"])
def wechat_callback():
    print(f"WeChat callback received: method={request.method}")
    if request.method == "GET":
        # 验证 URL
        signature = request.args.get("msg_signature")
        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        echostr = request.args.get("echostr")
        print(f"GET params: signature={signature}, timestamp={timestamp}, nonce={nonce}")
        
        crypto = get_wechat_crypto()
        if not crypto:
            print("WeChat crypto not initialized")
            return "Missing WeChat config", 400
        
        try:
            echo_str = crypto.check_signature(signature, timestamp, nonce, echostr)
            print(f"Signature check passed, returning: {echo_str}")
            return echo_str
        except Exception as e:
            print(f"Signature check failed: {e}")
            return f"Signature check failed: {e}", 403
    
    else:
        # 处理消息
        print(f"POST data received, size: {len(request.data)}")
        signature = request.args.get("msg_signature")
        timestamp = request.args.get("timestamp")
        nonce = request.args.get("nonce")
        
        crypto = get_wechat_crypto()
        if not crypto:
            print("Missing WeChat config")
            return "ok"
        
        try:
            msg = crypto.decrypt_message(request.data, signature, timestamp, nonce)
            from wechatpy.enterprise import parse_message
            msg_obj = parse_message(msg)
            print(f"Message type: {msg_obj.type}, content: {msg_obj.content if hasattr(msg_obj, 'content') else 'N/A'}")
            
            # 立即返回 ok，避免超时
            # 在后台处理消息
            if msg_obj.type == "text":
                try:
                    user_id = msg_obj.source
                    content = msg_obj.content
                    print(f"Processing message from {user_id}: {content}")
                    
                    # 调用 AI 获取回复
                    users_data = load_users_data()
                    if user_id not in users_data:
                        users_data[user_id] = {
                            "history": [],
                            "customer_info": {"wechat_user_id": user_id},
                            "first_visit": True,
                            "industry": "interior_design"
                        }
                    
                    user_data = users_data[user_id]
                    conversation_history = user_data["history"]
                    conversation_history.append({"role": "user", "content": content})
                    
                    greeting = ""
                    if not user_data["first_visit"] and user_data["customer_info"].get("name"):
                        name = user_data["customer_info"].get("name", "")
                        surname = name[0] if name else ""
                        greeting = f"\n\n重要：回头客户，姓{surname}。用姓氏敬称问候，回顾需求。"
                    
                    industry = user_data.get("industry", "interior_design")
                    template = PROMPT_TEMPLATES.get(industry, PROMPT_TEMPLATES["interior_design"])
                    system_msg = template["system_prompt"].format(greeting=greeting)
                    
                    messages = [{"role": "system", "content": system_msg}]
                    for msg_item in conversation_history[:-1]:
                        messages.append(msg_item)
                    messages.append({"role": "user", "content": content})
                    
                    print("Calling AI...")
                    response = get_client().chat.completions.create(
                        model=user_data.get("model", "claude-sonnet-4-6"),
                        messages=messages
                    )
                    
                    reply = response.choices[0].message.content
                    print(f"AI reply: {reply[:100]}")
                    
                    # 提取结构化信息
                    import re
                    json_match = re.search(r'\[JSON\](.*?)\[/JSON\]', reply)
                    if json_match:
                        try:
                            info = json.loads(json_match.group(1))
                            for key in ["name", "phone", "wechat", "area", "budget", "style", "layout", 
                                       "requirements", "space_info", "design_needs", "timeline", "special_needs"]:
                                if key in info and info[key]:
                                    customer_info[key] = info[key]
                            user_data["customer_info"] = customer_info
                            reply = reply.replace(json_match.group(0), "").strip()
                        except Exception as e:
                            print(f"JSON parsing error: {e}")
                    
                    conversation_history.append({"role": "assistant", "content": reply})
                    user_data["first_visit"] = False
                    user_data["history"] = conversation_history
                    users_data[user_id] = user_data
                    save_users_data(users_data)
                    
                    # 发送回复
                    client = get_wechat_client()
                    if client:
                        print(f"Sending reply to {user_id}")
                        client.message.send_text(
                            agent_id=os.getenv("WECHAT_AGENT_ID"),
                            user_id=user_id,
                            content=reply
                        )
                        print("Reply sent")
                except Exception as e:
                    print(f"Error processing message: {e}")
            
            return "ok"
        except Exception as e:
            print(f"WeChat error: {e}")
            return "ok"

if __name__ == "__main__":
    print("David室内设计客服启动中...")
    port = int(os.getenv("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=False)
