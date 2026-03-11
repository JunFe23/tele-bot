# AI Persona Clone Bot

이 프로젝트는 카카오톡 대화 기록을 바탕으로 특정 인물(오랜 지인)의 **페르소나(말투, 성격, 반응 방식)**를 완벽하게 모사하는 텔레그램 AI 챗봇입니다.

수천 건의 실제 카카오톡 대화 기록(RAG)과 LLM의 Few-Shot Prompting 기법을 결합하여, AI 특유의 기계적인 친절함을 제거하고 실제 친구와 대화하는 듯한 날것의 시니컬한 반응을 구현했습니다.

## ✨ 주요 기능
*   **완벽한 페르소나 복제 (Few-Shot & RAG)**
    - 로컬에 저장된 카카오톡 대화방 기록(`Talk_*.txt`)을 봇 실행 시 메모리에 로드합니다.
    - 사용자가 질문을 던지면, 과거 대화에서 가장 유사한 키워드의 대화를 검색하여 프롬프트에 주입합니다 (RAG).
    - `gemma2:9b` 모델의 강력한 추론 능력을 유지하면서도, 철저하게 주입된 페르소나 제약 규칙("반말 사용", "친절함 금지", "ㅋㅋㅋ/~맨 필수 사용" 등)에 따라 답변을 짧고 유쾌하게 변환합니다.
*   **다턴(Multi-turn) 문맥 유지**
    - 최근 10개의 대화 기록을 세션에 저장하여, 질문이 꼬리를 물어도 맥락을 이해하고 자연스럽게 대화를 이어갑니다.
*   **물리적 출력 필터링 및 앵무새 방지**
    - AI가 종종 고장나서 의미 없는 문자를 반복하거나 영어/이모티콘을 섞어 쓰는 것을 방지하기 위해 정규식 필터와 강력한 `repeat_penalty`가 적용되어 있습니다.
*   **랜덤 선톡 기능 (Proactive Messaging)**
    - 봇이 수동적으로 묻는 말에만 대답하는 것이 아니라, 일정 확률(시간당 10%)로 사용자에게 먼저 뜬금없는 카톡(선톡)을 보냅니다. (새벽 시간대 제외)

## 🛠 기술 스택
*   **Language**: Python 3.11
*   **AI Model**: [Ollama](https://ollama.com/) 로컬 컨테이너 (Base Model: `gemma2:9b`)
*   **Bot Framework**: `pyTelegramBotAPI`
*   **Infrastructure**: Docker, Docker Compose

## 🚀 실행 방법 (로컬 환경)

### 1. 사전 준비 (Prerequisites)
- [Docker & Docker Compose](https://www.docker.com/) 설치
- [Ollama](https://ollama.com/) 설치 및 `gemma2:9b` 모델 다운로드 (`ollama pull gemma2:9b`)
- Telegram Bot API Token 발급 (@BotFather)
- 본인의 Telegram Chat ID (봇이 응답할 대상)
- 카카오톡 대화 내보내기로 추출한 텍스트 파일 (`Talk_*.txt`)들을 프로젝트 루트 디렉토리에 위치

### 2. 환경 변수 설정
로컬 또는 서버 환경 변수에 다음 값을 세팅합니다. (또는 `.env` 사용 가능)
```bash
export OPENCLAW_TELEGRAM_TOKEN="your_telegram_bot_token"
export OPENCLAW_TELEGRAM_ALLOWED_USERS="your_telegram_chat_id"
export KAKAOTALK_MY_NAME="카톡대화상_내이름"
export KAKAOTALK_FRIEND_NAME="카톡대화상_모사할친구이름"
```

### 3. 도커 컨테이너 빌드 및 실행
```bash
# 컨테이너 빌드 및 백그라운드 실행
docker compose up -d --build

# 실행 로그 확인
docker compose logs -f
```

## ⚠️ 보안 및 개인정보 관리
- 카카오톡 대화 내역(`Talk_*.txt`)과 API 토큰이 담긴 환경 변수 파일(`.env`)은 깃허브에 절대 업로드되지 않도록 `.gitignore`에 의해 차단되어 있습니다.
- 모든 API 요청은 로컬 환경(호스트 컴퓨터의 Ollama)에서만 이루어지며 외부 클라우드로 대화 데이터가 유출되지 않습니다.
