# Contributing

Use a focused branch and a pull request targeting main. Run:

```powershell
python -m pip install -r requirements.txt
python -m compileall -q orders_assistant app.py examples/orders tests
python -m unittest discover -s tests -v
```

Tests must stay offline. Use synthetic orders, never customer exports or keys.
Treat model output as untrusted. Unknown causes stay unknown; missing values are
not zero. Never execute model-produced code or silently repair source data.

Review the diff and CI before merging. Describe the change, evidence from tests,
and limitations. Do not claim live API verification when only mocks were tested.
