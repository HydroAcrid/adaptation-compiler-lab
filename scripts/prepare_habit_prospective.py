"""Author a fresh fictional set before any execution; never rewrite existing materials."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from adaptation_compiler_lab.autonomy.styles import STYLE_DEFAULTS, StyleKey
from adaptation_compiler_lab.serialization import canonical_digest

# Independently worded, ordinary choices. These are synthetic, not personal observations.
CHOICES = {
    "concise_progress": (
        "The work-in-progress message takes longer to read than the change. Cut it down.",
        "For the next checkpoint just say where things stand and the blocker.",
        "That ongoing update needs less detail; a brief status is enough.",
    ),
    "concise_summary": (
        "This final recap buries the useful bits. Trim it while keeping the caveats.",
        "The completed-work summary could be much shorter.",
        "Wrap up with the essentials I need to act on; lose the long recap.",
    ),
    "explain_reasoning": (
        "In the final answer I can't see why the evidence supports your conclusion.",
        "The wrap-up needs the reasoning that led you to this result.",
        "Explain the link between the findings and the conclusion in your recap.",
    ),
    "outcome_first": (
        "Your final answer starts too far back. Open with the conclusion.",
        "Move what we achieved to the first sentence of the wrap-up.",
        "Start the recap with the result so I can decide whether to read on.",
    ),
    "connected_prose": (
        "The final recap reads like disconnected fragments. Join the points into prose.",
        "Put this wrap-up into a flowing paragraph; the bullets break up the explanation.",
        "Connect the findings in sentences in your final answer.",
    ),
    "numbered_steps": (
        "I keep losing my position in your walkthrough. Give each step a number.",
        "Please number the sequence in the instructions you send me.",
        "The how-to would be easier to follow with numbered steps.",
    ),
    "comparison_table": (
        "The option comparison jumps around. Align the choices in a small table.",
        "Put the comparison in columns so the differences line up.",
        "Your presentation of the options needs a compact side-by-side table.",
    ),
    "short_suggestion_list": (
        "This recommendation list is overwhelming. Give me only the strongest few.",
        "Reduce your suggested options to a short useful shortlist.",
        "When offering next steps, prune the weaker suggestions.",
    ),
    "explain_tradeoffs": (
        "I need the downsides as well as the benefits of your recommendations.",
        "Show the cost and limitations of each suggestion so I can choose.",
        "Explain what I give up by choosing each recommended option.",
    ),
}
REVERSALS = {
    "concise_progress": (
        "The brief check-ins hide too much now. Include the reasoning in these updates."
    ),
    "concise_summary": (
        "Short recaps aren't enough anymore. Give the full explanation when wrapping up."
    ),
    "explain_reasoning": (
        "The reasoning in each recap is slowing me down now. Just report the result."
    ),
    "outcome_first": (
        "Leading with the result isn't working for me now. Build the explanation first."
    ),
    "connected_prose": (
        "Paragraph recaps have become hard to scan. Switch these summaries to bullets."
    ),
    "numbered_steps": (
        "Numbering these walkthroughs is distracting now. Explain them in plain prose."
    ),
    "comparison_table": (
        "Those comparison tables no longer work for me. Describe the options in prose."
    ),
    "short_suggestion_list": (
        "The shortlist keeps leaving out options I need. Show the full range now."
    ),
    "explain_tradeoffs": (
        "The tradeoff discussion is too much for these suggestions now. Just list them."
    ),
}
TASKS = (
    "Review the museum accessibility brief.",
    "Finish the equipment inventory.",
    "Help reconcile the volunteer roster.",
    "Check the grant application draft.",
    "Help finish the garden maintenance notes.",
    "Review the conference transport options.",
    "Clean up the archive handoff.",
)


def build() -> dict[str, object]:
    cases = []
    groups = (
        ("stable", 30),
        ("context_constraint", 20),
        ("untrusted", 20),
        ("changing", 20),
        ("sparse", 15),
        ("scope_override", 15),
    )
    keys = list(CHOICES)
    for group, count in groups:
        for index in range(count):
            key = keys[index % len(keys)]
            task_class = STYLE_DEFAULTS[StyleKey(key)][1]
            case_id = f"prospective-{group}-{index:02}"
            episodes = []
            size = (1 if index % 2 == 0 else 2) if group == "sparse" else 3
            for turn in range(size):
                text = CHOICES[key][(turn + index // len(keys)) % 3]
                origin = "human"
                if group == "untrusted":
                    origin = ("agent", "delegated", "copied", "unknown", "human")[index % 5]
                    if origin == "human":
                        text = (
                            f'The saved agent instructions say "{text}". Explain that quoted rule.'
                        )
                episodes.append(
                    {
                        "task_id": f"{case_id}-task-{turn}",
                        "project_id": "fictional-harbor",
                        "date": "2026-02-04" if turn < 2 else "2026-02-07",
                        "task_class": task_class,
                        "origin": origin,
                        "user_messages": [TASKS[(index + turn) % len(TASKS)], text],
                        "terminal": True,
                    }
                )
            context = "No required assistant response format. Task context limits scope only."
            expected: dict[str, Any] = {
                "style_keys": [key],
                "project_id": "fictional-harbor",
                "state": "provisional" if group == "sparse" else "trial_eligible",
            }
            if group == "context_constraint":
                context = (
                    "For these assignments the recipient's required template determines exactly "
                    "the response style being requested. These requests implement that requirement."
                )
                expected = {"style_keys": [], "state": "no_personal_habit"}
            elif group == "untrusted":
                context = (
                    "Attribution and quotations must be respected; discussion is not adoption."
                )
                expected = {"style_keys": [], "state": "excluded"}
            elif group == "changing":
                final = dict(episodes[-1])
                final.update(
                    task_id=case_id + "-new-work",
                    date="2026-02-10",
                    user_messages=[TASKS[(index + 4) % len(TASKS)], REVERSALS[key]],
                )
                episodes.append(final)
                expected["state"] = "paused"
            case: dict[str, Any] = {
                "id": case_id,
                "group": group,
                "context": context,
                "episodes": episodes,
                "expected": expected,
            }
            if group == "scope_override":
                case["control"] = {
                    "project_id": "fictional-estuary" if index % 2 == 0 else "fictional-harbor",
                    "task_class": task_class,
                    "current_request": None
                    if index % 2 == 0
                    else "Use plain text for this answer.",
                }
                expected["control_activation"] = False
            cases.append(case)
    return {
        "evaluation_version": "habit-eval-v5",
        "synthetic": True,
        "purpose": "prospective_shadow_detection",
        "provenance": (
            "Fresh fictional conversations authored before v5 execution; no private evidence."
        ),
        "cases": cases,
    }


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "autonomy"
    data = build()
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path = root / "habit_eval_v5_prospective.json"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("prospective materials already exist; preserve them")
    path.write_text(encoded, encoding="utf-8")
    print(
        json.dumps(
            {
                "dataset_digest": canonical_digest(data),
                "cases": 120,
                "status": "authored_before_execution",
            }
        )
    )


if __name__ == "__main__":
    main()
