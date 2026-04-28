from __future__ import annotations

from playwright.async_api import Page

from core.models import FormCandidate, FormDetectionResult


class FormDetector:
    async def detect(self, page: Page) -> FormDetectionResult:
        payload = await page.evaluate(
            r"""
            () => {
              const visible = el => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 &&
                  style.visibility !== 'hidden' &&
                  style.display !== 'none' &&
                  !el.closest('[aria-hidden="true"]');
              };
              const normalize = value => (value || '').replace(/\s+/g, ' ').trim();
              const cssEscape = value => {
                if (window.CSS && window.CSS.escape) return window.CSS.escape(value);
                return String(value || '').replace(/[^a-zA-Z0-9_-]/g, '\\$&');
              };
              const selectorFor = el => {
                if (el.id) return `#${cssEscape(el.id)}`;
                const name = el.getAttribute('name');
                if (name) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\"')}"]`;
                const role = el.getAttribute('role');
                if (role) return `${el.tagName.toLowerCase()}[role="${role.replace(/"/g, '\\"')}"]`;
                const parent = el.parentElement;
                if (!parent) return el.tagName.toLowerCase();
                const siblings = Array.from(parent.children).filter(child => child.tagName === el.tagName);
                const index = siblings.indexOf(el) + 1;
                return `${el.tagName.toLowerCase()}:nth-of-type(${index || 1})`;
              };
              const rectFor = el => {
                const rect = el.getBoundingClientRect();
                return {
                  x: Math.round(rect.x + window.scrollX),
                  y: Math.round(rect.y + window.scrollY),
                  width: Math.round(rect.width),
                  height: Math.round(rect.height)
                };
              };
              const labelFor = el => normalize(
                el.getAttribute('placeholder') ||
                el.getAttribute('aria-label') ||
                el.getAttribute('name') ||
                el.id ||
                el.value ||
                el.innerText ||
                el.tagName
              );
              const textFor = el => normalize(
                el.innerText ||
                el.value ||
                el.getAttribute('aria-label') ||
                el.getAttribute('placeholder') ||
                el.getAttribute('name') ||
                el.id ||
                ''
              ).slice(0, 500);
              const inputSelector = [
                'input:not([type="hidden"]):not([disabled])',
                'textarea:not([disabled])',
                'select:not([disabled])',
                '[contenteditable="true"]'
              ].join(',');
              const inputs = Array.from(document.querySelectorAll(inputSelector)).filter(visible);
              const controls = Array.from(document.querySelectorAll('button,input[type="submit"],input[type="button"],a,[role="button"]'))
                .filter(visible);
              const submitWords = /(submit|send|get started|start|continue|next|apply|sign up|register|request|quote|contact|join|enroll)/i;
              const submitControls = controls.filter(el => {
                const text = normalize(el.innerText || el.value || el.getAttribute('aria-label'));
                return submitWords.test(text);
              });
              const formElements = Array.from(document.querySelectorAll('form')).filter(visible);
              const formCount = formElements.length;
              const evidence = [];
              for (const input of inputs.slice(0, 5)) {
                evidence.push(labelFor(input));
              }
              for (const control of submitControls.slice(0, 5)) {
                evidence.push(labelFor(control));
              }
              const positiveWords = /(apply|application|loan|cash|quote|request|get started|start|continue|next|sign up|register|contact|phone|email|name|address|zip|amount|income|employment|enroll|join)/i;
              const weakWords = /(search|newsletter|subscribe|login|log in|sign in|filter|sort)/i;
              const scoreCandidate = (kind, label, text, inputCount, submitCount, isForm) => {
                let score = 0;
                score += Math.min(inputCount, 8) * 22;
                score += Math.min(submitCount, 4) * 30;
                if (isForm) score += 15;
                const combined = `${label} ${text}`;
                if (positiveWords.test(combined)) score += 35;
                if (submitWords.test(combined)) score += 20;
                if (weakWords.test(combined)) score -= 35;
                if (kind === 'submit_control' && inputCount === 0) score -= 25;
                return Math.max(score, 0);
              };
              const reasonFor = (kind, score, inputCount, submitCount, text) => {
                const details = [];
                if (inputCount) details.push(`${inputCount} visible input${inputCount === 1 ? '' : 's'}`);
                if (submitCount) details.push(`${submitCount} submit-like control${submitCount === 1 ? '' : 's'}`);
                if (/apply|loan|quote|request|get started|sign up|register|contact/i.test(text)) {
                  details.push('conversion/form language');
                }
                if (!details.length && kind === 'submit_control') details.push('submit-like control text');
                if (!details.length) details.push('visible form-like element');
                return `${details.join(', ')}. Score ${score}.`;
              };
              const makeCandidate = (kind, el, inputCount, submitCount, isForm = false) => {
                const label = labelFor(el);
                const text = textFor(el);
                const score = scoreCandidate(kind, label, text, inputCount, submitCount, isForm);
                return {
                  kind,
                  label,
                  selector: selectorFor(el),
                  text,
                  score,
                  reason: reasonFor(kind, score, inputCount, submitCount, `${label} ${text}`),
                  inputCount,
                  submitButtonCount: submitCount,
                  ...rectFor(el)
                };
              };
              const candidates = [];
              for (const form of formElements) {
                const formInputs = Array.from(form.querySelectorAll(inputSelector)).filter(visible);
                const formSubmits = Array.from(form.querySelectorAll('button,input[type="submit"],input[type="button"],a,[role="button"]'))
                  .filter(visible)
                  .filter(el => submitWords.test(labelFor(el)));
                candidates.push(makeCandidate('form', form, formInputs.length, formSubmits.length, true));
              }
              for (const input of inputs) {
                const container = input.closest('form') || input.closest('section,article,main,div') || input;
                if (formElements.includes(container)) continue;
                const containerInputs = Array.from(container.querySelectorAll ? container.querySelectorAll(inputSelector) : [input]).filter(visible);
                const containerSubmits = Array.from(container.querySelectorAll ? container.querySelectorAll('button,input[type="submit"],input[type="button"],a,[role="button"]') : [])
                  .filter(visible)
                  .filter(el => submitWords.test(labelFor(el)));
                candidates.push(makeCandidate('input_group', container, containerInputs.length || 1, containerSubmits.length, false));
              }
              for (const control of submitControls) {
                const container = control.closest('form') || control.closest('section,article,main,div') || control;
                if (formElements.includes(container)) continue;
                const containerInputs = Array.from(container.querySelectorAll ? container.querySelectorAll(inputSelector) : []).filter(visible);
                candidates.push(makeCandidate('submit_control', control, containerInputs.length, 1, false));
              }
              const seen = new Set();
              const rankedCandidates = candidates
                .filter(candidate => candidate.label || candidate.text || candidate.inputCount || candidate.submitButtonCount)
                .sort((left, right) => right.score - left.score)
                .filter(candidate => {
                  const key = `${candidate.kind}:${candidate.selector}:${candidate.label}`.toLowerCase();
                  if (seen.has(key)) return false;
                  seen.add(key);
                  return true;
                })
                .slice(0, 12);
              return {
                inputCount: inputs.length,
                submitButtonCount: submitControls.length,
                formCount,
                evidence: evidence.filter(Boolean),
                candidates: rankedCandidates
              };
            }
            """
        )
        input_count = int(payload.get("inputCount", 0))
        submit_count = int(payload.get("submitButtonCount", 0))
        form_count = int(payload.get("formCount", 0))
        evidence = list(payload.get("evidence", []))
        candidates = [
            FormCandidate(
                kind=str(item.get("kind", "")),
                label=str(item.get("label", "")),
                selector=str(item.get("selector", "")),
                text=str(item.get("text", "")),
                score=int(item.get("score", 0)),
                reason=str(item.get("reason", "")),
                x=float(item.get("x", 0)),
                y=float(item.get("y", 0)),
                width=float(item.get("width", 0)),
                height=float(item.get("height", 0)),
                input_count=int(item.get("inputCount", 0)),
                submit_button_count=int(item.get("submitButtonCount", 0)),
            )
            for item in payload.get("candidates", [])
        ]
        primary_candidate = candidates[0] if candidates else None
        return FormDetectionResult(
            found=primary_candidate is not None or input_count > 0 or submit_count > 0 or form_count > 0,
            input_count=input_count,
            submit_button_count=submit_count,
            form_count=form_count,
            evidence=evidence,
            candidates=candidates,
            primary_candidate=primary_candidate,
        )
