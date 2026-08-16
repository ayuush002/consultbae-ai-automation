# ConsultBae AI Automation Assignment

A working candidate-data pipeline, n8n duplicate-alert automation, and WAV audio collection application built for the ConsultBae AI Automation assignment.

## Live links

- **Application:** https://consultbae-ai-automation.onrender.com
- **Audio submissions:** https://consultbae-ai-automation.onrender.com/submissions
- **Health check:** https://consultbae-ai-automation.onrender.com/health
- **n8n production webhook:** https://ayuush002.app.n8n.cloud/webhook/candidate-csv-duplicate-check
- **Repository:** https://github.com/ayuush002/consultbae-ai-automation

> The Render free service may take about a minute to wake up after a period of inactivity.

## What is included

1. **Audited data ingestion:** normalizes three inconsistent CSV schemas, validates input columns, repairs one shifted row, rejects invalid rows, merges duplicate identities, and writes SQLite tables with source lineage.
2. **No-code automation:** an importable n8n workflow accepts a CSV through a webhook, checks every candidate against the deployed API, and returns a duplicate or no-duplicate alert summary.
3. **Audio collection app:** accepts a worker's name, phone number, and uncompressed WAV file; extracts technical metadata; stores the submission; and provides browser playback.
4. **Data-quality report:** documents defects, normalization rules, matching decisions, limitations, and production recommendations.

## Architecture

```text
Three source CSVs
        |
        v
Python normalization + identity resolution
        |
        +--> SQLite: candidates + source lineage + rejected rows
        |                         |
        |                         v
        |                 Candidate-check API <--- n8n CSV webhook
        |
        +--> Flask audio upload --> WAV analysis --> submissions + playback
```

## Data-pipeline results

| Metric | Result |
|---|---:|
| Raw source rows | 105 |
| Accepted rows | 103 |
| Automatically repaired rows | 1 |
| Rejected rows | 2 |
| Unique candidates | 56 |
| Duplicate rows merged | 47 |

The full analysis is in [docs/data_quality_report.md](docs/data_quality_report.md).

Supporting engineering notes:

- [Stuck and decision log](docs/stuck_and_decision_log.md)
- [Production scaling note](docs/scaling_note.md)

## Run locally

### Requirements

- Python 3.12
- No Node.js or Docker is required for the Python application
- An n8n account is required only if you want to import and run the no-code workflow

### Setup

```bash
git clone https://github.com/ayuush002/consultbae-ai-automation.git
cd consultbae-ai-automation
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Build the database

```bash
python automation/ingest_and_merge.py
```

Expected summary:

```text
Raw Rows             105
Accepted Rows        103
Repaired Rows        1
Rejected Rows        2
Unique Candidates    56
Duplicates Merged    47
```

The command creates `consultbae.db`. The generated database is intentionally not committed because it is reproducible from the fictional source CSVs.

### Start the web application

```bash
flask --app app.api run --debug
```

Open http://127.0.0.1:5000. Use `data/audio_test_sample.wav` to test the audio form.

## Candidate duplicate API

Endpoint:

```text
POST /api/candidates/check
Content-Type: application/json
```

Example:

```bash
curl -X POST \
  https://consultbae-ai-automation.onrender.com/api/candidates/check \
  -H "Content-Type: application/json" \
  -d '{"email":"tanvi.gupta31@example.com","phone":"9000000254"}'
```

The response reports whether a duplicate exists, which normalized identifiers matched, and the matching canonical candidates.

## n8n automation

Workflow export: [automation/ConsultBae CSV Duplicate Alert.json](automation/ConsultBae%20CSV%20Duplicate%20Alert.json)

### Import and run

1. In n8n, create or open a project.
2. Choose **Import from File** and select the workflow JSON above.
3. Confirm the Webhook node uses `POST`, path `candidate-csv-duplicate-check`, and **Using Respond to Webhook Node**.
4. Publish the workflow.
5. Send a multipart upload using the binary field name `data`.

Production test:

```bash
curl -X POST \
  "https://ayuush002.app.n8n.cloud/webhook/candidate-csv-duplicate-check" \
  -F "data=@data/n8n_test_candidates.csv"
```

Expected summary for the included mixed test file:

```json
{
  "message": "Duplicate candidates found in uploaded CSV",
  "status": "duplicate_alert",
  "total_records": 2,
  "duplicate_count": 1,
  "new_count": 1
}
```

Use `data/n8n_test_new_only.csv` to verify the no-duplicates branch.

### Workflow stages

```text
Webhook -> Extract CSV -> Check Candidate API -> Aggregate Results
        -> Build Summary -> Duplicates Found?
             true  -> duplicate alert response
             false -> no-duplicates response
```

## Audio application

The form accepts:

- Full name
- Valid 10-digit Indian mobile number
- Uncompressed PCM WAV file, up to 20 MB

For each valid recording, the application calculates and displays:

- Duration
- Sample rate
- Uncompressed bitrate
- RMS loudness in dBFS
- Channel count
- A simple level-quality estimate

Invalid or empty WAV files are rejected and removed. The submissions page lists recordings and provides an HTML audio player.

## Tests

The project uses Python's built-in `unittest`, so no separate test framework is required.

```bash
python -m unittest discover -s tests -v
```

The suite contains 16 tests covering normalization, schema changes, ingestion auditing, duplicate API behavior, WAV validation, metadata extraction, and candidate linkage.

## Database tables

- `candidates`: canonical merged candidate profiles.
- `candidate_sources`: every accepted raw source row and repair status.
- `rejected_rows`: rejected source rows with reasons and original content.
- `audio_submissions`: uploaded-audio metadata and candidate linkage.

## Deployment notes

`render.yaml` defines the public Gunicorn/Flask service. On startup, the application rebuilds the SQLite candidate database from the committed fictional CSV files when the database does not exist.

The free deployment uses an ephemeral filesystem. Uploaded recordings and audio-submission rows may disappear when the service restarts or redeploys. A production version should use managed PostgreSQL and object storage such as S3 or Cloudflare R2.

## Important limitations

- Audio analysis supports uncompressed PCM WAV files only.
- Phone normalization currently assumes Indian 10-digit mobile numbers.
- Email validation checks syntax but does not verify mailbox ownership.
- Name-and-city matching is conservative but still heuristic.
- The public endpoint has no authentication because the assignment uses fictional data; production endpoints should require authentication and rate limiting.

## Stuck log: three hardest problems

The complete chronological log is in [docs/stuck_and_decision_log.md](docs/stuck_and_decision_log.md). These were the three hardest points.

### 1. Making ingestion survive changed files and columns

I asked AI: **“What if the number of columns or number of files changes, and how should we handle it?”** I also reviewed how pandas exposes headers before rows are processed. The first suggestion I rejected was matching columns by position or manually changing the script for every new CSV; that would silently map the wrong data after a reorder. I instead added a source-specific schema contract with canonical names and accepted aliases. Extra columns are harmless, but missing required columns fail before the database is replaced. Tests then deliberately add an extra column, use aliases, and remove a required column.

### 2. Getting n8n webhooks and responses to work

I searched/asked about the exact n8n errors: **“webhook is not registered,” “Unused Respond to Webhook node,”** and **“Expression evaluation failed: `$json` is not defined.”** I learned that test webhooks accept one request only after the listener starts, while the published `/webhook/` URL stays registered. I rejected the suggestion to delete the no-duplicates response node because both IF outcomes need a clear caller response; the real unused-node problem was the Webhook's immediate-response setting. I changed it to **Using Respond to Webhook Node** and replaced ambiguous `$json` response expressions with the explicit `$("Build Summary").first().json` reference. I then tested both branches and the published production URL with `curl`.

### 3. Deploying audio analysis without unnecessary dependencies

I compared Node.js, Docker, FFmpeg, and Python options and asked how an evaluator could run the project without having Node installed. I rejected making Node.js or Docker mandatory because the core app did not need them and that would add setup friction. I implemented PCM WAV inspection with Python's standard library. When deployment compatibility showed that `audioop` is unavailable after Python 3.12, I pinned Python 3.12 rather than introducing a system-level FFmpeg dependency late in the assignment. The trade-off is documented: a production version should migrate to a maintained audio library.

AI tools were used for guidance, debugging, code review, and documentation. I manually tested the pipeline, both n8n branches, the production webhook, the deployed audio app, and all 16 automated tests. I reviewed the implementation and can explain its matching, persistence, API, workflow, and audio decisions.

## Repository structure

```text
app/                         Flask API, audio processing, templates, and CSS
automation/                  CSV pipeline and exported n8n workflow
data/                        Fictional assignment data and reproducible test inputs
docs/data_quality_report.md  Data issues and engineering decisions
tests/                       Built-in unittest suite
render.yaml                  Reproducible Render deployment
requirements.txt             Python dependencies
```
