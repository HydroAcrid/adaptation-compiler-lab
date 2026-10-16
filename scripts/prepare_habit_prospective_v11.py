"""Author new fictional materials after the v10 instrument failure; never overwrite a freeze."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from scripts import prepare_habit_prospective as original

CHOICES = {
    "concise_progress": (
        "Your progress report is taking over the chat. Keep the checkpoint to a few key facts.",
        "For status messages, just give the change since the last check-in and any obstacle.",
        "The ongoing commentary can be tighter. I only need a quick progress note.",
    ),
    "concise_summary": (
        "The end-of-task answer could be trimmed to the takeaway and its important limits.",
        "That closing summary is longer than I can use. Give me the short version.",
        "Condense the final recap so the essential result is easy to find.",
    ),
    "explain_reasoning": (
        "Back up the wrap-up's conclusion with why it follows from what you found.",
        "The final answer needs to connect the evidence to the conclusion for me.",
        "In your closing explanation, show the thinking that supports the takeaway.",
    ),
    "outcome_first": (
        "Put the end result at the top of your final reply; explain it afterward.",
        "I have to scroll for the conclusion. Move it to the opening of the recap.",
        "In the wrap-up, say what happened first and then how you got there.",
    ),
    "connected_prose": (
        "Make the recap read as connected sentences rather than a stack of bullet fragments.",
        "The final explanation flows better as a paragraph. Join these separate points.",
        "Could you turn the closing bullets into prose that links the findings together?",
    ),
    "numbered_steps": (
        "Add step numbers to the walkthrough so I can tell where to pick it up.",
        "The instruction sequence is hard to track. Number the individual steps.",
        "When presenting this how-to, label each step with its position in the sequence.",
    ),
    "comparison_table": (
        "Arrange the option comparison as a small table with the same columns for each choice.",
        "Show the differences between these alternatives in aligned rows and columns.",
        "For your comparison presentation, put the alternatives side by side in a table.",
    ),
    "short_suggestion_list": (
        "There are too many recommendations to choose from. Keep the list to the best few.",
        "Your suggestions need pruning. Give me a handful of strong options.",
        "Narrow the proposed next moves to a short list I can actually act on.",
    ),
    "explain_tradeoffs": (
        "When you recommend an option, tell me the compromise that comes with it.",
        "Include the effort and drawbacks alongside the upside of each suggestion.",
        "Help me choose among your recommendations by explaining what each sacrifices.",
    ),
}
REVERSALS = {
    "concise_progress": (
        "These short progress notes have stopped being useful. Give the fuller picture now."
    ),
    "concise_summary": (
        "The compressed wrap-ups leave me guessing now. Use detailed closing explanations."
    ),
    "explain_reasoning": (
        "I no longer need the reasoning in every recap. Keep these answers to the result."
    ),
    "outcome_first": (
        "Result-first recaps no longer suit this work. Explain the path before the conclusion now."
    ),
    "connected_prose": (
        "Continuous paragraphs are harder for me to scan now. Use bullets for these recaps."
    ),
    "numbered_steps": (
        "The numbered walkthroughs are getting in my way now. Describe the sequence in prose."
    ),
    "comparison_table": (
        "The tabular option summaries aren't working anymore. "
        "Explain those comparisons in sentences."
    ),
    "short_suggestion_list": (
        "Your shortlists have become too restrictive. Include a broader set of suggestions now."
    ),
    "explain_tradeoffs": (
        "The detailed tradeoff notes slow these choices down now. "
        "Give the recommendations without them."
    ),
}
TASKS = (
    "Review the food bank handoff.",
    "Help finish the neighborhood workshop schedule.",
    "Check the equipment repair budget.",
    "Reconcile the community event roster.",
    "Review the cycling route notes.",
    "Help finish the library training brief.",
    "Check the renovation timeline.",
)


def build() -> dict[str, object]:
    previous = original.CHOICES, original.REVERSALS, original.TASKS
    try:
        original.CHOICES, original.REVERSALS, original.TASKS = CHOICES, REVERSALS, TASKS
        data = original.build()
    finally:
        original.CHOICES, original.REVERSALS, original.TASKS = previous
    data["evaluation_version"] = "habit-eval-v11"
    data["provenance"] = (
        "Fresh fictional sequences authored before v11 execution; no private evidence."
    )
    for case in cast(list[dict[str, Any]], data["cases"]):
        case["id"] = case["id"].replace("prospective-", "fresh11-", 1)
        for episode in case["episodes"]:
            episode["task_id"] = episode["task_id"].replace("prospective-", "fresh11-", 1)
            episode["project_id"] = "fictional-ridge"
            episode["date"] = {
                "2026-02-04": "2026-03-11",
                "2026-02-07": "2026-03-14",
                "2026-02-10": "2026-03-20",
            }[episode["date"]]
        if "project_id" in case["expected"]:
            case["expected"]["project_id"] = "fictional-ridge"
        if "control" in case:
            case["control"]["project_id"] = (
                "fictional-valley"
                if case["control"]["project_id"] == "fictional-estuary"
                else "fictional-ridge"
            )
    return data


def main() -> None:
    from adaptation_compiler_lab.serialization import canonical_digest

    data = build()
    path = (
        Path(__file__).resolve().parents[1]
        / "tests/fixtures/autonomy/habit_eval_v11_prospective.json"
    )
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("existing prospective materials changed; preserve the freeze")
    path.write_text(encoded, encoding="utf-8")
    print(json.dumps({"dataset_digest": canonical_digest(data), "cases": 120, "executed": False}))


if __name__ == "__main__":
    main()
