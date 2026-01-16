from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


_KEY_RE = re.compile(r"([A-Z][A-Z0-9]+-\d+)")


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None:
        return None
    txt = (el.text or "").strip()
    return txt or None


def _find_first_text(node: ET.Element, tag_names: List[str]) -> Optional[str]:
    """
    Best-effort extraction across different JIRA XML export shapes.
    Looks for direct children first, then any descendants.
    """
    # Direct children
    for t in tag_names:
        child = node.find(t)
        v = _text(child)
        if v:
            return v
    # Descendants
    for t in tag_names:
        child = node.find(f".//{t}")
        v = _text(child)
        if v:
            return v
    return None


def _guess_issue_key(node: ET.Element) -> Optional[str]:
    # Common tags
    v = _find_first_text(node, ["key", "issuekey", "issueKey", "IssueKey", "IssueKeyValue"])
    if v:
        m = _KEY_RE.search(v)
        return m.group(1) if m else v

    # Sometimes key is embedded in link/title
    for t in ["link", "title", "summary"]:
        vv = _find_first_text(node, [t])
        if vv:
            m = _KEY_RE.search(vv)
            if m:
                return m.group(1)
    return None


def parse_jira_xml(xml_content: str) -> List[Dict[str, Any]]:
    """
    Parse a JIRA XML export into a list of issue-like dicts.

    JIRA exports vary a lot (RSS-like <item> vs <issue> trees). This parser is
    intentionally forgiving and will do best-effort extraction.
    """
    root = ET.fromstring(xml_content)

    # Common shapes
    issue_nodes = root.findall(".//item")
    if not issue_nodes:
        issue_nodes = root.findall(".//issue")
    if not issue_nodes:
        # last resort: treat any element named "Issue" as issue node
        issue_nodes = [n for n in root.iter() if n.tag.lower() == "issue"]

    parsed: List[Dict[str, Any]] = []
    for node in issue_nodes:
        issue_key = _guess_issue_key(node)
        summary = _find_first_text(node, ["summary", "title"]) or ""
        description = _find_first_text(node, ["description", "body"])
        status = _find_first_text(node, ["status"])
        priority = _find_first_text(node, ["priority"])
        assignee = _find_first_text(node, ["assignee"])
        issue_type = _find_first_text(node, ["type", "issuetype", "issueType"])
        link = _find_first_text(node, ["link", "url"])

        # Store a raw dict of all immediate children for traceability
        raw: Dict[str, Any] = {"_source": "jira_xml_export"}
        for child in list(node):
            tag = child.tag
            raw[tag] = _text(child)

        parsed.append(
            {
                "issue_key": issue_key,
                "summary": summary,
                "description": description,
                "status": status,
                "priority": priority,
                "assignee": assignee,
                "issue_type": issue_type,
                "url": link,
                "raw": raw,
            }
        )

    return parsed


def build_embedding_text_from_parsed(issue: Dict[str, Any]) -> str:
    return (
        f"JIRA Issue {issue.get('issue_key','')}\n"
        f"Type: {issue.get('issue_type','')}\n"
        f"Status: {issue.get('status','')}\n"
        f"Priority: {issue.get('priority','')}\n"
        f"Assignee: {issue.get('assignee','')}\n"
        f"Summary: {issue.get('summary','')}\n\n"
        f"Description:\n{issue.get('description','') or ''}\n"
    )

