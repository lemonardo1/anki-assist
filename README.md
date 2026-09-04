# Anki Assist AI

Anki 리뷰 화면 오른쪽에서 현재 카드에 대해 AI 후속 질문을 하거나, 필드별 수정안을 검토한 뒤 적용하는 Anki 애드온입니다.

> AI-powered sidebar for asking follow-up questions and safely editing cards while reviewing in Anki.

[![Tests](https://github.com/lemonardo1/anki-assist/actions/workflows/tests.yml/badge.svg)](https://github.com/lemonardo1/anki-assist/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 기능

- 현재 카드의 노트 유형과 필드를 자동으로 AI 문맥에 포함
- 카드별 후속 대화
- 질문용/수정용 프롬프트 템플릿 추가·수정·삭제
- AI 카드 수정안을 필드별로 미리보고 선택 적용
- Anki 실행 취소 기록을 남기는 카드 업데이트
- OpenAI 요청을 백그라운드에서 실행
- 진행 상태 및 요청 취소, 실패한 질문 내용 복원
- 마지막 AI 답변 복사와 안전한 기본 서식 표시

## 설치

1. [Releases](https://github.com/lemonardo1/anki-assist/releases)에서 최신 `anki-assist-ai.ankiaddon` 파일을 받아 더블 클릭하거나 Anki의 **도구 → 애드온 → 파일에서 설치**로 엽니다.
2. Anki를 재시작합니다.
3. 리뷰 화면 오른쪽의 **Anki Assist**에서 **설정**을 누릅니다.
4. OpenAI API 키와 사용할 모델을 입력합니다.

개발 중에는 이 저장소를 Anki의 `addons21/anki_assist_ai`에 심볼릭 링크해도 됩니다.

현재 Anki 25.09 이상을 지원하며 macOS의 Anki 25.09.4에서 검증했습니다.

## 사용

- **후속 질문**: 첫 질문은 큰 입력 영역에 바로 입력하거나 템플릿을 선택합니다. 첫 답변 뒤에는 아래 입력창에서 대화를 이어갑니다. 두 입력창 모두 `⌘+Enter`로 전송할 수 있습니다.
- **카드 수정**: 수정 지시를 입력하고 수정안을 생성한 뒤, 미리보기 창에서 적용할 필드를 선택합니다.
- **키보드**: 질문과 카드 수정 모두 `⌘+Enter`로 실행합니다. Windows/Linux에서는 `Ctrl+Enter`를 사용합니다.
- **템플릿**: 사이드바 상단의 템플릿 버튼에서 질문/수정 프롬프트를 관리합니다.
- 사이드바가 닫혔다면 **도구 → Anki Assist 사이드바** 또는 `Ctrl+Shift+A`로 다시 엽니다.

## 개인정보 및 비용

현재 카드 필드, 질문, 해당 카드의 대화 이력이 OpenAI API로 전송됩니다. 요청에는 `store: false`가 설정됩니다. API 사용료는 입력한 OpenAI 계정에 청구됩니다. API 키는 Anki 프로필의 애드온 설정에 평문으로 저장될 수 있으므로 공유 컴퓨터에서는 환경 변수 `OPENAI_API_KEY` 사용을 권장합니다.

## 개발 및 기여

```bash
python3 -m unittest discover -v
```

버그 신고와 Pull Request를 환영합니다. 자세한 내용은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.
