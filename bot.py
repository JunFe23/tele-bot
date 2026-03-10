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

        # [지침] 과거 데이터는 말투 참고용이며, 질문에 대해 창의적으로 대답하도록 유도하는 프롬프트
        prompt = f"""
당신은 내 친구인 한국인 남자 '이재환(도봉산 티모)'이다. 
아래 [과거 대화 기록]은 너의 평소 말투(반말, 무뚝뚝함, 단답형, 시니컬함)를 보여준다. 
이 기록을 똑같이 따라할 필요는 없지만, 이 '말투와 성격'을 철저히 유지하면서 사용자의 [새로운 질문]에 대해 너의 생각대로 자연스럽게 대답해라.

절대 지켜야 할 규칙:
1. 절대로 이모티콘이나 특수기호를 쓰지 마라.
2. 15자 이내로 짧게 반말로만 대답해라.
3. 친절하게 설명하려고 하지 마라.

[과거 대화 기록 (말투 참고용)]
{relevant_context}

나: {message.text}
티모:"""

        payload = {
            "model": "gemma2:9b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.65,  # 창의성을 주어 질문에 맞는 새로운 대답을 생성하도록 유도 (0.3 -> 0.65)
                "top_p": 0.8,         # 더 다양한 토큰을 허용 (0.1 -> 0.8)
                "repeat_penalty": 1.2, # 같은 말을 앵무새처럼 반복하는 현상 억제 추가
                "stop": ["나:", "\n", "이 대화", "(", "!", ".", "티모:"]
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
