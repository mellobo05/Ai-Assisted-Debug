"""
Evaluate the lightweight issue-domain classifier for over/underfitting signals.

This repo uses a weakly-supervised, simple Multinomial Naive Bayes classifier
trained from your local Postgres `jira_issues` data (components/labels are used
as weak labels).

This script measures how well the model generalizes on a hold-out split.

Usage (PowerShell):
  python scripts/ml/eval_issue_domain_classifier.py --max-items 500 --test-frac 0.2

Notes:
  - This is NOT a "ground truth" evaluation unless you provide manual labels.
  - Still useful to detect obvious overfitting (train high, test low) or
    underfitting (both low).
"""

from __future__ import annotations

import argparse
import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple


def _tokenize_simple(text: str) -> List[str]:
    t = (text or "").lower()
    # words + simple tokens (keep dp/hdmi)
    toks = re.findall(r"[a-z0-9][a-z0-9\-\_\.]{1,30}", t)
    return [x for x in toks if len(x) >= 2]


def _domain_keywords() -> Dict[str, List[str]]:
    # Must be kept consistent with backend/app/agents/tools/jira_tools.py
    return {
        "display": [
            "display",
            "graphics",
            "drm",
            "kms",
            "i915",
            "xe",
            "wayland",
            "x11",
            "xorg",
            "compositor",
            "monitor",
            "external display",
            "dock",
            "docked",
            "dp",
            "displayport",
            "hdmi",
            "edp",
        ],
        "media": ["media", "video", "codec", "decoder", "encode", "hevc", "h.265", "av1", "vaapi", "libva", "gstreamer"],
        "audio": ["audio", "alsa", "pulseaudio", "pipewire", "speaker", "microphone", "snd"],
        "network": ["network", "wifi", "wlan", "bluetooth", "bt", "ethernet", "iwlwifi", "rtl", "mt7921"],
        "storage": ["storage", "nvme", "ssd", "mmc", "emmc", "ufs", "sata", "ext4", "btrfs"],
        "power": ["power", "suspend", "resume", "s0ix", "hibernate", "battery", "thermal", "fan"],
        "input": ["touch", "trackpad", "keyboard", "hid", "i2c", "wacom"],
    }


def _infer_weak_label(*, components: List[str], labels: List[str]) -> Optional[str]:
    cl = (" ".join([str(x) for x in (components or [])]) + " " + " ".join([str(x) for x in (labels or [])])).lower()
    cl = cl.strip()
    if not cl:
        return None
    for dd, kws in _domain_keywords().items():
        if any(k in cl for k in kws):
            return dd
    return None


@dataclass(frozen=True)
class Example:
    issue_key: str
    text: str
    label: str


class MultinomialNB:
    def __init__(self, *, alpha: float = 1.0):
        self.alpha = float(alpha)
        self.domains: List[str] = []
        self.vocab: Dict[str, int] = {}
        self.label_word_counts: Dict[str, Dict[int, int]] = {}
        self.label_totals: Dict[str, int] = {}
        self.label_docs: Dict[str, int] = {}
        self.priors_log: Dict[str, float] = {}

    def fit(self, examples: List[Example]) -> None:
        domains = sorted({ex.label for ex in examples})
        self.domains = domains
        self.vocab = {}
        self.label_word_counts = {d: {} for d in domains}
        self.label_totals = {d: 0 for d in domains}
        self.label_docs = {d: 0 for d in domains}

        for ex in examples:
            self.label_docs[ex.label] += 1
            toks = _tokenize_simple(ex.text)
            for tok in toks:
                if tok not in self.vocab:
                    self.vocab[tok] = len(self.vocab)
                tid = self.vocab[tok]
                wc = self.label_word_counts[ex.label]
                wc[tid] = wc.get(tid, 0) + 1
                self.label_totals[ex.label] += 1

        total_docs = float(sum(self.label_docs.values()))
        a = float(self.alpha)
        self.priors_log = {
            d: math.log((self.label_docs[d] + a) / (total_docs + a * len(domains))) for d in domains
        }

    def predict_proba(self, text: str) -> Dict[str, float]:
        toks = _tokenize_simple(text)
        counts: Dict[int, int] = {}
        for tok in toks:
            tid = self.vocab.get(tok)
            if tid is None:
                continue
            counts[tid] = counts.get(tid, 0) + 1

        if not counts:
            return {d: 1.0 / float(len(self.domains) or 1) for d in self.domains}

        V = float(len(self.vocab) or 1)
        a = float(self.alpha)

        scores: Dict[str, float] = {}
        for d in self.domains:
            s = self.priors_log.get(d, 0.0)
            denom = float(self.label_totals.get(d, 0)) + a * V
            wc = self.label_word_counts.get(d, {})
            for tid, c in counts.items():
                num = float(wc.get(tid, 0)) + a
                s += c * math.log(num / denom)
            scores[d] = s

        m = max(scores.values())
        exps = {d: math.exp(scores[d] - m) for d in self.domains}
        Z = sum(exps.values()) or 1.0
        return {d: float(exps[d] / Z) for d in self.domains}

    def predict(self, text: str) -> str:
        probs = self.predict_proba(text)
        return max(probs.items(), key=lambda kv: kv[1])[0] if probs else ""


def _split(examples: List[Example], *, test_frac: float, seed: int) -> Tuple[List[Example], List[Example]]:
    rng = random.Random(int(seed))
    items = list(examples)
    rng.shuffle(items)
    n_test = max(1, int(round(len(items) * float(test_frac))))
    test = items[:n_test]
    train = items[n_test:]
    return train, test


def _metrics(y_true: List[str], y_pred: List[str]) -> Dict[str, float]:
    assert len(y_true) == len(y_pred)
    n = len(y_true) or 1
    acc = sum(1 for a, b in zip(y_true, y_pred) if a == b) / float(n)
    return {"accuracy": float(acc)}


def _per_class_report(y_true: List[str], y_pred: List[str]) -> Tuple[str, Dict[str, Dict[str, float]]]:
    labels = sorted(set(y_true) | set(y_pred))
    tp = Counter()
    fp = Counter()
    fn = Counter()
    for yt, yp in zip(y_true, y_pred):
        if yt == yp:
            tp[yt] += 1
        else:
            fp[yp] += 1
            fn[yt] += 1

    rows: Dict[str, Dict[str, float]] = {}
    lines = []
    lines.append("label\tprecision\trecall\tf1\tsupport")
    for lab in labels:
        t = float(tp[lab])
        p = float(tp[lab] + fp[lab])
        r = float(tp[lab] + fn[lab])
        prec = t / p if p else 0.0
        rec = t / r if r else 0.0
        f1 = (2.0 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
        sup = int(sum(1 for x in y_true if x == lab))
        rows[lab] = {"precision": prec, "recall": rec, "f1": f1, "support": float(sup)}
        lines.append(f"{lab}\t{prec:.3f}\t{rec:.3f}\t{f1:.3f}\t{sup}")

    # macro averages
    if labels:
        macro_p = sum(rows[l]["precision"] for l in labels) / float(len(labels))
        macro_r = sum(rows[l]["recall"] for l in labels) / float(len(labels))
        macro_f1 = sum(rows[l]["f1"] for l in labels) / float(len(labels))
        lines.append(f"macro_avg\t{macro_p:.3f}\t{macro_r:.3f}\t{macro_f1:.3f}\t{len(y_true)}")

    return "\n".join(lines), rows


def _top_confusions(y_true: List[str], y_pred: List[str], *, k: int = 10) -> List[Tuple[str, str, int]]:
    c = Counter()
    for yt, yp in zip(y_true, y_pred):
        if yt != yp:
            c[(yt, yp)] += 1
    items = [((a, b), n) for (a, b), n in c.items()]
    items.sort(key=lambda x: x[1], reverse=True)
    out: List[Tuple[str, str, int]] = []
    for (a, b), n in items[: int(k)]:
        out.append((a, b, int(n)))
    return out


def _load_examples_from_db(*, max_items: int) -> List[Example]:
    # Local import so this script can be present even if backend deps aren't installed.
    import sys
    from pathlib import Path

    # Ensure "backend" is on sys.path when running from repo root.
    root = Path(__file__).resolve().parents[2]
    backend_dir = root / "backend"
    sys.path.insert(0, str(backend_dir))

    # Load .env so DATABASE_URL works when running as a script.
    try:
        from dotenv import load_dotenv  # type: ignore

        env_path = (root / ".env").resolve()
        if env_path.exists():
            load_dotenv(dotenv_path=env_path, override=False)
    except Exception:
        pass

    from app.db.session import SessionLocal  # type: ignore
    from app.models.jira import JiraIssue  # type: ignore

    db = SessionLocal()
    try:
        rows = (
            db.query(JiraIssue.issue_key, JiraIssue.summary, JiraIssue.description, JiraIssue.components, JiraIssue.labels)
            .limit(int(max_items))
            .all()
        )
    finally:
        db.close()

    exs: List[Example] = []
    for issue_key, summary, description, components, labels in rows:
        comps = components if isinstance(components, list) else []
        labs = labels if isinstance(labels, list) else []
        lab = _infer_weak_label(components=[str(x) for x in comps], labels=[str(x) for x in labs])
        if not lab:
            continue
        text = (str(summary or "") + "\n" + str(description or "")).strip()
        k = str(issue_key or "").strip().upper()
        if not k or not text:
            continue
        exs.append(Example(issue_key=k, text=text, label=lab))
    return exs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-items", type=int, default=2000)
    ap.add_argument("--test-frac", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--min-examples", type=int, default=30, help="Minimum weak-labeled examples required to run.")
    args = ap.parse_args()

    exs = _load_examples_from_db(max_items=int(args.max_items))
    if len(exs) < int(args.min_examples):
        print(f"Not enough weak-labeled examples to evaluate: n={len(exs)} (min={int(args.min_examples)})")
        return 2

    train, test = _split(exs, test_frac=float(args.test_frac), seed=int(args.seed))
    if len(train) < 5 or len(test) < 5:
        print(f"Split too small: train={len(train)}, test={len(test)}")
        return 2

    clf = MultinomialNB(alpha=1.0)
    clf.fit(train)

    y_train_true = [e.label for e in train]
    y_train_pred = [clf.predict(e.text) for e in train]
    y_test_true = [e.label for e in test]
    y_test_pred = [clf.predict(e.text) for e in test]

    m_train = _metrics(y_train_true, y_train_pred)
    m_test = _metrics(y_test_true, y_test_pred)

    print("=== Weak-label domain classifier evaluation ===")
    print(f"examples_total={len(exs)} train={len(train)} test={len(test)} seed={int(args.seed)} test_frac={float(args.test_frac):.2f}")
    print("")
    print(f"train_accuracy={m_train['accuracy']:.3f}")
    print(f"test_accuracy ={m_test['accuracy']:.3f}")
    print("")

    rep, _rows = _per_class_report(y_test_true, y_test_pred)
    print("=== Test per-class report ===")
    print(rep)
    print("")

    conf = _top_confusions(y_test_true, y_test_pred, k=10)
    if conf:
        print("=== Top confusions (true -> pred) ===")
        for a, b, n in conf:
            print(f"{a} -> {b}: {n}")
        print("")

    # Heuristic readout: overfit vs underfit hint
    gap = float(m_train["accuracy"]) - float(m_test["accuracy"])
    if float(m_train["accuracy"]) >= 0.85 and float(m_test["accuracy"]) <= 0.60 and gap >= 0.20:
        print("Hint: likely OVERFITTING (train high, test low, big gap).")
    elif float(m_train["accuracy"]) <= 0.60 and float(m_test["accuracy"]) <= 0.60:
        print("Hint: likely UNDERFITTING (both low).")
    else:
        print("Hint: unclear/mixed (review per-class metrics + confusions).")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

