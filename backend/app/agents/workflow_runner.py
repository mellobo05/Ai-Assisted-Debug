from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml


ToolFn = Callable[..., Any]


@dataclass(frozen=True)
class Step:
    name: str
    action: str
    parameters: Dict[str, Any]
    options: Dict[str, Any]


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    steps: list[Step]


_TEMPLATE_RE = re.compile(r"\$\{([^}]+)\}")


def _get_by_path(obj: Any, path: str) -> Any:
    """
    Resolve dotted paths like:
      inputs.query
      steps.sync.embedded
    Also supports ADAG-style variables with no prefix:
      target_jira_key   -> inputs.target_jira_key
    """
    cur: Any = obj
    # ADAG-style: if the template is a single name, prefer ctx["inputs"][name]
    # (so YAML can use ${target_jira_key} instead of ${inputs.target_jira_key}).
    if "." not in path and isinstance(obj, dict):
        inputs = obj.get("inputs")
        if isinstance(inputs, dict) and path in inputs:
            return inputs.get(path)

    for part in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            cur = getattr(cur, part, None)
        if cur is None:
            return None
    return cur


def _render_templates(value: Any, ctx: Dict[str, Any]) -> Any:
    if isinstance(value, str):
        # If the entire string is a single template, return the raw value (not stringified).
        m = _TEMPLATE_RE.fullmatch(value.strip())
        if m:
            return _get_by_path(ctx, m.group(1).strip())

        def _repl(match: re.Match[str]) -> str:
            v = _get_by_path(ctx, match.group(1).strip())
            return "" if v is None else str(v)

        return _TEMPLATE_RE.sub(_repl, value)

    if isinstance(value, list):
        return [_render_templates(v, ctx) for v in value]

    if isinstance(value, dict):
        return {k: _render_templates(v, ctx) for k, v in value.items()}

    return value


def load_workflow(path: str | Path) -> Workflow:
    p = Path(path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    wf = raw.get("workflow") or {}

    name = str(wf.get("name") or p.stem)
    description = str(wf.get("description") or "")
    steps_raw = wf.get("steps") or []
    steps: list[Step] = []
    for s in steps_raw:
        if not isinstance(s, dict):
            continue
        step_name = str(s.get("step") or s.get("name") or s.get("id") or f"step_{len(steps)+1}")
        action = str(s.get("action") or "").strip()
        parameters = s.get("parameters") or {}
        options = s.get("options") or {}
        if not isinstance(parameters, dict):
            raise ValueError(f"Step '{step_name}': parameters must be a dict")
        if not isinstance(options, dict):
            raise ValueError(f"Step '{step_name}': options must be a dict")
        if not action:
            raise ValueError(f"Step '{step_name}': missing action")
        steps.append(Step(name=step_name, action=action, parameters=parameters, options=options))

    return Workflow(name=name, description=description, steps=steps)


def run_workflow(
    workflow_path: str | Path,
    tools: Dict[str, ToolFn],
    inputs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute a workflow and return a structured result.

    Context shape:
      ctx["inputs"] = user-provided inputs
      ctx["steps"][step_name] = step output
    """
    wf = load_workflow(workflow_path)
    ctx: Dict[str, Any] = {"inputs": inputs or {}, "steps": {}}

    outputs: Dict[str, Any] = {"workflow": {"name": wf.name, "description": wf.description}, "steps": []}

    for step in wf.steps:
        if step.action not in tools:
            raise ValueError(f"Unknown action '{step.action}' (step '{step.name}')")

        params = _render_templates(step.parameters, ctx)
        opts = step.options or {}
        save_as = str(opts.get("save_as") or step.name)
        skip_in_output = bool(opts.get("skip_in_output") or False)

        # Optional "input" wiring: pass previous step output(s) as input_data
        if "input" in opts:
            input_ref = opts.get("input")
            if isinstance(input_ref, str):
                params = dict(params)
                params["input_data"] = _get_by_path(ctx, input_ref)
            elif isinstance(input_ref, list):
                params = dict(params)
                # Preserve the ref name as the key so subagent-like tools can access inputs predictably.
                params["input_data"] = {str(k): _get_by_path(ctx, str(k)) for k in input_ref}

        out = tools[step.action](ctx=ctx, **(params or {}))
        ctx["steps"][save_as] = out

        if not skip_in_output:
            outputs["steps"].append({"step": step.name, "action": step.action, "save_as": save_as, "output": out})
        else:
            outputs["steps"].append({"step": step.name, "action": step.action, "save_as": save_as, "output": None})

    outputs["context"] = {"steps": ctx["steps"]}
    return outputs

