# Агент проверки требований

Статическая проверка документа требований по ISO/IEC/IEEE 29148:2018 и IEEE 830. Модель: Gemini (`gemini-2.5-flash` по умолчанию).

## Ключ
1. Получите бесплатный ключ: https://aistudio.google.com/apikey
2. `cp .env.example .env` и впишите ключ в `GEMINI_API_KEY`.

## Запуск
```
pip install -r requirements.txt
python agent.py docs/requirements.md report.md
```
Вход: `.md`, `.txt`, `.pdf`, `.docx`. Отчёт ляжет по второму пути (например `report.md`).

Промпт агента — `prompt.md`.
