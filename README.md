# ИИ-агент проверки требований

Консольный агент для статической проверки документов с программными требованиями по критериям ISO/IEC/IEEE 29148:2018 и IEEE Std 830-1998.

## Поддерживаемые форматы

- Markdown (`.md`)
- PDF (`.pdf`)
- TXT (`.txt`)
- DOCX (`.docx`), включая таблицы

## Требования

- Python 3.11 или новее
- Gemini API key

## Установка

### Windows PowerShell

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

### Linux/macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Настройка Gemini

1. Получите API-ключ: [Google AI Studio](https://aistudio.google.com/apikey).
2. Откройте файл `.env`.
3. Укажите ключ:

```env
GEMINI_API_KEY=ваш_ключ
GEMINI_MODEL=gemini-2.5-flash
```

Файл `.env` не добавляется в Git.

## Запуск

```bash
python main.py --input docs/requirements.md --output output/report.md
```

Короткая форма:

```bash
python main.py -i docs/requirements.md -o output/report.md
```

Старый формат запуска также поддерживается:

```bash
python agent.py docs/requirements.md output/report.md
```

После завершения отчёт будет сохранён по пути, указанному в `--output`.

## Дополнительные параметры

```bash
python main.py --help
```

Выбор модели:

```bash
python main.py -i docs/requirements.md -o output/report.md --model gemini-2.5-flash
```

## Тесты

```bash
python -m unittest discover -s tests -v
```

## Структура

```text
.
├── main.py
├── agent.py
├── requirements_validator/
├── prompts/
├── docs/
├── tests/
├── output/
├── .env.example
├── .gitignore
├── requirements.txt
└── VERSION
```

Для PDF-сканов без текстового слоя необходимо предварительно выполнить OCR.
