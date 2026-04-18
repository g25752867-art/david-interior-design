cat > ~/desktop/ai-test/app.py << 'EOF'
import os
import json
import time
import uuid
from flask import Flask, request, jsonify, send_from_directory, session
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)
app.secret_key = "david-interior-design-secret-key-12345"

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("API_BASE_URL")
)

USERS_FILE = "users_data.json"

def load_users_data():
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_users_data(users_data):
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
        user_content = [
            {
                "type": "text",
                "text": user_message if user_message else "请分析这张图片的设计风格。"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": image_data
                }
            }
        ]
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
    
    system_msg = "你是David室内设计客服助理。" + greeting + 
"\n\n【流程】第一步：上门测量500元（不退）。第二步：免费方案（基础平面图+参考图）。第三步：签合同。第四步：分阶段付款（50%+30%+20%）。\n\n【图片】分析风格、颜色、材质、氛围。用专业设计语言。\n\n【职责】热情接待，逐步了解需求，不重复问，上传图片时分析，引导留联系方式，语气专业亲切。\n\n【提取信息】用[JSON]{...}[/JSON]包含：name、phone、wechat、area、budget、style、layout、requirements"
    
    messages = [{"role": "system", "content": system_msg}]
    
    for msg in conversation_history[:-1]:
        messages.append(msg)
    
    messages.append({"role": "user", "content": user_content})
    
    response = client.chat.completions.create(
        model="claude-sonnet-4-6",
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

if __name__ == "__main__":
    print("David室内设计客服启动中...")
    app.run(port=5001, debug=False)
EOF
