import logging
import os
import json
import re
import time
import io
from typing import Any, Dict, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

class CloneLogger:
    """
    Enhanced consolidated logger for The Clone's execution.
    Creates a structured, nested Markdown log with collapsible sections.
    """

    def __init__(self, debug_dir: Optional[str] = None):
        self.debug_dir = debug_dir
        self.log_file = None
        self.start_time = time.time()
        self.memory_buffer = io.StringIO()
        self.steps_data: List[Dict[str, Any]] = []
        self.step_start_times: Dict[str, float] = {}

        if debug_dir:
            try:
                os.makedirs(debug_dir, exist_ok=True)
                self.log_file = os.path.join(debug_dir, "FULL_LOG.md")
            except Exception:
                self.log_file = None
        
        self._write_header()

    def _write_header(self):
        header = f"# Clone Execution Log\n"
        header += f"**Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        if self.debug_dir:
            header += f"**Debug Directory:** `{self.debug_dir}`\n"
        self._write(header) # Write immediately

    def _write(self, text: str):
        self.memory_buffer.write(text)
        if self.log_file:
            try:
                # Use 'a' to append incrementally
                with open(self.log_file, 'a', encoding='utf-8') as f:
                    f.write(text)
            except Exception:
                pass # Fail silently if file writing fails

    @staticmethod
    def _step_anchor(step_name: str) -> str:
        """Convert step name to a valid HTML anchor id (lowercase, spaces→hyphens)."""
        return "step-" + re.sub(r'[^a-z0-9-]', '-', step_name.lower()).strip('-')

    def start_step(self, step_name: str):
        """Starts a top-level collapsible section with an HTML anchor id for deep-linking."""
        self.step_start_times[step_name] = time.time()
        timestamp = datetime.now().strftime('%H:%M:%S')
        anchor = self._step_anchor(step_name)
        # id= attribute lets the summary table link directly to this section via #anchor
        self._write(f"\n<details id=\"{anchor}\">\n<summary><b>[SUCCESS] Step: {step_name}</b> <small>({timestamp})</small></summary>\n\n")

    def end_step(self, step_name: str):
        """Closes the top-level collapsible section for a step."""
        duration = time.time() - self.step_start_times.get(step_name, self.start_time)
        self._write(f"<p align='right'><small>Step duration: {duration:.2f}s</small></p>\n")
        self._write("</details>\n")

    def record_step_metric(self, name: str, provider: str, model: str, cost: float, time_taken: float, details: str = ""):
        self.steps_data.append({
            "name": name, "provider": provider, "model": model,
            "cost": cost, "time": time_taken, "details": details
        })

    def log_model_attempts(self, attempted_models: List[Dict], step_name: str = ""):
        """Log model attempts including failures for transparency."""
        if not attempted_models or len(attempted_models) <= 1:
            return  # No failures to report

        failures = [a for a in attempted_models if not a.get('success', True)]
        if not failures:
            return  # All succeeded on first try

        self._write(f"\n> **Model Attempts{' (' + step_name + ')' if step_name else ''}:**\n")
        for attempt in attempted_models:
            if attempt.get('success'):
                self._write(f"> - ✓ `{attempt['model']}` - Success\n")
            else:
                error = attempt.get('error', 'Unknown error')
                self._write(f"> - ✗ `{attempt['model']}` - Failed: {error}\n")
        self._write("\n")

    def log_section(self, title: str, content: Any = None, level: int = 3, collapse: bool = False):
        timestamp = datetime.now().strftime('%H:%M:%S')
        heading = "#" * level

        section_text = f"{heading} {title} <small>({timestamp})</small>\n\n"

        if content is not None:
            formatted_content = self._format_content(content)
            if collapse:
                section_text += f"<details><summary>Click to expand</summary>\n\n{formatted_content}\n\n</details>\n\n"
            else:
                section_text += f"{formatted_content}\n\n"

        self._write(section_text)

    def get_log_content(self) -> str:
        return self.memory_buffer.getvalue()

    def finalize(self, metadata: Dict[str, Any], final_answer: Dict, citations: List[Dict]):
        """Prepends the summary, settings, and final answer to the log."""
        summary_section = self._generate_summary(metadata)
        settings_section = self._generate_settings_summary(metadata)
        answer_section = self._generate_final_answer(final_answer, citations)

        current_content = self.memory_buffer.getvalue()

        # Find the end of the configuration section (look for the <details> tag)
        details_pos = current_content.find("\n<details>")
        if details_pos == -1:
            # Fallback: insert after first ## heading
            details_pos = current_content.find("\n##")
        if details_pos == -1:
            # Last fallback: insert at beginning
            details_pos = len(current_content)

        header = current_content[:details_pos]
        body = current_content[details_pos:]

        full_content = (
            f"{header}\n\n{summary_section}\n{settings_section}\n{answer_section}\n---\n{body}"
        )

        self.memory_buffer = io.StringIO(full_content)
        self.memory_buffer.seek(0, 2)

        if self.log_file:
            try:
                with open(self.log_file, 'w', encoding='utf-8') as f:
                    f.write(full_content)
            except Exception:
                pass

    def _generate_final_answer(self, answer: Dict, citations: List[Dict]) -> str:
        answer_str = f"## 📝 Final Answer\n\n"
        answer_str += self._format_content(answer)
        answer_str += f"\n\n### Citations\n\n"
        answer_str += self._to_markdown_citations(citations)
        return answer_str

    def _expand_classification(self, c: str) -> str:
        """Expand classification codes to full words."""
        if not c:
            return ""

        # Map codes to full descriptions
        code_map = {
            # Authority
            'H': 'High Authority',
            'M': 'Medium Authority',
            'L': 'Low Authority',
            # Quality
            'P': 'Primary',
            'D': 'Documented',
            'A': 'Attributed',
            'O': 'OK',
            'C': 'Contradicted',
            'U': 'Unsourced',
            'PR': 'Promotional',
            'S': 'Stale',
            'SL': 'AI Slop',
            'IR': 'Indirect'
        }

        # Split by / and expand each code
        parts = c.split('/')
        expanded = [code_map.get(part.strip(), part.strip()) for part in parts]
        return ' + '.join(expanded)

    def _escape_markdown(self, text: str) -> str:
        """Escape markdown special characters in citation text."""
        if not text:
            return ""
        # Don't escape characters already in code blocks
        if text.strip().startswith('```'):
            return text

        # Escape markdown characters that break formatting
        text = text.replace('*', '\\*')
        text = text.replace('_', '\\_')

        # Escape markdown headers (# at start of line) to prevent breaking out of blockquote
        lines = text.split('\n')
        escaped_lines = []
        for line in lines:
            # If line starts with # (markdown header), escape it
            if line.lstrip().startswith('#'):
                # Add backslash before first #
                stripped = line.lstrip()
                leading_space = line[:len(line) - len(stripped)]
                escaped_lines.append(leading_space + '\\' + stripped)
            else:
                escaped_lines.append(line)

        return '\n'.join(escaped_lines)

    def _to_markdown_citations(self, citations: List[Dict]) -> str:
        if not citations: return "(No citations)"
        md_citations = []
        for i, cite in enumerate(citations):
            url = cite.get('url', '#')
            title = cite.get('title', 'No Title')
            date = cite.get('date', cite.get('last_updated', ''))
            snippet = cite.get('cited_text', '')
            p_score = cite.get('p', '')
            c_classification = cite.get('c', '')

            entry = f"- **[{i+1}] [{title}]({url})**"
            if date: entry += f" ({date})"

            # Add p/c metadata - expand codes to full words
            metadata = []
            if p_score:
                metadata.append(f"probability={p_score}")
            if c_classification:
                expanded_c = self._expand_classification(c_classification)
                metadata.append(f"classification={expanded_c}")

            if metadata:
                entry += f"\n  *{', '.join(metadata)}*"

            if snippet:
                # Escape markdown in snippet to prevent formatting issues
                escaped_snippet = self._escape_markdown(snippet)
                entry += f"\n  > {escaped_snippet}"
            md_citations.append(entry)
        return "\n".join(md_citations)

    def _generate_settings_summary(self, m: Dict[str, Any]) -> str:
        settings = {
            "Provider": m.get('provider'),
            "Model Override": m.get('model_override'),
            "Schema Provided": "Yes" if m.get('schema_provided') else "No",
            "Use Code Extraction": m.get('use_code_extraction'),
            "Academic Mode": m.get('academic')
        }
        settings_lines = []
        for k, v in settings.items():
            if v is not None: # Only include if value is not None
                settings_lines.append(f"| **{k}** | `{v}` |")
        settings_str = "\n".join(settings_lines)
        return f"### ⚙️ Initial Settings\n\n| Setting | Value |\n| :--- | :--- |\n{settings_str}\n\n---\n"

    def _generate_summary(self, m: Dict[str, Any]) -> str:
        """Generate markdown summary table from recorded steps."""
        
        # Overall metrics
        cost_total = m.get('total_cost', 0.0)
        time_total = m.get('total_time_seconds', 0.0)
        
        summary = f"# ⚡ Execution Summary\n\n| Metric | Value |\n| :--- | :--- |\n"
        summary += f"| **Strategy** | `{m.get('strategy', 'unknown')}` ({m.get('breadth')}/{m.get('depth')}) |\n"
        summary += f"| **Total Cost** | **${cost_total:.4f}** |\n"
        summary += f"| **Total Time** | **{time_total:.1f}s** |\n"
        summary += f"| **Output** | {m.get('citations_count')} Citations / {m.get('total_snippets')} Snippets |\n"
        summary += f"| **Quality** | {m.get('self_assessment', 'N/A')} |\n"
        summary += f"| **Repairs** | {m.get('schema_repairs', 0)} |\n"
        summary += f"| **Tier 4 Upgrade** | {'Yes' if m.get('upgraded_to_deepest') else 'No'} |\n"

        summary += "\n### 🔍 Process Breakdown\n\n| Step | Provider | Model | Cost | Time | Details |\n| :--- | :--- | :--- | :--- | :--- | :--- |\n"

        for step in self.steps_data:
            provider = step['provider']
            if provider in ['unknown', 'mixed']: provider = f"⚠️ {provider}"
            anchor = self._step_anchor(step['name'])
            # Link step name to its collapsible section in the same document
            step_link = f"[{step['name']}](#{anchor})"
            summary += f"| **{step_link}** | {provider} | `{step['model']}` | ${step['cost']:.4f} | {step['time']:.2f}s | {step['details']} |\n"

        return summary + "\n"

    def _format_content(self, content: Any) -> str:
        """Format content for Markdown."""
        if isinstance(content, (dict, list)):
            try:
                return f"```json\n{json.dumps(content, indent=2, ensure_ascii=False)}\n```"
            except (TypeError, ValueError) as e:
                # Handle non-serializable objects (exceptions, semaphores, etc.)
                logger.warning(f"[CLONE_LOGGER] Failed to JSON serialize content: {e}")
                try:
                    return f"```text\n{repr(content)}\n\nNote: Content contained non-JSON-serializable objects\n```"
                except Exception:
                    return "```text\n[content not representable]\n```"
        elif isinstance(content, str):
            if content.strip().startswith("```"): return content
            return f"```text\n{content}\n```"
        else:
            return str(content)
