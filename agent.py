"""Requirements validator agent: python agent.py <requirements file> <report file>"""
import os, sys, subprocess, datetime, pathlib
import requests
from dotenv import load_dotenv

load_dotenv()
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
KEY = os.getenv("GEMINI_API_KEY")
HERE = pathlib.Path(__file__).parent


def read_doc(path):
    p = pathlib.Path(path)
    if p.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(pg.extract_text() or "" for pg in PdfReader(p).pages)
    if p.suffix.lower() == ".docx":
        import docx
        return "\n".join(par.text for par in docx.Document(p).paragraphs)
    return p.read_text(encoding="utf-8")


def agent_version():
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=HERE, text=True).strip()
    except Exception:
        return "dev"


def call_llm(system, user):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.2},
    }
    r = requests.post(url, json=body, headers={"x-goog-api-key": KEY}, timeout=600)
    r.raise_for_status()
    return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])


def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python agent.py <requirements file> <report file>")
    if not KEY:
        sys.exit("GEMINI_API_KEY is not set (see .env.example)")
    src, out = sys.argv[1], sys.argv[2]
    system = (HERE / "prompt.md").read_text(encoding="utf-8")
    for k, v in {"{{DOC_NAME}}": pathlib.Path(src).name,
                 "{{RUN_DATE}}": datetime.date.today().isoformat(),
                 "{{MODEL_NAME}}": MODEL,
                 "{{AGENT_VERSION}}": agent_version()}.items():
        system = system.replace(k, v)
    doc = read_doc(src)
    report = call_llm(system, "Проверь следующий документ требований:\n\n" + doc)
    pathlib.Path(out).write_text(report, encoding="utf-8")
    print(f"Report written to {out}")


if __name__ == "__main__":
    main()
