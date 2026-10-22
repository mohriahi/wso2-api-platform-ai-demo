# Configuration: demo.env and secrets

The demo reads its settings from two places:

- **`demo.env`**, at the repo root: this machine's settings (name, versions,
  ports, analytics, and how some cards behave). It holds no secrets. The
  scripts create it from `demo.env.example` on the first run, and git ignores
  it, so your changes stay on your machine.
- **`secrets/`**: keys and credentials. Only the templates (`*.example`) are
  in git.

After a change, `./scripts/run-local.sh` applies most settings. Each section
says when another step is needed.

## demo.env

Write comments on their own line: text after a value, on the same line,
becomes part of the value. When `demo.env.example` gains a setting, the
scripts tell you which ones your `demo.env` lacks.

### Name and hostname

| Setting | Default | What it does |
|---|---|---|
| `DEMO_NAME` | `ai-demo` | The demo's name, in lowercase letters and hyphens. It names the custom gateway image and the Docker network of the MCP servers. |
| `DEMO_HOSTNAME` | blank | The server's public hostname, when the demo runs on a VM. The consoles, the launcher's links and the gateway's answers to MCP clients use it. Blank locally: `localhost` is used. |

Set `DEMO_NAME` before the first run. Changing it later means building the
gateway image again with `./scripts/reset-and-setup.sh`, which starts from an
empty state.

### Versions

| Setting | Default | What it does |
|---|---|---|
| `PLATFORM_API_VERSION` | `0.16.0` | The Platform API, AI Workspace's backend. |
| `AI_WORKSPACE_VERSION` | `1.0.0` | AI Workspace, the control plane console. |
| `API_PORTAL_VERSION` | `1.0.0` | The API Portal. It runs, but no card uses it. |
| `AI_GATEWAY_VERSION` | `1.2.0` | The AI Gateway. It must equal `gateway.version` in `ai-gateway/build.yaml`. |

The gateway runs a custom image, with the demo's own policies built in. To
change its version, change both values, then run
`./scripts/reset-and-setup.sh`: it builds the image again, from an empty
state.

With an external registry (`secrets/registry.env`, below), the scripts run the
newest update of each version: for `0.16.0`, the newest `0.16.0.N`.

### Ports

| Setting | Default | What it does |
|---|---|---|
| `AI_CHATBOT_PORT` | `8600` | The chatbot, at http://localhost:8600. If you change it, change the redirect URL in your identity provider too (`http://localhost:<port>/oauth/callback`). |
| `PLATFORM_API_PORT` | `9243` | The Platform API, which the gateway connects to. |
| `AI_WORKSPACE_PORT` | `9643` | AI Workspace, at https://localhost:9643. |
| `API_PORTAL_PORT` | `9543` | The API Portal, at https://localhost:9543/api-portal/. |
| `GATEWAY_PORT_OFFSET` | `0` | Moves all the gateway's ports up by this number, like the port offset of WSO2 products. With `1`, 8443 becomes 8444 and 8080 becomes 8081. For a machine where another program already uses them. The chatbot and the provisioning follow. |

The gateway's own ports are in `ai-gateway/.env`: 8443 (HTTPS), 8080 (HTTP),
9090 (management API) and a few internal ones. Move them with
`GATEWAY_PORT_OFFSET` rather than in that file.

### Analytics

| Setting | Default | What it does |
|---|---|---|
| `ANALYTICS_MODE` | `moesif` | Where the gateway's analytics go. `moesif`: to [Moesif](https://www.moesif.com/), with the Application ID set in `secrets/api-keys.env`; without it, analytics stay off and the scripts say so. `local`: to tools started on this machine and linked in the chatbot's launcher menu: Grafana (port 3000), Jaeger (16686), OpenSearch Dashboards (5601) and Prometheus (9092). |

### How some cards behave

| Setting | Default | What it does |
|---|---|---|
| `PEAK_HOURS` | `13:30-18:00` | The peak hours of the Time-based routing card, as `HH:MM-HH:MM`. During them, even complex questions go to the fast model. |
| `PEAK_TIMEZONE` | `Europe/Paris` | The time zone of `PEAK_HOURS`, as a name from the IANA list: `Europe/London`, `America/New_York`... |
| `RATE_LIMIT_ALGORITHM` | `gcra` | How budgets and rate limits count, for the spend limit, cost-based routing, token quota and MCP rate limit cards. `gcra`: capacity comes back gradually; the cards are tuned for it. `fixed-window`: the count resets at fixed times of the clock, the gateway's default when the setting is absent. |
| `DISABLED_CARDS` | blank | Card ids, comma-separated, shown greyed out and not clickable: for a card whose outside service is down during a live demo. The ids are in `ai-chatbot/showcases.json`, for example `content-safety-bedrock`. Takes effect on the next page load, with no restart. |

`PEAK_HOURS` and `PEAK_TIMEZONE` are written into the card's policy: after a
change, run `./scripts/python/provision_showcases.py`.

For `RATE_LIMIT_ALGORITHM` in production, weigh the choice against performance
and memory use. With several gateways, use a shared Redis backend (in
`ai-gateway/configs/config.toml`), with the same value on every gateway.

### Models the gateway calls itself

Two features call a model of their own, apart from the cards' providers.
`demo.env.example` has one ready block per provider: keep one uncommented. The
block the demo uses comes last.

| Setting | Default | What it does |
|---|---|---|
| `EMBEDDING_PROVIDER`, `EMBEDDING_ENDPOINT`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION` | Mistral's `mistral-embed`, 1024 | The embeddings model of the semantic cards (Semantic caching, Semantic routing, Prompt injection and Topic guardrails). It turns each question into numbers, so the gateway can compare meanings. Blocks for Mistral and Gemini (paid key only: the free quota refuses the gateway's calls at startup); Anthropic has no embeddings model. `EMBEDDING_DIMENSION` is the size of the model's vectors. The cards' similarity thresholds are tuned for Mistral's model. |
| `CLASSIFIER_PROVIDER`, `CLASSIFIER_ENDPOINT`, `CLASSIFIER_MODEL` | Mistral's `ministral-14b-latest` | The model that reads each question and picks the rule in Intelligent routing. Blocks for Mistral, Anthropic and Gemini. `CLASSIFIER_PROVIDER` is `OPENAI` for any OpenAI-compatible API (all three), `AZURE_OPENAI` for Azure OpenAI. When this model fails (wrong key, no quota left), every question takes the backup route. |

For a provider other than Mistral, put its key in `secrets/api-keys.env`:
`EMBEDDINGS_PROVIDER_API_KEY` or `CLASSIFIER_API_KEY`.

### An AI Workspace and a gateway that already run elsewhere

To put the showcases on an existing deployment instead of this machine's
stack. The steps are in the
[README](../README.md#provisioning-onto-an-existing-ai-workspace-and-gateway).

| Setting | Default | What it does |
|---|---|---|
| `REMOTE_AI_WORKSPACE_URL` | blank | AI Workspace's address, for example `https://workspace.example.com:9643`. When set, the provisioning and the chatbot use that deployment. |
| `REMOTE_GATEWAY_ID` | blank | The gateway's id in that AI Workspace. |
| `REMOTE_GATEWAY_URL` | blank | The gateway's address, for example `https://gateway.example.com:8443`. |
| `REMOTE_ADMIN_USERNAME` | `admin` | The admin user of that AI Workspace. Its password goes in the environment (see below). |
| `REMOTE_PROJECT_ID` | `default` | The AI Workspace project the showcases go in. |
| `REMOTE_GATEWAY_CONTROLLER_URL` | blank | Optional: the gateway's management API, for example `http://gateway.example.com:9090`. Deployments are then checked there, without test requests that would show in analytics. |
| `REMOTE_MCP_GATEWAY_ID`, `REMOTE_MCP_GATEWAY_URL`, `REMOTE_MCP_GATEWAY_CONTROLLER_URL` | blank | Another gateway for the MCP cards, already registered in AI Workspace. Works with this machine's stack too. |

A `demo.env` written with the earlier names (`AIW_URL`, `GATEWAY_ID`...)
still works: the README lists them.

## Secrets

Each file in `secrets/` comes with a template, `<file>.example`. Copy it
without `.example`, then fill it in. Git ignores the copies, so your keys never
reach the repository. Only `api-keys.env` is required.

After a change, run `./scripts/run-local.sh`, then
`./scripts/python/provision_showcases.py`: a card whose key or service was
missing stays skipped until then.

### secrets/api-keys.env (required)

```bash
cp secrets/api-keys.env.example secrets/api-keys.env
```

| Key | What it is for | How to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude models | In the [Claude Console](https://platform.claude.com/settings/keys), create a key. The account needs credit. |
| `MISTRAL_API_KEY` | Mistral models, and by default the embeddings and Intelligent routing's classifier | In the [Mistral console](https://console.mistral.ai/api-keys), create a key. A free plan is enough. |
| `GEMINI_API_KEY` | Gemini models | In [Google AI Studio](https://aistudio.google.com/apikey), create a key. The free tier allows about 20 requests per model per day, which a few cards use up: turn billing on for the key's project. |
| `EMBEDDINGS_PROVIDER_API_KEY` | The embeddings model chosen in `demo.env` | Blank for Mistral: `MISTRAL_API_KEY` is used. For Gemini, your Gemini key. |
| `CLASSIFIER_API_KEY` | Intelligent routing's classifier chosen in `demo.env` | Blank for Mistral: `MISTRAL_API_KEY` is used. For Anthropic or Gemini, that provider's key. |
| `APIP_GW_ANALYTICS_PUBLISHERS_MOESIF_APPLICATION_ID` | Analytics, with `ANALYTICS_MODE=moesif` | Create a [Moesif](https://www.moesif.com/) account, then in Moesif: *Settings*, *API Keys*, the Application ID. Blank: analytics stay off. |

You need at least one provider key. The demo is tested with Anthropic (paid
credit) and Mistral (a free key), the combination we recommend; Intelligent
routing needs both. A provider without a key is skipped. To leave one out for
everyone, set `"enabled": false` on it in `providers.json`.

### secrets/content-safety.env (optional)

For the cards whose policy calls an outside service. When a service is left
blank, its cards are skipped and the chatbot says what to set.

```bash
cp secrets/content-safety.env.example secrets/content-safety.env
```

| Key | Card | How to get it |
|---|---|---|
| `AZURE_CONTENT_SAFETY_ENDPOINT`, `AZURE_CONTENT_SAFETY_KEY` | Content safety (Azure) | Create an [Azure AI Content Safety resource](https://aka.ms/acs-create). In the Azure portal, open it, then *Keys and Endpoint*: the endpoint, and either key. |
| `AWS_BEDROCK_REGION`, `AWS_BEDROCK_GUARDRAIL_ID`, `AWS_BEDROCK_GUARDRAIL_VERSION` | Content safety (AWS Bedrock), not tested yet | Create a [guardrail](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html) in the Amazon Bedrock console. Its region (for example `eu-west-1`), its ID, shown on its page, and its version: `DRAFT` for the working draft, or a published version's number. |
| `AWS_BEARER_TOKEN_BEDROCK` | Content safety (AWS Bedrock) | A [Bedrock API key](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html), created in the Bedrock console. Or, instead, an IAM user's access key pair in `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, allowed to apply the guardrail (`bedrock:ApplyGuardrail`). |
| `TYPESAFE_API_KEY` | The five Jev cards | Create a key on [TypeSafe AI's console](https://console.typesafe.ai/keys). |

### secrets/idp.env (optional)

For the MCP Authentication and Authorization cards: an OpenID Connect identity
provider (Asgardeo, WSO2 Identity Server or any other). How to set it up:
[IDP Setup](mcp-identity-provider.md).

| Key | What it is |
|---|---|
| `IDP_ISSUER` | The issuer the provider writes in its tokens. |
| `IDP_JWKS_URI` | Where the gateway fetches the provider's signing keys. For a provider on this machine, write `host.docker.internal` instead of `localhost`. |
| `IDP_CLIENT_ID` | The client ID of the application the demo signs users in with. |
| `IDP_CONSOLE_URL` | Optional: the provider's console, listed in the chatbot's launcher menu. |

Both URLs are in the provider's `<issuer>/.well-known/openid-configuration`.

### secrets/registry.env (optional)

To run the newest product updates from an external registry instead of the
public images.

| Key | What it is |
|---|---|
| `USE_EXTERNAL_REGISTRY` | `true` to use the registry below, `false` for the public images. |
| `EXTERNAL_REGISTRY_URL` | The registry and the path to the images, without `https://`. WSO2's: `registry.wso2.com/wso2-api-platform`. |
| `EXTERNAL_REGISTRY_USERNAME`, `EXTERNAL_REGISTRY_TOKEN` | Your account on that registry, and its token or password. WSO2's registry needs a WSO2 subscription. |

Then run `./scripts/reset-and-setup.sh`: it rebuilds the gateway on those
images, from an empty state.

### secrets/gateway-keys.env (written for you)

The keys the gateway issues for each card, one per card and provider.
`provision_showcases.py` writes this file: leave it alone, unless you set up
the cards by hand in AI Workspace. A card without its key still shows, but the
gateway refuses its messages.

### Passwords, in the environment only

Never write these in a file:

- `ADMIN_PASSWORD`: the password of AI Workspace's `admin` user on this
  machine. `reset-and-setup.sh` asks you to choose it on the first run. The
  other scripts log in as `admin`/`admin` unless you set it, for example
  `ADMIN_PASSWORD='...' ./scripts/python/provision_showcases.py`.
- `REMOTE_ADMIN_PASSWORD`: the admin password of the AI Workspace in
  `REMOTE_AI_WORKSPACE_URL`: `export REMOTE_ADMIN_PASSWORD='...'`.

### Filled in by the scripts

`ai-workspace/api-platform.env` and `ai-gateway/api-platform.env` also hold
credentials, written by the scripts: the admin password hashes
(`scripts/generate-local-certs.sh`) and the gateway's registration token (the
provisioning, when it registers the gateway). `reset-and-setup.sh` creates both
files: there is nothing to get or edit for a local run.
