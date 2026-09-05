# Anki Assist AI 설정

설정은 애드온의 **설정** 버튼을 이용하는 것을 권장합니다.

- `api_key`: OpenAI API 키. Anki의 로컬 애드온 설정(`meta.json`)에 저장됩니다. 설정창은 저장된 값을 다시 표시하지 않으며, 변경하거나 삭제할 때만 입력합니다. `OPENAI_API_KEY` 환경 변수가 있으면 환경 변수 값이 우선합니다.
- `model`: Responses API에서 사용할 모델 이름입니다.
- `max_output_tokens`: 한 응답의 최대 출력 토큰 수입니다.
- `show_only_in_review`: 리뷰 화면에서만 사이드바를 표시합니다.
- `templates`: 질문(`ask`) 또는 카드 수정(`edit`) 프롬프트 템플릿입니다.
