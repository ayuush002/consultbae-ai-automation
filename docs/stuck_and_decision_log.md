# Stuck and Decision Log

This log records the main problems encountered while building the assignment, the diagnosis, and the final decision. It is intentionally concise and includes unsuccessful approaches because they show how the implementation evolved.

## 1. Changing CSV columns and file counts

**Problem:** The first ingestion version depended too closely on the supplied column names. A changed header could silently break field access or produce incorrect data.

**Investigation:** I considered relying only on column positions, but that would fail as soon as a source added or reordered a column.

**Decision:** Define required canonical columns and known aliases for each source. Extra columns are accepted, recognized aliases are renamed, and missing required columns stop the run before the database is changed.

**Lesson:** Input contracts should be validated at the boundary, and failures should be explicit rather than silently producing partial data.

## 2. A shifted gig-worker row

**Problem:** One row had valid-looking values shifted into the wrong columns. Treating every column independently would reject useful data; accepting it unchanged would corrupt the database.

**Investigation:** The value in the name column had a valid email structure, and the following values matched the expected name, rate, location, status, and skills pattern.

**Decision:** Repair only this unambiguous structural pattern, then mark the source record with `was_repaired = 1`. Any row that still fails required-field validation is rejected and audited.

**Lesson:** Automatic repair is acceptable only when the rule is narrow, explainable, and traceable.

## 3. Avoiding false duplicate merges

**Problem:** Email and phone are strong identity fields, but some sources do not contain both. Name plus city can help connect records, but it can also merge two different people with common names.

**Decision:** Use normalized email and phone as primary keys. Use name plus city only when that pair does not occur more than once within any source. Resolve transitive matches with union-find and retain all source lineage.

**Lesson:** Deduplication is a risk decision, not just a string-comparison problem. Conservative matching plus auditability is safer than maximizing merge count.

## 4. Making the project runnable without Node.js

**Problem:** The evaluator may not have Node.js installed, while the assignment still requires a no-code workflow.

**Decision:** Keep the application and API in Python, deploy them publicly on Render, and export the n8n workflow as JSON. An evaluator can inspect the workflow in GitHub, import it into n8n, or call the published webhook without installing Node.js locally.

**Lesson:** A reproducible submission should minimize local dependencies and provide both code and a working hosted path.

## 5. Render runtime incompatibility

**Problem:** The audio implementation uses Python's standard-library `audioop`, which is unavailable in Python 3.13 and later. A newer default runtime would make deployment fail even though it worked locally.

**Decision:** Pin Python 3.12 using `.python-version`. This keeps the lightweight WAV implementation reproducible without adding a system-level FFmpeg dependency.

**Trade-off:** For a long-lived production system, replace deprecated `audioop` with a maintained audio-analysis library and update the runtime.

## 6. n8n test webhook returned 404

**Problem:** Calling `/webhook-test/candidate-csv-duplicate-check` returned “webhook is not registered.”

**Cause:** An n8n test webhook is registered for only one request after **Execute workflow** or **Listen for test event** is selected.

**Resolution:** Start the test listener before each test request. After both branches passed, publish the workflow and use the permanent `/webhook/` production URL.

**Lesson:** n8n test and production webhook lifecycles are different and should be tested separately.

## 7. Multipart upload appeared to have an empty body

**Problem:** The Webhook output displayed an empty JSON body, which initially looked as if the CSV had not arrived.

**Cause:** n8n stores multipart files under binary data rather than the JSON body.

**Resolution:** Confirm the binary property was named `data` and configure **Extract from File** to read that property as CSV.

**Lesson:** HTTP metadata, JSON fields, and binary multipart content appear in separate parts of an n8n item.

## 8. “Unused Respond to Webhook node”

**Problem:** The workflow contained two branch-specific response nodes, but n8n reported that Respond to Webhook nodes were unused.

**Cause:** The initial Webhook node still used its default immediate response mode.

**Resolution:** Set the Webhook's Respond option to **Using Respond to Webhook Node**. The true and false IF branches can then each terminate in their own response node.

**Lesson:** Trigger response configuration must agree with downstream response nodes.

## 9. `$json is not defined` in the response expression

**Problem:** The entire workflow reached the duplicate branch, but the response failed while evaluating a spread expression using `$json`.

**Resolution:** Reference the summary node explicitly with `$("Build Summary").first().json` in both response expressions.

**Lesson:** Explicit node references are clearer and more reliable when a node's expression context is restricted or ambiguous.

## 10. Deployment storage behavior

**Problem:** SQLite and uploaded WAV files work on the hosted prototype, but Render's free filesystem is ephemeral.

**Decision:** Clearly document this limitation. The prototype rebuilds candidate data from committed fictional CSVs on startup. A production deployment would use managed PostgreSQL and object storage.

**Lesson:** A successful request does not prove durable storage; persistence has to be designed and tested separately.

## Use of AI tools

AI assistance was used for implementation guidance, debugging, review, and documentation. Every flow was run manually, both n8n branches were tested through HTTP requests, the deployed audio upload was tested end to end, and the Python suite was executed locally. I reviewed the code and can explain the normalization, matching, database, API, n8n, and audio-processing decisions.
