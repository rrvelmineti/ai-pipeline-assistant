# Claims data onboarding: process map

```mermaid
flowchart TD
    A[Client sends claims extract] --> B[Analyst uploads CSV]
    B --> C{Headers readable<br/>and unique?}
    C -- No --> X[Return file to client<br/>with header problem]
    C -- Yes --> D[Name matching suggests mappings]
    D --> E[Optional: Gemini suggests mappings<br/>from headings only]
    E --> F[Analyst approves or corrects<br/>each mapping]
    F --> G[Correction log updated]
    G --> H{All required fields<br/>mapped once?}
    H -- No --> F
    H -- Yes --> I[Code checks every row against<br/>plain-language rules]
    I --> J[Readiness report:<br/>blockers, warnings, decision]
    J --> K{Zero blockers and<br/>complete scan?}
    K -- No --> L[Send findings CSV to client]
    L --> A
    K -- Yes --> M[Approver signs off for go-live]
```

## Who does what

| Step | Owner | AI involved? |
| --- | --- | --- |
| Upload and header check | Analyst | No |
| Mapping suggestions | Tool | Name matching always; Gemini optional, headings only |
| Approve or correct mappings | Analyst | No, this is the human decision point |
| Rule checks | Tool (code) | No, results must be exact |
| Readiness decision | Tool (code) | No |
| Plain-English summary | Tool | Optional, restricted to verified figures |
| Sign-off | Approver | No |
