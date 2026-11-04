"""Optional RAG over generic issue categories; uploaded headers and cells stay local."""
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from .investigate import Citation, context


class ReadChoice(BaseModel):
    action: Literal["evidence", "search", "finish"]


def explain_issue(issue, index, llm, *, agent=False):
    # Construct an allowlisted payload instead of forwarding an arbitrary finding.
    code = issue["code"]
    facts = {"stage": "validation", "code": code, "row": issue["line"],
             "underlying_cause": None}
    if code == "invalid_type":
        code = "csv_type"
    elif code == "invalid_date":
        code = "csv_date"
    elif code == "missing_value":
        code = "csv_missing"
    elif code == "field_count":
        code = "csv_structure"
    else:
        raise ValueError("Unsupported guidance category.")
    facts["code"] = code
    query = "What should I check next? " + code
    docs = index.search(query, "validation")
    trace = []
    decisions = 0
    if agent:
        class State(TypedDict):
            action: str

        def decide(state):
            nonlocal decisions
            decisions += 1
            allowed = [a for a in ("evidence", "search") if a not in [t["tool"] for t in trace]]
            result = llm.with_structured_output(ReadChoice).invoke(
                f"Read-only CSV investigation. Facts: {facts}. Read results: {trace}. "
                f"Choose a useful action from {allowed}, or finish. No source data can be edited.")
            return {"action": result.action if result.action in allowed else "finish"}

        def read(state):
            if state["action"] == "search":
                more = index.search(query + " verify source", "validation")
                docs.extend(d for d in more if d.metadata["id"] not in {x.metadata["id"] for x in docs})
                value = [d.metadata["id"] for d in more]
            else:
                value = facts
            trace.append({"tool": state["action"], "result": value})
            return state

        graph = StateGraph(State)
        graph.add_node("choose", decide)
        graph.add_node("read", read)
        graph.add_edge(START, "choose")
        graph.add_conditional_edges("choose", lambda s: END if s["action"] == "finish" else "read")
        graph.add_conditional_edges("read", lambda s: END if len(trace) >= 2 else "choose")
        graph.compile().invoke({"action": "finish"})
    prompt, included = context("What should I check next?", facts, trace, docs)
    answer = llm.with_structured_output(Citation).invoke(prompt)
    accepted = next((d for d in included if d.metadata["id"] == answer.source
                     and d.metadata["code"] == code and d.metadata["section"] == "Next check"
                     and d.page_content == answer.quote), None)
    return {"observed": facts, "model_explanation": answer.explanation if accepted else None,
            "next_check": accepted.page_content if accepted else None,
            "citation": accepted.metadata["id"] if accepted else None,
            "sources": [{"passage": d.page_content, **d.metadata} for d in included],
            "tool_trace": trace, "model_calls": decisions + 1,
            "input_bytes": len(prompt.encode()), "output_reserve_tokens": 512,
            "limitation": "Guidance is not a verified cause or an automatic correction."}
