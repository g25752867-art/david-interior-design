import os
import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CORP_ID = os.getenv("WECHAT_CORP_ID")
AGENT_ID = os.getenv("WECHAT_AGENT_ID")
SECRET = os.getenv("WECHAT_SECRET")

client = OpenAI(
    api_key=os.getenv("API_KEY"),
    base_url=os.getenv("API_BASE_URL")
)

def get_access_token():
    url = "https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid=" + CORP_ID + "&corpsecret=" + SECRET
    response = requests.get(url)
    data = response.json()
    return data.get("access_token")

def ai_reply(customer_message):
    response = client.chat.completions.create(
        model="claude-sonnet-4-6",
        messages=[
            {
                "role": "system",
                "content": "你是David室内设计的客服助理。热情回复客户，提取需求，告知安排设计师跟进，语气专业亲切。"
            },
            {"role": "user", "content": customer_message}
        ]
    )
    return response.choices[0].message.content

customer_msg = "你好，我想装修100平米的新房，预算15万，喜欢北欧风格"
print("客户消息：", customer_msg)
print("\n正在生成AI回复...")
reply = ai_reply(customer_msg)
print("\nAI回复：")
print(reply)

token = get_access_token()
if token:
    print("\n企业微信连接成功")
else:
    print("\n企业微信连接失败，检查凭证")