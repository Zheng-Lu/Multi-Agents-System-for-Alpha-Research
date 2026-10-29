# Provider integration

Documentation snapshot: 2026-10-28. **All six adapters tested with mocked HTTP; zero real-provider
inferences tested.** Documentation presence does not establish account access, region support or
model performance. Recheck model IDs/pricing before paid benchmarking.

| Provider | Credential | Default protocol/base | Registry candidate | Official references |
|---|---|---|---|---|
| GLM | ZAI_API_KEY | Chat; https://api.z.ai/api/paas/v4 | glm-4.7 | [API](https://docs.z.ai/api-reference/llm/chat-completion), [pricing](https://docs.z.ai/guides/overview/pricing) |
| DeepSeek | DEEPSEEK_API_KEY | Chat; https://api.deepseek.com | deepseek-flash | [first call](https://api-docs.deepseek.com/quick_start/pricing), [tools](https://api-docs.deepseek.com/guides/tool_calls/) |
| Qwen | DASHSCOPE_API_KEY | Chat; QWEN_BASE_URL required | qwen-plus | [regional endpoints](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope), [tools](https://help.aliyun.com/zh/model-studio/qwen-function-calling) |
| Kimi | MOONSHOT_API_KEY | Chat; https://api.moonshot.ai/v1 | kimi-k3.1-pro | [tools](https://platform.kimi.ai/docs/guide/use-kimi-api-to-complete-tool-calls), [models](https://platform.kimi.ai/docs/models), [pricing](https://platform.kimi.ai/docs/pricing/chat) |
| OpenAI | OPENAI_API_KEY | Responses; https://api.openai.com/v1 | gpt-6-luna | [tools](https://developers.openai.com/api/docs/guides/function-calling), [pricing](https://developers.openai.com/api/docs/pricing) |
| Anthropic | ANTHROPIC_API_KEY | Messages; https://api.anthropic.com/v1 | claude-haiku-5-5 | [model](https://platform.claude.com/docs/en/models/haiku-5-5/overview), [tools](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview), [pricing](https://platform.claude.com/docs/en/about-claude/pricing) |

Base URLs can be overridden with `<PROVIDER>_BASE_URL`, using GLM, DEEPSEEK, QWEN, KIMI, OPENAI
or ANTHROPIC. HTTPS required; configuration is server-side only. Never use coding-subscription
endpoints with general inference keys. No key aliases are recognized.

Qwen's current documentation includes workspace-specific regional hosts. Copy the exact URL
matching the account/key region rather than assuming a universal endpoint. DeepSeek's current
first-call page documents a changed Flash alias; this registry uses that documented name instead
of older names from memory. Kimi's docs distinguish pay-as-you-go inference from Kimi Code and
membership; the selected current tool example avoids a soon-retiring K2 model.

Adapters normalize text, tool call IDs/names/validated argument objects, finish reasons and usage.
Chat function arguments may be a JSON string or object; both are parsed at the boundary. Multiple
calls are executed with independently validated arguments and correctly paired result IDs.
OpenAI resubmits complete response output items with encrypted reasoning continuation; Anthropic
retains signed thinking/tool blocks and groups multiple tool results in one user turn. These opaque
states remain in memory and never enter public artifacts. DeepSeek/GLM Chat reasoning_content is
preserved verbatim between tool turns; it is never shown in the UI.

Reasoning overrides currently validated for GLM and DeepSeek; Qwen translation exists but is not
enabled in its initial model profile. Other overrides reject explicitly. Provider token streaming
is not implemented; `stream=true` rejects. SSE streams execution events, not provider tokens.
GLM/DeepSeek structured text uses JSON mode plus **local JSON Schema validation**. Anthropic
structured-output options are currently rejected. Capability flags describe this runtime's validated
subset, not every capability offered by a vendor. `parallel_tool_calls=null` means unverified.

Registry rows are per model for the server's single configured endpoint. Changing a base URL/region
requires revalidation of that row; multiple endpoints for the same provider in one run are not yet
supported. Add models by editing `config/models.json`. Add providers by registering a translator and
server-side credential profile in `providers/registry.py`; no coordination module needs changes.

Pricing: GLM reference rates are USD $0.60 input / $2.20 output / $0.11 cached input per million,
from the linked pricing page on the snapshot date. OpenAI Standard short-context pricing was added on 2026-10-29; see the
[OpenAI quickstart](openai-quickstart.md). Other fetched tables were missing recoverable
rates or required region/tier assumptions, so their entries remain null. Fill a ModelPricing object
with currency, effective date, rates and source before live execution. Unknown is not zero.
Anthropic cache creation remains incomplete rather than receiving an unvalidated tariff estimate.
Prices and maximum output allowances are conservative configuration snapshots, not billing guarantees.

Router precedence: role override → run default. Explicit per-role fallbacks require
`authorize_fallback_data_transfer=true`; absent that authorization the run rejects. Every fallback
records original and selected identities. No automatic provider/region transfer occurs. Each retry
counts as a call, retains its reservation and produces a distinct invocation record. Unknown usage
on a returned response prevents later paid calls. Failed HTTP attempts leave overall cost incomplete.

Use `scripts/smoke_provider.py --allow-paid ...` for a manually authorized baseline tool-loop test.
A success proves actual tools and usage for that specific model/endpoint; it does not validate all
reasoning modes, schemas or streaming. Update smoke_tested only after recording such evidence.
Ordinary CI exercises only mocked HTTP and deterministic decisions.
