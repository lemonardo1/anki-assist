# Changelog

## 0.4.0 — 2026-09-05

- Keep stored API keys out of the settings input; preserve or delete them explicitly.
- Show whether `OPENAI_API_KEY` is active without exposing its value.
- Add a menu for copying the entire visible conversation.
- Add `⌘+L`/`Ctrl+L` to focus the active prompt and `Esc` to cancel a request.
- Present friendlier messages for authentication, permission, rate-limit, and server errors.
- Make the card-edit preview scrollable with side-by-side before/after fields.
- Add select-all and clear-all controls for proposed field updates.

## 0.3.0 — 2026-09-04

- Stream follow-up answers into the conversation as they are generated.
- Cancel active streams with a cooperative network cancellation signal.
- Show total token usage when a response finishes.
- Keep up to 20 card conversations and drafts available while the review session remains open.
- Retry the latest question without duplicating its previous answer in model context.

## 0.2.0 — 2026-09-04

- Handle the submit shortcut directly in question editors for more reliable keyboard input.
- Support `⌘+Enter` in both question and card-edit prompts.
- Add inline loading, completion, cancellation, and error status.
- Restore question text after failed or cancelled requests.
- Add a button to copy the latest AI answer.
- Safely render basic bold and inline-code formatting in conversations.
- Ignore stale background responses after cancellation or card changes.

## 0.1.1 — 2026-09-03

- Fix `⌘+Enter` question submission on macOS by using Qt's platform-portable Control mapping.

## 0.1.0 — 2026-09-03

- Add a right-side AI assistant during Anki reviews.
- Support card-aware follow-up conversations.
- Add prompt template management for questions and edits.
- Preview and selectively apply AI-generated field updates.
- Preserve active review timing after a card edit.
- Send the initial question from the main composer and follow-ups with `⌘+Enter`.
