from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from src.analyzer.scorer import (
    ContributorSignal,
    DifficultyScore,
    DifficultyLabel,
    ScoringResult,
    UnitScore,
)
from src.analyzer.llm_provider import LLMProvider
from src.analyzer.retriever import RetrievalResult, RetrievedUnit


SYSTEM_PROMPT = """You are a senior open source contributor mentoring a newcomer on a GitHub issue.

Respond ONLY with valid JSON. Use EXACTLY this structure — no extra fields, no nesting, no alternative names:

{
    "difficulty": "easy",
    "confidence": 0.8,
    "core_problem": "One or two sentences explaining the real root cause of this issue.",
    "strategic_guidance": [
        "Guidance item 1: what to understand before touching code",
        "Guidance item 2: what to trace or investigate",
        "Guidance item 3: where the fix likely lives and why",
        "Guidance item 4: common pitfalls or edge cases",
        "Guidance item 5: how to validate the fix"
    ],
    "suggested_approach": [
        "Step 1: investigation",
        "Step 2: implementation",
        "Step 3: validation"
    ],
    "positive_signals": ["Signal 1", "Signal 2"],
    "warning_signals": ["Warning 1"],
    "is_good_first_issue": false,
    "files_to_focus": ["path/to/file1", "path/to/file2"]
}

CRITICAL RULES:
- You MUST use the exact field names above. No alternatives. No nested objects.
- strategic_guidance must be a flat list of 4-7 plain strings. Each string is mentoring advice.
- suggested_approach must be a flat list of 2-4 plain strings. Each string is one action step.
- Do NOT use fields like "analysis", "nodes", "steps", "technical_details", "implementation_plan", etc.
- Do NOT nest data inside objects. Keep everything flat.
- Write strategic_guidance in a mentoring tone: "Look at how X works before changing Y because...", "Trace the call chain from A to B...", "Be careful about C because..."
- Confidence should be a number between 0.0 and 1.0."""


def build_ai_prompt(retrieval: RetrievalResult, heuristic_result: Optional[ScoringResult] = None) -> str:
    issue = retrieval.issue
    
    prompt_parts = [
        f"# Issue Analysis Request",
        f"",
        f"## Issue Information",
        f"Title: {issue.title}",
        f"Type: {issue.issue_type.value if hasattr(issue.issue_type, 'value') else issue.issue_type}",
        f"",
    ]
    
    if issue.body:
        body_snippet = issue.body[:1500] if len(issue.body) > 1500 else issue.body
        prompt_parts.append(f"Body (truncated):\n{body_snippet}\n")
    
    if issue.error_patterns:
        prompt_parts.append(f"Error patterns: {', '.join(e.pattern for e in issue.error_patterns[:3])}\n")
    
    if issue.comments:
        prompt_parts.extend([
            f"## Issue Discussion & Comments ({len(issue.comments)} comments)",
            "",
        ])
        for i, comment in enumerate(issue.comments):
            truncated = comment[:600] + "..." if len(comment) > 600 else comment
            prompt_parts.append(f"- {truncated}")
        prompt_parts.append("")
    
    prompt_parts.extend([
        f"## Relevant Code Units Retrieved ({len(retrieval.units)} found)",
        f"",
    ])
    
    for i, unit in enumerate(retrieval.units[:8]):
        unit_info = f"### Unit {i+1}: {unit.path}"
        if unit.name:
            unit_info += f" -> {unit.name}"
        unit_info += f" ({unit.unit_type}, {unit.language})"
        
        if unit.signature:
            unit_info += f"\nSignature: {unit.signature[:100]}"
        if unit.docstring:
            unit_info += f"\nDocstring: {unit.docstring[:200]}"
        
        code_snippet = unit.code[:300] + "..." if len(unit.code) > 300 else unit.code
        unit_info += f"\nCode:\n{code_snippet}"
        
        prompt_parts.append(unit_info)
        prompt_parts.append("")
    
    if heuristic_result:
        prompt_parts.extend([
            f"## Heuristic Analysis (for reference)",
            f"Initial difficulty assessment: {heuristic_result.overall_difficulty.difficulty}",
            f"Confidence: {heuristic_result.overall_difficulty.confidence:.0%}",
            f"Raw score: {heuristic_result.overall_difficulty.raw_score:.2f}",
            f"",
            f"Suggested approach from heuristics:",
        ])
        for suggestion in heuristic_result.suggested_approach[:3]:
            prompt_parts.append(f"  - {suggestion}")
        
        if heuristic_result.positive_signals:
            prompt_parts.append("")
            prompt_parts.append("Positive signals identified:")
            for signal in heuristic_result.positive_signals:
                prompt_parts.append(f"  + {signal}")
        
        if heuristic_result.warning_signals:
            prompt_parts.append("")
            prompt_parts.append("Warning signals:")
            for signal in heuristic_result.warning_signals:
                prompt_parts.append(f"  ! {signal}")
    
    prompt_parts.extend([
        "",
        "## Task",
        "Provide your analysis in JSON format as specified in the system prompt.",
        "Focus on practical guidance for a first-time contributor.",
    ])
    
    return "\n".join(prompt_parts)


def parse_ai_response(response: str) -> dict:
    json_match = re.search(r'\{[\s\S]*\}', response)
    
    if not json_match:
        raise ValueError(f"Could not parse JSON from response: {response[:200]}")
    
    try:
        parsed = json.loads(json_match.group(0))
        
        # --- Extract core_problem from any available field ---
        if not parsed.get("core_problem") or not str(parsed.get("core_problem", "")).strip():
            for key in ["core_problem", "issue_summary", "problem_statement", "summary"]:
                val = parsed.get(key)
                if isinstance(val, str) and len(val.strip()) > 10:
                    parsed["core_problem"] = val.strip()
                    break
            else:
                analysis = parsed.get("analysis")
                if isinstance(analysis, str) and len(analysis.strip()) > 10:
                    parsed["core_problem"] = analysis.strip()
                elif isinstance(analysis, dict):
                    for key in ["summary", "problem_statement", "overview", "description"]:
                        val = analysis.get(key)
                        if isinstance(val, str) and len(val.strip()) > 10:
                            parsed["core_problem"] = val.strip()
                            break
        
        core = str(parsed.get("core_problem", "")).strip()
        
        # --- Extract strategic_guidance from any available field ---
        guidance = []
        existing = parsed.get("strategic_guidance")
        if isinstance(existing, list) and existing:
            guidance = existing
        else:
            # nodes: per-file insights (these ARE strategic guidance)
            nodes = parsed.get("nodes")
            if isinstance(nodes, list):
                for n in nodes:
                    if isinstance(n, dict):
                        desc = n.get("description") or n.get("note") or n.get("rationale")
                        f = n.get("file") or n.get("path") or ""
                        if desc:
                            item = f"In {f}: {desc}" if f else str(desc)
                            if item.strip() and item.strip() not in core:
                                guidance.append(item.strip())
                    elif isinstance(n, str):
                        if n.strip() and n.strip() not in core:
                            guidance.append(n.strip())
            
            analysis = parsed.get("analysis")
            if isinstance(analysis, str) and len(analysis.strip()) > 30:
                # Only add if meaningfully different from core_problem
                if core and (len(analysis.strip()) > len(core) * 1.5 or core not in analysis):
                    guidance.append(analysis.strip())
            elif isinstance(analysis, dict):
                for key in ["context", "technical_details", "background", "ambiguity_check", "description"]:
                    val = analysis.get(key)
                    if isinstance(val, str) and len(val.strip()) > 20 and val.strip() not in core:
                        guidance.append(val.strip())
                for key in ["potential_causes", "root_causes", "key_considerations", "risks"]:
                    val = analysis.get(key)
                    if isinstance(val, list):
                        guidance.extend(f"Consider: {v}" for v in val if isinstance(v, str))
                for key, val in analysis.items():
                    if key not in ["summary", "problem_statement", "overview", "description", "context", "technical_details", "potential_causes", "root_causes", "key_considerations", "risks", "background", "ambiguity_check"]:
                        if isinstance(val, str) and len(val.strip()) > 30 and val.strip() not in core:
                            guidance.append(f"{key}: {val.strip()}")
                        elif isinstance(val, list):
                            guidance.extend(f"Note: {v}" for v in val if isinstance(v, str) and len(str(v).strip()) > 20)
            
            ta = parsed.get("technical_analysis")
            if isinstance(ta, dict):
                for key, val in ta.items():
                    if isinstance(val, str) and len(val.strip()) > 20 and val.strip() not in core:
                        guidance.append(val.strip())
                    elif isinstance(val, list):
                        guidance.extend(str(v).strip() for v in val if v)
            
            vulns = parsed.get("vulnerabilities")
            if isinstance(vulns, list):
                for v in vulns:
                    if isinstance(v, dict):
                        desc = v.get("description") or v.get("issue") or v.get("problem")
                        if isinstance(desc, str) and desc.strip():
                            guidance.append(f"Issue in {v.get('component', 'unknown')}: {desc}")
                    elif isinstance(v, str):
                        guidance.append(v)
            
            rp = parsed.get("reproduction_plan")
            if isinstance(rp, dict):
                steps = rp.get("steps", [])
                if isinstance(steps, list) and steps:
                    guidance.append("To reproduce: " + "; ".join(str(s).strip() for s in steps[:3] if s))
            
            ip = parsed.get("implementation_plan")
            if isinstance(ip, dict):
                steps = ip.get("steps", [])
                if isinstance(steps, list) and steps:
                    guidance.append("Implementation path: " + "; ".join(str(s).strip() for s in steps[:3] if s))
            
            changes = parsed.get("proposed_changes")
            if isinstance(changes, list):
                for c in changes:
                    if isinstance(c, dict):
                        instr = c.get("instructions") or c.get("description") or c.get("change")
                        if isinstance(instr, str) and instr.strip():
                            guidance.append(f"In {c.get('file', 'unknown')}: {instr}")
                    elif isinstance(c, str):
                        guidance.append(c)
            
            vp = parsed.get("verification_plan")
            if isinstance(vp, dict):
                auto = vp.get("automated_tests", [])
                manual = vp.get("manual_verification", [])
                if auto or manual:
                    items = []
                    items.extend(str(s).strip() for s in auto[:2] if s)
                    items.extend(str(s).strip() for s in manual[:2] if s)
                    if items:
                        guidance.append("Verify by: " + "; ".join(items))
            
            ver_steps = parsed.get("verification_steps")
            if isinstance(ver_steps, list) and ver_steps:
                items = []
                for v in ver_steps[:3]:
                    if isinstance(v, dict):
                        desc = v.get("description") or v.get("step") or v.get("action")
                        if isinstance(desc, str) and desc.strip():
                            items.append(desc.strip())
                    elif isinstance(v, str):
                        items.append(v.strip())
                if items:
                    guidance.append("Verify by: " + "; ".join(items))
        
        # Deduplicate while preserving order
        seen = set()
        unique_guidance = []
        for g in guidance:
            key = g[:80]
            if key not in seen:
                seen.add(key)
                unique_guidance.append(g)
        parsed["strategic_guidance"] = unique_guidance[:7]
        
        # --- Extract suggested_approach from any available field ---
        steps = []
        existing_steps = parsed.get("suggested_approach")
        if isinstance(existing_steps, list) and existing_steps:
            steps = existing_steps
        else:
            sb = parsed.get("step_by_step_instructions")
            if isinstance(sb, list):
                for item in sb:
                    if isinstance(item, dict):
                        desc = item.get("description") or item.get("step") or item.get("action") or ""
                        if desc:
                            steps.append(str(desc).strip())
                    elif isinstance(item, str):
                        steps.append(item.strip())
            
            if not steps:
                ip = parsed.get("implementation_plan")
                if isinstance(ip, dict):
                    ip_steps = ip.get("steps", [])
                    if isinstance(ip_steps, list):
                        steps.extend(str(s).strip() for s in ip_steps if s)
            
            if not steps:
                changes = parsed.get("proposed_changes")
                if isinstance(changes, list):
                    for c in changes:
                        if isinstance(c, dict):
                            instr = c.get("instructions") or c.get("description")
                            if isinstance(instr, str) and instr.strip():
                                steps.append(f"In {c.get('file', 'unknown')}: {instr.strip()}")
                        elif isinstance(c, str):
                            steps.append(c.strip())
            
            if not steps:
                rp = parsed.get("reproduction_plan")
                if isinstance(rp, dict):
                    rp_steps = rp.get("steps", [])
                    if isinstance(rp_steps, list):
                        steps.extend("Repro: " + str(s).strip() for s in rp_steps[:2] if s)
            
            if not steps:
                stf = parsed.get("steps_to_fix")
                if isinstance(stf, list):
                    steps.extend(str(s).strip() for s in stf if s)
            
            if not steps:
                raw_steps = parsed.get("steps")
                if isinstance(raw_steps, list):
                    for s in raw_steps:
                        if isinstance(s, dict):
                            desc = s.get("step") or s.get("description") or s.get("action") or ""
                            details = s.get("details") or ""
                            combined = f"{desc} — {details}".strip(" —") if details else str(desc).strip()
                            if combined:
                                steps.append(combined)
                        elif isinstance(s, str) and s.strip():
                            steps.append(s.strip())
        
        parsed["suggested_approach"] = steps[:5]
        
        parsed.setdefault("difficulty", "medium")
        parsed.setdefault("confidence", 0.5)
        parsed.setdefault("is_good_first_issue", False)
        parsed.setdefault("positive_signals", [])
        parsed.setdefault("warning_signals", [])
        parsed.setdefault("files_to_focus", [])
        
        if parsed["difficulty"] not in ["easy", "medium", "hard"]:
            parsed["difficulty"] = "medium"
        
        return parsed
    
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}. Response: {response[:200]}")


class AIScorer:
    def __init__(
        self,
        provider: LLMProvider,
        fallback_scorer: Optional[object] = None,
        timeout: int = 30,
    ):
        self.provider = provider
        self.fallback_scorer = fallback_scorer
        self.timeout = timeout

    def score(self, retrieval: RetrievalResult) -> ScoringResult:
        heuristic_result = None
        
        if self.fallback_scorer:
            heuristic_result = self.fallback_scorer.score(retrieval)
        
        prompt = build_ai_prompt(retrieval, heuristic_result)
        
        try:
            response = self.provider.complete(prompt)
            ai_analysis = parse_ai_response(response)
            
            return self._build_result(retrieval, ai_analysis, heuristic_result)
        
        except Exception as e:
            if heuristic_result:
                return heuristic_result
            
            raise AIScoringError(f"AI scoring failed: {e}") from e

    def _build_result(
        self,
        retrieval: RetrievalResult,
        ai_analysis: dict,
        heuristic_result: Optional[ScoringResult],
    ) -> ScoringResult:
        difficulty_str = ai_analysis.get("difficulty", "medium").lower()
        
        if difficulty_str not in ["easy", "medium", "hard"]:
            difficulty_str = "medium"
        
        difficulty_label = DifficultyLabel(difficulty_str)
        
        difficulty_score = DifficultyScore(
            raw_score=0.5 if difficulty_str == "medium" else (0.25 if difficulty_str == "easy" else 0.75),
            difficulty=difficulty_label.value,
            confidence=ai_analysis.get("confidence", 0.7),
            relative_percentile=None,
        )
        
        positive_signals = ai_analysis.get("positive_signals", [])
        if not positive_signals and heuristic_result:
            positive_signals = heuristic_result.positive_signals
        
        warning_signals = ai_analysis.get("warning_signals", [])
        if not warning_signals and heuristic_result:
            warning_signals = heuristic_result.warning_signals
        
        suggested_approach = ai_analysis.get("suggested_approach", [])
        if not suggested_approach and heuristic_result:
            suggested_approach = heuristic_result.suggested_approach
        
        core_problem = ai_analysis.get("core_problem", "")
        strategic_guidance = ai_analysis.get("strategic_guidance", [])
        
        units = []
        if heuristic_result:
            units = heuristic_result.units
        else:
            units = [
                UnitScore(
                    unit=unit,
                    difficulty_score=0.5,
                    signals=[],
                )
                for unit in retrieval.units
            ]
        
        return ScoringResult(
            issue_title=retrieval.issue.title,
            overall_difficulty=difficulty_score,
            units=units,
            positive_signals=positive_signals[:5],
            warning_signals=warning_signals[:5],
            suggested_approach=suggested_approach[:5],
            is_good_first_issue=ai_analysis.get("is_good_first_issue", False),
            core_problem=core_problem,
            strategic_guidance=strategic_guidance[:7],
        )


class AIScoringError(Exception):
    pass


def create_ai_scorer(
    provider_name: str,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    fallback_scorer: Optional[object] = None,
    timeout: int = 30,
) -> Optional[AIScorer]:
    from src.analyzer.config import ProviderName
    from src.analyzer.llm_provider import get_provider_instance
    
    try:
        provider_enum = ProviderName(provider_name.lower())
    except ValueError:
        return None
    
    provider = get_provider_instance(provider_enum, api_key=api_key, model=model)
    
    if provider is None:
        return None
    
    return AIScorer(
        provider=provider,
        fallback_scorer=fallback_scorer,
        timeout=timeout,
    )


__all__ = [
    "AIScorer",
    "AIScoringError",
    "build_ai_prompt",
    "parse_ai_response",
    "create_ai_scorer",
]