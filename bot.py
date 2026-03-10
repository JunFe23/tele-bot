import os
import telebot
import requests
import json
import time
import re

TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER = int(os.getenv("ALLOWED_USER"))
OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

# 1. 데이터 로딩 및 정제
qa_pairs = []
chat_files = [f for f in os.listdir('.') if f.endswith('.txt')]

for file_name in chat_files:
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i in range(1, len(lines)):
                if "김준철 :" in lines[i-1] and "망원동 티모 :" in lines[i]:
                    u_msg = lines[i-1].split(" : ")[-1].strip()
                    t_msg = lines[i].split(" : ")[-1].strip()
                    # 노이즈(이모티콘, 사진 등)가 포함된 문장은 학습 데이터에서 제외
                    if not any(x in t_msg for x in ["사진", "이모티콘", "동영상", "샵검색"]):
                        qa_pairs.append({"u": u_msg, "t": t_msg})
    except: continue

def get_context(user_input, all_pairs):
    # 키워드 매칭 검색
    relevant = [f"나: {p['u']}\n티모: {p['t']}" for p in all_pairs if user_input in p['u']]
    # 데이터가 부족하면 최신 15개로 보충
    if len(relevant) < 15:
        relevant.extend([f"나: {p['u']}\n티모: {p['t']}" for p in all_pairs[-15:]])
    return "\n".join(relevant[-15:])

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda message: message.from_user.id == ALLOWED_USER)
def handle_message(message):
    try:
        print(f"💬 나: {message.text}", flush=True)
        bot.send_chat_action(message.chat.id, 'typing')
        
        relevant_context = get_context(message.text, qa_pairs)

        # [지침] 모델에게 선택권을 주지 않는 단호한 프롬프트
        prompt = f"""
당신은 한국인 남자 '티모'다. 아래 [데이터]의 말투를 100% 복사한다.
- 이모티콘 사용 시 즉시 종료.
- 10자 이내로만 말한다.
- 무조건 반말한다.

[데이터]
{relevant_context}

나: {message.text}
티모:"""

        payload = {
            "model": "gemma2:9b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.3,  # 0에 가까울수록 데이터와 똑같이 말함 (창의성 제거)
                "top_p": 0.1,
                "stop": ["나:", "\n", "이 대화", "(", "!", "."] # 설명하려 하면 바로 차단
            }
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        reply = response.json().get('response', '').strip()
        
        # [물리적 필터] 한글, 숫자, 자음(ㅋ,ㅎ,ㅅ), 공백 외 모든 문자(이모티콘 포함) 강제 삭제
        reply = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣ0-9\s]', '', reply)
        
        # 만약 필터링 후 아무것도 안 남거나 AI 냄새가 나면 재환이 형 리액션으로 덮어쓰기
        if not reply or len(reply) > 15:
            reply = "ㄹㅇ"

        print(f"🤖 티모: {reply}", flush=True)
        bot.send_message(message.chat.id, reply)

    except Exception as e:
        print(f"⚠️ 에러: {e}")

bot.infinity_polling()
