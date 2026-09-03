# Contributing

Anki Assist AI에 관심을 가져주셔서 감사합니다.

## 개발 환경

1. 저장소를 clone합니다.
2. 프로젝트 폴더를 Anki 프로필의 `addons21/anki_assist_ai`에 심볼릭 링크합니다.
3. Anki를 재시작해 변경 사항을 확인합니다.
4. 제출 전 테스트를 실행합니다.

```bash
python3 -m unittest discover -v
python3 -m compileall -q .
```

## Pull Request

- 한 PR에는 관련된 변경만 포함해 주세요.
- UI 변경은 가능하면 전후 스크린샷을 첨부해 주세요.
- 새 동작에는 가능한 범위에서 테스트를 추가해 주세요.
- `meta.json`, API 키, 개인 카드 데이터는 절대 commit하지 마세요.

## 버그 신고

Anki 버전, 운영체제, 재현 단계, 오류의 **Copy Debug Info**를 포함해 주세요. 디버그 정보에 개인 카드 내용이나 토큰이 포함되어 있지 않은지 먼저 확인해 주세요.
