import os
import time
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CORP_ID = "ww1d13df7039a84c20"
AGENT_ID = "1000002"
SECRET = "uBQLejFl687RzMt95odGp4ylHGqMGtvkJoeaBs0gWOY"

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("API_BASE_URL")
)

def get_access_token():
    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=" + CORP_ID + "&corpsecret=" + SECRET
    response = requests.get(url)
    return response.json().get("access_token")

def ai_reply(message):
    response = client.chat.completions.create(
        model="claude-sonnet-4-6",
        messages=[
            {
                "role": "system",
                "content": "你是David室内设计的客服助理。热情回复客户，提取需求，告知安排设计师跟进，语气专业亲切，回复简洁。"
            },
            {"role": "user", "content": message}
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

def send_to_me(content):
    token = get_access_token()
    url = "https://qyapi.weixin.qq.com/cgi-bin/message/send?access_token=" + token
    data = {
        "touser": "@all",
        "msgtype": "text",
        "agentid": AGENT_ID,
        "text": {"content": content}
    }
    result = requests.post(url, json=data)
    return result.json()

# 测试：发一条消息给自己
print("测试发送消息给自己...")
result = send_to_me("🤖 David AI客服系统已启动！这是一条测试消息。")
print("结果：", result)

