# Visual Compliance Agent

Automated browser agent that opens a source URL, uses screenshots plus an optional vision LLM to navigate toward a form, then extracts consent language, Terms text, Privacy text, and evidence.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
```

Optional LLM navigation:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-4o-mini"
```

For local UI testing, you can also put the key in `config/local_settings.py`:

```python
OPENAI_API_KEY = "your-key"
OPENAI_MODEL = "gpt-4o-mini"
```

Environment variables take precedence. Without an OpenAI key, the agent falls back to legacy DOM/CTA heuristics.

## Run

```powershell
python main.py https://example.com --output runs/example-result.json
```

Useful options:

```powershell
python main.py https://example.com --max-steps 5 --max-runtime 120 --headful
python main.py https://example.com --no-llm
```

## Report UI

```powershell
python report_server.py
# If 8765 is already in use:
python report_server.py --port 8766
```

Open the matching UI URL, for example `http://127.0.0.1:8766/ui/` when using `--port 8766`. The interface can run a fresh inspection from a pasted URL, choose max steps/runtime, toggle LLM navigation, choose a model, show the browser, load `runs/result.json`, or import/paste another result JSON.

The report includes a Form Candidates panel showing which form-like element was selected, the detector score, selector, reason, visible text, field counts, and page coordinates.

## Flow

1. Load the URL in Playwright.
2. Capture a full-page screenshot and scroll segments.
3. On the initial page, ask the LLM whether a valid finance form is visible.
4. If no valid form is visible, ask the LLM for strong button/link candidates that may lead to it.
5. Click those candidate buttons in ranked order.
6. After each candidate click, ask the LLM only whether the destination page contains a valid finance form.
7. Extract visible consent language, Terms/Privacy links, and policy text.
8. Return structured JSON with screenshots, LLM assessment, candidates, and evidence.

## Output Shape

```json
{
  "form_found": true,
  "final_url": "https://example.com/signup",
  "steps": [],
  "submit_language": "By clicking Submit, you agree to...",
  "terms_url": "https://example.com/terms",
  "privacy_url": "https://example.com/privacy",
  "terms_text": "...",
  "privacy_text": "...",
  "screenshots": []
}
```
