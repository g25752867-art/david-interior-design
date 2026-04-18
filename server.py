import os
import requests
import hashlib
import xml.etree.ElementTree as ET
from flask import Flask, request
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

app = Flask(__name__)

CORP_ID = "ww1d13df7039a84c20"
AGENT_ID = "1000002"
SECRET = "uBQLejFl687RzMt95odGp4ylHGqMGtvkJoeaBs0gWOY"
TOKEN = "david123"

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("API_BASE_URL")
)

def get_access_token():
    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=" + CORP_ID + "&corpsecret=" + SECRET
    response = requests.get(url)
    return response.json().get("access_token")

def ai_reply(customer_message):
    response = client.chat.completions.create(
        model="claude-sonnet-4-6",
        messages=[
            {
                "role": "system",
                "content": "你是David室内设计的客服助理。热情回复客户，提取需求，告知安排设计师跟进，语气专业亲切，回复简洁。"
            },
            {"role": "user", "content": customer_message}
        ]
    )
    return response.choices[0].message.content

def send_message(user_id, content):
    token = get_access_token()
    url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=" + token
    data = {
        "touser": user_id,
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": content}
    }
    requests.post(url, json=data)

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        msg_signature = request.args.get("msg_signature", "")
        timestamp = request.args.get("timestamp", "")
        nonce = request.args.get("nonce", "")
        echostr = request.args.get("echostr", "")
        
        # 验证签名
        params = sorted([TOKEN, timestamp, nonce, echostr])
        signature = hashlib.sha1("".join(params).encode()).hexdigest()
        
        if signature == msg_signature:
            return echostr
        return "验证失败", 403

    try:
        xml_data = request.data
        root = ET.fromstring(xml_data)
        msg_type = root.find("MsgType").text
        from_user = root.find("FromUserName").text

        if msg_type == "text":
            content = root.find("Content").text
            print(f"收到消息：{content}")
            reply = ai_reply(content)
            print(f"AI回复：{reply}")
            send_message(from_user, reply)

        return "success"
    except Exception as e:
        print(f"错误：{e}")
        return "success"

if __name__ == "__main__":
    print("服务器启动中...")
    app.run(port=5000)