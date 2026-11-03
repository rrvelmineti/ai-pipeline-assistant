"""Compare ranked sources. Live mode sends only the public corpus and fixed questions."""
import argparse
import json
import os
from pathlib import Path
from time import monotonic

from orders_assistant.investigate import Index, corpus, keyword_search

CASES = {
    "invalid_number": ["Can an item count contain a fraction?", "My unit price has too many decimal places."],
    "invalid_mapping": ["The vendor renamed a header. What do I map?", "Two input columns share a name."],
    "missing_value": ["A required cell contains only whitespace.", "The export has a blank required field."],
    "invalid_date": ["February 30 appears in a snapshot.", "What date format does inventory accept?"],
    "duplicate": ["One SKU appears twice.", "Does the inventory snapshot require unique identifiers?"],
    "invalid_csv": ["My quoted field has an unclosed quote.", "The export cannot be decoded as UTF-8."],
    "input_limit": ["Which file size is allowed?", "The export has too many rows."],
    "empty_file": ["An extract had only a header.", "Why did an empty report fail?"],
    "database_failure": ["SQLite rejected the write.", "Could another writer have locked the database?"],
    "ok": ["Can I rerun the same orders import?", "How do I verify the committed order count?"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Also call Google's embedding API.")
    args = parser.parse_args()
    docs = corpus()
    stage = {d.metadata["code"]: d.metadata["stage"] for d in docs}
    index = None
    if args.live:
        from langchain_google_genai import GoogleGenerativeAIEmbeddings
        model = os.environ["GEMINI_EMBEDDING_MODEL"]
        embed = GoogleGenerativeAIEmbeddings(model=model, google_api_key=os.environ["GEMINI_API_KEY"], vertexai=False)
        index = Index(Path("local_data/evaluation-index"), model, embed)
    results = []
    for code, queries in CASES.items():
        for q in queries:
            start = monotonic()
            candidates = keyword_search(q, docs)
            row = {"query": q, "expected": code, "keyword_hit": any(d.metadata["code"] == code for d in candidates)}
            if index:
                hits = index.search(q, stage[code])
                row.update(vector_hit=any(d.metadata["code"] == code for d in hits),
                           retrieved=[d.metadata["id"] for d in hits], elapsed_seconds=monotonic()-start)
            results.append(row)
    print(json.dumps({"results": results, "keyword_hits": sum(r["keyword_hit"] for r in results),
                      "vector_hits": sum(r["vector_hit"] for r in results) if index else None}, indent=2))


if __name__ == "__main__":
    main()
