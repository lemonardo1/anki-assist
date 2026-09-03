# Security Policy

## API key storage

Anki Assist AI can read `OPENAI_API_KEY` from the environment. When a key is entered in the add-on settings, Anki stores it in the local add-on `meta.json`. That file is excluded from Git, but it may be plaintext on disk.

Never attach `meta.json` to an issue or commit it to a repository. If a key is exposed, revoke it immediately in the OpenAI Platform dashboard and create a replacement.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability that could expose credentials or private card data. Contact the repository owner privately through their GitHub profile and include only the minimum information needed to reproduce the issue.
