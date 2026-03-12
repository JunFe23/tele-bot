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
GEMINI_KEY = os.getenv("GEMINI_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_KEY}"

# 카카오톡 파싱을 위한 이름 (보안을 위해 환경변수 처리. 로컬 .env 에 KAKAOTALK_MY_NAME, KAKAOTALK_FRIEND_NAME 설정)
MY_NAME = os.getenv("MY_NAME", "나")
FRIEND_NAME = os.getenv("FRIEND_NAME", "친구")

# 1. 로컬 카카오톡 대화 기록 불러오기 (RAG 데이터베이스 구축)
# MY_NAME -> FRIEND_NAME 순서와 FRIEND_NAME -> MY_NAME 순서 모두 수집해
# 친구의 말투(t_msg 또는 u_msg)를 최대한 많이 학습 데이터로 확보
qa_pairs = []
chat_files = [f for f in os.listdir('.') if f.endswith('.txt')]

for file_name in chat_files:
    try:
        with open(file_name, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            for i in range(1, len(lines)):
                prev, curr = lines[i-1], lines[i]
                noise = ["사진", "이모티콘", "동영상", "샵검색"]
                # 케이스 1: 내가 말하고 -> 친구가 대답 (기존)
                if f"{MY_NAME} :" in prev and f"{FRIEND_NAME} :" in curr:
                    u_msg = prev.split(" : ", 1)[-1].strip()
                    t_msg = curr.split(" : ", 1)[-1].strip()
                    if not any(x in t_msg for x in noise):
                        qa_pairs.append({"u": u_msg, "t": t_msg})
                # 케이스 2: 친구가 먼저 말하고 -> 내가 대답 (친구 선톡 말투 수집)
                elif f"{FRIEND_NAME} :" in prev and f"{MY_NAME} :" in curr:
                    t_msg = prev.split(" : ", 1)[-1].strip()  # 친구 말 = 학습 대상
                    u_msg = curr.split(" : ", 1)[-1].strip()
                    if not any(x in t_msg for x in noise):
                        qa_pairs.append({"u": u_msg, "t": t_msg})
    except: continue

print(f"✅ 카카오톡 파싱 완료: {len(qa_pairs)}개의 대화 쌍 로드됨", flush=True)

def get_context(user_input, all_pairs):
    # 입력이 짧아도 (예: ㅎㅇ, ㄹㅌ?) 통째로 검색
    raw = user_input.strip()
    keywords = [w for w in raw.split() if len(w) >= 1]
    if not keywords:
        keywords = [raw]

    relevant = []
    for p in all_pairs:
        if any(k in p['u'] for k in keywords):
            relevant.append(f"\ub098: {p['u']}\n\uce5c\uad6c: {p['t']}")

    # 최신 15개만 쭬집
    if len(relevant) > 15:
        relevant = relevant[-15:]

    # 부족할 경우 최신 대화 보충
    if len(relevant) < 10:
        needed = 10 - len(relevant)
        recent = [f"\ub098: {p['u']}\n\uce5c\uad6c: {p['t']}" for p in all_pairs[-needed:]
                  if f"\ub098: {p['u']}\n\uce5c\uad6c: {p['t']}" not in relevant]
        relevant.extend(recent)

    return "\n".join(relevant)

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
        print(f"🔍 [RAG Context] 매칭된 과거 대화 길이: {len(relevant_context)}자", flush=True)

        # --- Gemini Persona Prompt ---
        history_context = "\n".join(session_history[-6:])  # 최근 6턴만

        prompt = f"""아래 [카톡 대화 예시]는 내가 매일 카톡하는 30대 남자 친구의 실제 대화 데이터다.
나의 [최근 말] ("대화 흐름" 맨 마지막 "나: " 라인)에 쳤카오톡 친구로서 답장을 보내라.

[금지 사항]
- 전 세계 AI/챗봇/쥬스누마크 굴지
- 존댓말 절대 금지 ("왔어요", "감사합니다" 등)
- [대화 흐름]에 이미 있는 문구를 그대로 도복하거나 어구 반복 금지
- 2문장 이상 금지

[대화 스타일]
- [카톡 대화 예시]의 말투("~맨", "~쓰", "~미", "ㅋㅋㅋ" 등)를 자연스럽게 써라
- "뭐하냐맨", "너나만 툭툭 던져라" 주식으로 짧고 무심하게

[카톡 대화 예시 - 이 말투채 참고해 답해라]
{relevant_context}

[대화 흐름]
{history_context}

나: {message.text}
친구:"""

        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.8,
                "topP": 0.95,
                "maxOutputTokens": 100,
                "stopSequences": ["나:", "친구:", "\n\n", "System:"]
            }
        }

        response = requests.post(GEMINI_URL, json=payload, timeout=60).json()
        
        # Gemini 응답 파싱
        try:
            reply = response['candidates'][0]['content']['parts'][0]['text'].strip()
        except (KeyError, IndexError):
            reply = ""
        

        # [물리적 필터] 한글, 숫자, 자음(ㅋ,ㅎ,ㅅ), 영어, 기본 문장부호(!?~,.) 허용. 카카오톡 이모티콘 같은 건 삭제
        reply = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s!?~,.]', '', reply).strip()
        
        # 만약 필터링 후 내용이 거의 없거나, "와", "와 ㅋㅋㅋ" 처럼 의미없는 짧은 반복만 생성되었다면 예외처리
        if not reply or len(reply) < 2 or "와 와 와" in reply or "ㅋㅋㅋ ㅋㅋㅋ ㅋㅋㅋ" in reply:
            fallback_replies = ["뭐하미 ㅋㅋㅋ", "ㅇㅇ", "그래서어쩔", "ㄹㅇㅋㅋ"]
            reply = random.choice(fallback_replies)
        elif len(reply) > 60:
            reply = reply[:60]

        # 필터링 후 세션에 저장 (오염된 응답이 다음 프롬프트를 오염시키지 않도록)
        session_history.append(f"친구: {reply}")
        if len(session_history) > 12:
            session_history.pop(0)

        print(f"🤖 친구: {reply}", flush=True)
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
                prompt = """당신은 30대 남자 '친구(상대방)'이다.
사용자에게 아무 이유 없이 빈둥거리면서 심심하다고 선톡(먼저 말 걸기)을 하나 보내봐.
인사말 쓰지 말고, 뜬금없는 질문을 던지거나 이상한 소리를 해. 무조건 반말로 짧게 쓰고 ㅋㅋㅋ나 ~쓰, ~맨 같은 말투 꼭 써라.

[예시]
뭐하심 ㅋㅋㅋ
롤 ㄱ? 심심맨
밥먹음? 배고프미

선톡:"""
                
                payload = {
                    "contents": [{
                        "parts": [{"text": prompt}]
                    }],
                    "generationConfig": {
                        "temperature": 0.9,
                        "topP": 0.95,
                        "maxOutputTokens": 60,
                        "stopSequences": ["\n\n"]
                    }
                }

                response = requests.post(GEMINI_URL, json=payload, timeout=60).json()
                try:
                    reply = response['candidates'][0]['content']['parts'][0]['text'].strip()
                except (KeyError, IndexError):
                    reply = ""
                
                # 정규식 필터링
                reply = re.sub(r'[^가-힣ㄱ-ㅎㅏ-ㅣa-zA-Z0-9\s!?~,.]', '', reply).strip()
                
                if reply and len(reply) <= 25:
                    print(f"🔔 선톡 발송: {reply}", flush=True)
                    bot.send_message(ALLOWED_USER, reply)
                    
                    session_history.append(f"친구: {reply}")
                    if len(session_history) > 10:
                        session_history.pop(0)

            except Exception as e:
                print(f"⚠️ 선톡 에러: {e}")

# 선톡 스레드 백그라운드 실행
threading.Thread(target=proactive_messaging, daemon=True).start()

print("🚀 봇 가동 시작...")
bot.infinity_polling()
