# Maintenance Copilot MVP

A production-shaped water/wastewater maintenance copilot prototype.

## Current capabilities

- 24 synthetic pump assets across four demo facilities.
- Multiple failure scenarios: bearing degradation, obstruction, coupling/alignment, discharge restriction, seal issues, and normal operation.
- 5-minute SCADA-style operating trends.
- CMMS work-order history with similar-event search.
- Equipment troubleshooting knowledge retrieval.
- Deterministic evidence ranking as a transparent safety rail.
- Optional OpenAI tool-calling agent that decides which maintenance evidence tools to use before answering.
- Real CMMS CSV adapter via `CMMS_CSV_PATH`.
- GitHub Actions tests, Docker packaging, and a Render deployment blueprint.

## Architecture

```text
CMMS / SCADA / Manuals
        |
        v
   Data adapters
        |
        v
 Maintenance tools
  |      |      |
asset  SCADA  search
  |      |      |
  +------+------+ 
         |
         v
  AI tool-calling agent
         |
         +---- deterministic evidence ranking
         |
         v
     Streamlit UI
```

The interfaces are intentionally separated so demo sources can later be replaced with Snowflake, CMMS APIs, SCADA historians, WIMS/LIMS, and document stores.

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

The application works without an API key using the deterministic evidence engine.

## Enable the AI agent

Set an OpenAI API key in your environment. Do not commit keys to GitHub.

### PowerShell

```powershell
$env:OPENAI_API_KEY="your-key"
$env:OPENAI_MODEL="gpt-5.6-luna"
streamlit run app/main.py
```

The AI agent uses explicit maintenance tools for asset context, recent SCADA, equipment guidance, and prior work orders. The deterministic evidence ranking remains visible alongside AI synthesis.

## Use a real CMMS export

Normalize a CMMS export to these required columns:

```text
work_order_id
asset_id
date
problem
cause
corrective_action
```

Optional columns such as downtime, labor, parts, technician, priority, and status can remain in the CSV.

Then point the app to the file:

```powershell
$env:CMMS_CSV_PATH="C:\path\to\cmms_export.csv"
streamlit run app/main.py
```

If records exist for the selected asset, the copilot uses the real CMMS rows before demo-generated history.

## Deploy

The repository contains both `Dockerfile` and `render.yaml`. A hosted deployment can run without an OpenAI key using the deterministic engine. To enable AI in production, add `OPENAI_API_KEY` as a secret environment variable in the hosting platform.

For Render, create a new Blueprint/Web Service from this GitHub repository. Render will detect `render.yaml` and build the Docker image. Do not place secrets in `render.yaml` or the repository.

## Data-source roadmap

1. Replace CMMS CSV with a direct CMMS API connector.
2. Replace synthetic SCADA with historian/Snowflake streaming data.
3. Replace prototype text retrieval with embeddings/vector search across OEM manuals, SOPs, drawings, and engineering reports.
4. Add identity, permissions, audit logging, and facility-level access controls.
5. Add human-approved actions such as creating an inspection work order.
6. Expand the asset ontology beyond pumps to blowers, mixers, centrifuges, chemical feed systems, UV systems, valves, and instrumentation.

## Safety

This prototype provides decision support only. It does not issue equipment commands and must not be used to bypass lockout/tagout, guards, interlocks, permits, confined-space requirements, OEM procedures, or site safety rules.
