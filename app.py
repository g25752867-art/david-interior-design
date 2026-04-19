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

【信息提取】
分析对话中的客户信息，用以下格式提取：
[JSON]{{"name":"","phone":"","wechat":"","area":"","budget":"","style":"","layout":"","requirements":""}}[/JSON]

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
            customer_info.update(info)
            user_data["customer_info"] = customer_info
            reply = reply.replace(json_match.group(0), "").strip()
        except:
            pass
    
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
                    conversation_history.append({"role": "assistant", "content": reply})
                    user_data["first_visit"] = False
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
