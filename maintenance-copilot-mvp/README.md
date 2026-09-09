# Maintenance Copilot MVP

A production-shaped prototype for a water/wastewater maintenance copilot.

## What it does

A technician can:
1. Select an asset.
2. Ask a troubleshooting question.
3. View current/recent operating conditions.
4. Search asset manuals and troubleshooting guidance.
5. Search prior work orders for similar failures.
6. Receive a grounded recommendation with cited evidence.

The included demo uses synthetic data for a RAS pump at a fictitious wastewater treatment plant.

## Architecture

```text
Synthetic CMMS + Synthetic SCADA + Manuals
                   |
                   v
              Data services
                   |
       +-----------+-----------+
       |                       |
       v                       v
 Work-order search       Knowledge search
       |                       |
       +-----------+-----------+
                   |
                   v
            Maintenance Agent
                   |
                   v
              Streamlit UI
```

The data-service interfaces are intentionally separated so synthetic files can later be replaced with:
- Snowflake
- CMMS APIs
- SCADA historians
- WIMS/LIMS
- cloud document stores

## Run locally

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
streamlit run app/main.py
```

## Optional LLM

The MVP works without an LLM using a deterministic evidence-based answer generator.

To use OpenAI later, set:

```bash
OPENAI_API_KEY=...
```

and extend `app/agent.py` with your preferred model integration.

## Suggested next steps

1. Replace synthetic work orders with a real CMMS export/API.
2. Replace synthetic SCADA with historian/Snowflake data.
3. Add embeddings/vector search for large document libraries.
4. Add identity and role-based permissions.
5. Add human-approved CMMS actions such as creating inspection work orders.
