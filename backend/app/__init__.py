"""
Finance Spend Intelligence Assistant: backend package.

Reading order for newcomers (each file opens with a plain-English summary):

    config.py          settings, including the Claude API key (key_1)
    data/              loads the invoice and vendor files, converts money to EUR
    policy/            reads the procurement policy and its approval thresholds
    tools/             the four "calculators" Claude can call; they do all the maths
    llm/               the prompt and the conversation loop with Claude
    evidence.py        turns Claude's citations into the evidence shown to users
    validators.py      checks every citation and every number in an answer
    summary.py         the GET /summary overview (no AI involved)
    main.py            the web API that the frontend talks to
"""
