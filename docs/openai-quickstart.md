# Use the lab with OpenAI

Prepared 2026-10-29. The native Responses adapter and role-level configuration already exist.
The `gpt-6-luna` profile now includes dated Standard pricing. Live baseline validation succeeded
on 2026-10-29: 7 model calls, 11 tool calls, an estimated $0.00212379, and a persisted report.
See the [validation record](samples/openai-live-smoke.json). Pattern-specific live validation for
Generator–Verifier and Orchestrator–Subagent is still pending.

1. Open the repository's `.env` locally. It is ignored by Git. Set:

   ```dotenv
   OPENAI_API_KEY=your-real-key-here
   ALPHA_ALLOW_LIVE=true
   ```

   Create a key in your [OpenAI project](https://platform.openai.com/api-keys) with access to
   Responses and the configured model. Keep the key on the backend; do not paste it in chat.
   Leave OPENAI_BASE_URL unset for the global default https://api.openai.com/v1.

2. Run the bounded smoke test from the repository root:

   ```sh
   export PATH="$PWD/.venv/bin:$PWD/.tools/node-v22.16.0-darwin-x64/bin:$PATH"
   uv run python scripts/smoke_provider.py --allow-paid \
     --provider openai --model gpt-6-luna --max-cost 0.02 --max-output-tokens 4096
   ```

   This executes the baseline with real tool calls over synthetic data. Retries are disabled.
   It writes `alpha-smoke.db` and reports the final status and usage. The $0.02 limit is a
   conservative estimated allowance, not a guaranteed billing limit. A failed configuration
   makes no inference calls. Model access/billing errors require an account-side correction.

3. Start or restart the app to load your environment and refreshed registry:

   ```sh
   make demo
   ```

   Open http://127.0.0.1:8000. Expand **Model assignments**, choose the **OpenAI · Standard pricing**
   preset, and use **Single Agent** for the first experiment. The preset selects Live Mode and
   assigns OpenAI to all roles. Choose other implemented patterns after the baseline works.
   The default UI cost allowance is $0.10; lower it under Execution budget if desired.

The [model page](https://developers.openai.com/api/docs/models/gpt-6-luna) lists Standard short-context
USD rates per million tokens: $0.10 input, $0.50 output, $0.01 cached input. The adapter explicitly
requests `service_tier=default` so project Fast settings do not silently change the requested tier.
A reported different tier makes cost accounting incomplete and stops subsequent inference.
These rates exclude regional uplifts, long-context rates and cache-write charges. This initial
profile is for the global endpoint and small prompts; review rates for other configurations.
[Service-tier reference](https://developers.openai.com/api/reference/cli/resources/responses/methods/create).

Do not mark smoke_tested true merely after entering a key. First inspect a successful run's tool
artifacts, served model, usage, cost completeness and report. Demo Mode continues to use MockProvider
and makes no paid calls even when OpenAI credentials are configured.


The first real run exposed an assignment scope mismatch; a subsequent run reached its conservative
token allowance. The runtime now narrows factor schemas per assignment and compacts completed
assignments into evidence-backed memory. Full outputs remain stored; provider continuation state
stays intact within each active tool loop. No budget was increased for the successful validation.
