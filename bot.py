import os
import telebot
import requests
import json
import time
import re
import random
import threading
from datetime import datetime

TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_USER = int(os.getenv("ALLOWED_USER"))
OLLAMA_URL = "http://host.docker.internal:11434/api/generate"

# 1. 로컬 카카오톡 대화 기록 불러오기 (RAG 데이터베이스 구축)
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
    # 사용자의 질문과 관련된 과거 대화 검색 (키워드 매칭)
    relevant = [f"나: {p['u']}\n이재환: {p['t']}" for p in all_pairs if user_input in p['u']]
    # 데이터가 부족하면 가장 최근 대화 15개로 보충
    if len(relevant) < 15:
        relevant.extend([f"나: {p['u']}\n이재환: {p['t']}" for p in all_pairs[-15:]])
    return "\n".join(relevant[-15:])

# 다턴 대화 컨텍스트 메모리 (최대 10개 유지)
session_history = []

bot = telebot.TeleBot(TOKEN)

@bot.message_handler(func=lambda message: message.from_user.id == ALLOWED_USER)
def handle_message(message):
    try:
        print(f"💬 나: {message.text}", flush=True)
        bot.send_chat_action(message.chat.id, 'typing')
        # 세션 메모리 관리
        session_history.append(f"나: {message.text}")
        if len(session_history) > 10:
            session_history.pop(0)

        history_context = "\n".join(session_history)

        # 과거 실제 대화 기록 검색
        relevant_context = get_context(message.text, qa_pairs)

        # Few-Shot 프롬프팅 + RAG: 기본 Gemma 모델에 실제 데이터와 강력한 제약 걸기
        prompt = f"""[System]
당신은 AI나 어시스턴트가 절대 아니다. 당신의 정체성은 30대 한국인 남자 '이재환(도봉산 티모)'이다.
나(사용자)는 당신의 불알친구 '준철'이다.

[절대 규칙]
1. 아래 제시된 [과거 실제 대화 기록]의 말투, 단어 선택, 분위기를 100% 완벽하게 복사해라.
2. 기계처럼 친절하게 설명하거나 도와주려고 하지 마라. 친구끼리 카톡하듯이 무심하고 짧게 툭툭 던져라.
3. 절대 존댓말을 쓰지 마라. 100% 반말만 해라.
4. "ㅋㅋㅋ"를 자주 쓰고, 기분이 좋거나 장난칠 때 "~맨", "~쓰", "~미" 같은 어미를 섞어 써라.
5. 무조건 1~2문장으로 끝내라. 지식이나 코딩 질문이 들어와도 정답을 아주 건방지고 짧게 대답해라.

[과거 실제 대화 기록 (말투 완벽 복사할 것)]
{relevant_context}

[현재 직전 대화 흐름]
{history_context}

나: {message.text}
이재환:"""

        payload = {
            "model": "gemma2:9b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.65, # 실제 데이터에 좀 더 의존하도록 살짝 낮춤
                "top_p": 0.9,
                "repeat_penalty": 1.25,
                "stop": ["나:", "이재환:", "\n\n", "System:"]
            }
        }

        response = requests.post(OLLAMA_URL, json=payload, timeout=60)
        reply = response.json().get('response', '').strip()
        
        session_history.append(f"이재환: {reply}")
        
        # [물리적 필터] 한글, 숫자, 자음(ㅋ,ㅎ,ㅅ), 영어, 기본 문장부호(!?~,.) 허용. 카카오톡 이모티콘 같은 건 삭제
        reply = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s!?~,.]', '', reply).strip()
        
        # 만약 필터링 후 내용이 거의 없거나, "와", "와 ㅋㅋㅋ" 처럼 의미없는 짧은 반복만 생성되었다면 예외처리
        if not reply or len(reply) < 2 or "와 와 와" in reply or "ㅋㅋㅋ ㅋㅋㅋ ㅋㅋㅋ" in reply:
            fallback_replies = ["뭐하미 ㅋㅋㅋ", "ㅇㅇ", "그래서어쩔", "ㄹㅇㅋㅋ"]
            reply = random.choice(fallback_replies)
        elif len(reply) > 40:
            # 티모는 길게 말하지 않음
            reply = reply[:40] + "..."

        print(f"🤖 티모: {reply}", flush=True)
        bot.send_message(message.chat.id, reply)

    except Exception as e:
        print(f"⚠️ 에러: {e}")

# 선톡(Proactive Messaging) 기능 스레드
def proactive_messaging():
    while True:
        # 1시간(3600초)마다 선톡 여부 확인 (테스트를 위해 주기는 자유롭게 조절 가능)
        time.sleep(3600)
        
        now = datetime.now()
        # 새벽 시간(밤 12시 ~ 아침 8시)에는 선톡 금지
        if 0 <= now.hour <= 8:
            continue
            
        # 10% 확률로 선톡 시도 (확률 조절 가능)
        if random.random() < 0.10:
            try:
                print("🔄 선톡 생성 시도 중...", flush=True)
                # 선톡용 명령어
                prompt = """당신은 30대 남자 '망원동 이재환(도봉산 티모)'이다.
사용자에게 아무 이유 없이 빈둥거리면서 심심하다고 선톡(먼저 말 걸기)을 하나 보내봐.
인사말 쓰지 말고, 뜬금없는 질문을 던지거나 이상한 소리를 해. 무조건 반말로 짧게 쓰고 ㅋㅋㅋ나 ~쓰, ~맨 같은 말투 꼭 써라.

[예시]
뭐하심 ㅋㅋㅋ
롤 ㄱ? 심심맨
밥먹음? 배고프미

선톡:"""
                
                payload = {
                    "model": "gemma2:9b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                         "temperature": 0.8,
                         "repeat_penalty": 1.15,
                         "stop": ["\n\n"]
                    }
                }

                response = requests.post(OLLAMA_URL, json=payload, timeout=60)
                reply = response.json().get('response', '').strip()
                
                # 정규식 필터링
                reply = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s!?~,.]', '', reply).strip()
                
                if reply and len(reply) <= 25:
                    print(f"🔔 선톡 발송: {reply}", flush=True)
                    bot.send_message(ALLOWED_USER, reply)
                    
                    session_history.append(f"이재환: {reply}")
                    if len(session_history) > 10:
                        session_history.pop(0)

            except Exception as e:
                print(f"⚠️ 선톡 에러: {e}")

# 선톡 스레드 백그라운드 실행
threading.Thread(target=proactive_messaging, daemon=True).start()

print("🚀 티모봇 가동 시작...")
bot.infinity_polling()
