# Configuring the demo

**Nothing to configure for a first run, apart from one API key.** Everything
else on this page is optional: use it to turn on more cards, or to adapt the
demo to your machine.

There are two places:

- **Your keys** go in the `secrets/` folder. Each file there has a template
  ending in `.example`: copy it without `.example`, then fill it in. Your
  copies stay on your machine and never reach git.
- **The demo's options** go in `demo.env`, at the root of the repo. The setup
  creates it for you on the first run, with values that work as they are.

After any change, restart the demo with `./scripts/run-local.sh`. When a
change adds cards (a new key, for example), also run
`./scripts/python/provision_showcases.py`, which sets them up.

## 🔑 Keys and accounts

### 1. REQUIRED - LLM Providers Key

File: `secrets/api-keys.env`

```bash
cp secrets/api-keys.env.example secrets/api-keys.env
```

Paste in at least one key. Each provider you add a key for gets its own
version of every card; a provider left blank is simply skipped.

| Provider | Line to fill in | Where to get the key |
|---|---|---|
| Anthropic (Claude) | `ANTHROPIC_API_KEY` | [Claude Console](https://platform.claude.com/settings/keys). The account needs credit. |
| Mistral | `MISTRAL_API_KEY` | [Mistral console](https://console.mistral.ai/api-keys). A free plan is enough. |
| Gemini | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey). Turn billing on: the free tier allows only about 20 requests per model per day. |

Gemini is left out by default: to use it, take it out of `DISABLED_PROVIDERS`
in `demo.env`.

We recommend **Anthropic and Mistral together**: it is the combination the
demo is tested with. Mistral matters even if you mostly show another
provider: the gateway uses a Mistral model of its own to understand the
meaning of questions (Semantic caching, the meaning-based guards, Semantic
and Intelligent routing). Intelligent routing also needs the Anthropic key.

Leave `EMBEDDINGS_PROVIDER_API_KEY` and `CLASSIFIER_API_KEY` blank: they are
only needed if you change those Mistral models to another provider (see
[The models the gateway uses itself](#the-models-the-gateway-uses-itself)).

### 2. (Optional) Analytics (Moesif)

What for: see every call through the gateway, its cost and its tokens, in
[Moesif](https://www.moesif.com/)'s dashboards.

1. Create a Moesif account.
2. In Moesif, open *Settings*, then *API Keys*, and copy the Application ID.
3. Paste it in `secrets/api-keys.env`, on the
   `APIP_GW_ANALYTICS_PUBLISHERS_MOESIF_APPLICATION_ID` line.

Without it, the demo runs without analytics. To use tools on your own machine
instead of Moesif, see [Analytics](#analytics).

### 3. (Optional) Third-party cards (Azure, AWS, Jev)

What for: the cards whose check is done by an outside service. Each service
is independent: fill in only the ones you have. Until a service is set, its
cards are skipped and the chatbot says what is missing.

File: `secrets/content-safety.env`

```bash
cp secrets/content-safety.env.example secrets/content-safety.env
```

**Content safety (Azure)**, which refuses violent or hateful messages:

1. Create an [Azure AI Content Safety resource](https://aka.ms/acs-create).
2. In the Azure portal, open it, then *Keys and Endpoint*.
3. Copy the endpoint into `AZURE_CONTENT_SAFETY_ENDPOINT`, and one of the two
   keys into `AZURE_CONTENT_SAFETY_KEY`.

**Content safety (AWS Bedrock)**, the same with an AWS guardrail (this card
has not been tested yet):

1. In the Amazon Bedrock console, create a
   [guardrail](https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-components.html).
2. Fill in its region (`AWS_BEDROCK_REGION`, for example `eu-west-1`), its ID,
   shown on its page (`AWS_BEDROCK_GUARDRAIL_ID`), and its version
   (`AWS_BEDROCK_GUARDRAIL_VERSION`: keep `DRAFT`, or the number of a
   published version).
3. Create a [Bedrock API key](https://docs.aws.amazon.com/bedrock/latest/userguide/api-keys.html)
   and paste it into `AWS_BEARER_TOKEN_BEDROCK`. Instead, you can use an IAM
   user's access key pair (`AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`),
   allowed to apply the guardrail.

**The five Jev cards** (TypeSafe AI's Jev, which judges what a message is
trying to do):

1. Create a key on [TypeSafe AI's console](https://console.typesafe.ai/keys).
2. Paste it into `TYPESAFE_API_KEY`.

### 4. (Optional) Authentication for MCP (IDP)

What for: the MCP Authentication and Authorization cards, where the user signs
in before the agent may use its tools. They need an identity provider, such as
Asgardeo or WSO2 Identity Server.

File: `secrets/idp.env`. The full steps, from creating the application to
filling in the file, are in [Identity provider setup](mcp-identity-provider.md).

### 5. (Optional) Remote registry

What for: run the products' images from a private or remote Docker registry,
for example one with newer updates, instead of the public images.

File: `secrets/registry.env`

```bash
cp secrets/registry.env.example secrets/registry.env
```

1. Set `USE_EXTERNAL_REGISTRY=true`.
2. In `EXTERNAL_REGISTRY_URL`, write the registry's address and the path to
   the images, without `https://`: for example
   `registry.example.com/api-platform`.
3. Fill in your account on that registry: `EXTERNAL_REGISTRY_USERNAME`, and
   its token or password in `EXTERNAL_REGISTRY_TOKEN`.
4. Run `./scripts/reset-and-setup.sh`. It starts the demo again from an empty
   state, on those images.

For each product, the demo runs the newest update the registry has of the
version set in `demo.env`: for `1.0.0`, the newest `1.0.0.N`. It looks among
the long-term support (LTS) releases first, then among the short-term support
(STS) ones, in the `sts/` folder. A version found in neither runs from its
public image. To go back to the public images, set
`USE_EXTERNAL_REGISTRY=false` and run `./scripts/reset-and-setup.sh` again.

### Passwords

The demo never stores passwords in a file. The first run of
`./scripts/reset-and-setup.sh` asks you to choose one for AI Workspace's
`admin` user. If it is not `admin`, give it to the scripts that need it:

```bash
ADMIN_PASSWORD='your-password' ./scripts/python/provision_showcases.py
```

### Files you don't need to touch

- `secrets/gateway-keys.env`: the keys the chatbot uses to call each card on
  the gateway. The setup writes them.
- `ai-workspace/api-platform.env` and `ai-gateway/api-platform.env`: the setup
  creates them and fills them in.

## ⚙️ The demo's options

All in `demo.env`. The defaults work: change a value only for the cases below.

### The business the demo plays

The same cards play a bank or a mobile operator:

```
DEMO_VERTICAL=bank    # Acme Bank, the default
DEMO_VERTICAL=telco   # Acme Mobile
```

Then run `./scripts/run-local.sh`. Each business has its own project in AI
Workspace and its own routes on the gateways (`/telco/...`, `/bank/...`), so
both can stay in place side by side. The first time a business is chosen, it
is set up (a few minutes); after that, switching takes about half a minute.

To show the business under another name, such as a customer's, set
`DEMO_BRAND` in `demo.env`: the page, the cards and the assistant use it, and
the gateway does not change.

Each business is a folder of `verticals/`:

- `vertical.json`: its brand and colours, its assistant, its customer, its
  MCP tools and agents, and the words the gateway's rules work with (allowed
  topics, routing examples, personal data patterns, thresholds);
- `catalogue.md`: the products the assistant talks about;
- `cards.json`: how its cards are worded: the questions, the expected answers
  and the notes. `ai-chatbot/showcases.json` holds every card with Acme
  Mobile's wording too: the template a new business starts from.

To add a business, copy a folder and rewrite it. Then check it with
`python3 scripts/python/calibrate.py`: it proposes the thresholds that suit
its wording, and says how many answers each budget lasts with its catalogue.

### The gateway's ports are already in use

If another program on your machine already uses the gateway's ports (8443,
8080...), set:

```
GATEWAY_PORT_OFFSET=1
```

Every gateway port then moves up by one (8443 becomes 8444), like the port
offset of WSO2 products. The chatbot follows by itself.

Before the first run, `demo.env` does not exist yet: create it first with
`cp demo.env.example demo.env`.

### Analytics

`ANALYTICS_MODE` chooses where the gateway's analytics go:

- `moesif` (the default): to Moesif, once its Application ID is set (see 2.).
- `local`: to tools started on your machine, linked in the chatbot's top
  menu: Grafana (dashboards), Jaeger (the path of each request), OpenSearch
  Dashboards (the gateway's logs) and Prometheus (raw metrics).

### Peak hours of the Time-based routing card

During peak hours, even complex questions go to the fast model. Set the hours
and their time zone:

```
PEAK_HOURS=13:30-18:00
PEAK_TIMEZONE=Europe/Paris
```

Then run `./scripts/python/provision_showcases.py`.

### Hide a card during a live demo

If the outside service of a card is down while you present, grey the card out:

```
DISABLED_CARDS=content-safety,content-safety-bedrock
```

Card ids are listed in `ai-chatbot/showcases.json`. This takes effect when
the page is reloaded, without a restart.

### Hide a whole row of cards

To leave a theme out of your demo, for example the EU AI Act row when your
audience is outside Europe, hide its row:

```
DISABLED_GROUPS=compliance-eu-ai-act
```

Rows are named by their id, separated by commas: `routing-and-resilience`,
`cost-and-performance`, `safety`, `identity`, `tool-governance`,
`third-party-policies`, `agent-governance`, `owasp-llm`, `owasp-agentic`, `compliance-eu-ai-act`
and `baseline` (the `groups` list of `ai-chatbot/showcases.json`). A card
that also belongs to another row stays there. This takes effect when the page
is reloaded, without a restart.

### Show the "Ask without the policy" button

On the LLM cards, this button sends the last question again through the
gateway with none of the card's policies, so the audience sees the difference.
It is hidden by default. To show it:

```
POLICY_COMPARISON_ENABLED=true
```

This takes effect when the page is reloaded, without a restart.

### Turn on the A2A Gateway page (STS)

A third page where the assistant hands the customer's question to another
agent, through the gateway. It is off by default:

```
A2A_ENABLED=true
```

A2A needs a newer gateway than the main one, so the page comes with a gateway
of its own: the same definition and settings as the main one, on the version in
`A2A_GATEWAY_VERSION`, started next to it. The main gateway is not touched.

That version, 2026.10.0, is a short-term support (STS) release: WSO2
publishes it only on its private registry. Fill in `secrets/registry.env`
first (see [Remote registry](#5-optional-remote-registry)), which also takes
the other products from that registry. Without a WSO2 account, set
`A2A_GATEWAY_VERSION=2026.09.24`, which is public: the page then runs without
the **Jev between agents** card, which needs 2026.10.0. After the change, run
`./scripts/run-local.sh`, then
`./scripts/python/provision_showcases.py a2a-agent a2a-guardrail` the first
time, which deploys the agents on that gateway. Its ports are one above the
main gateway's: 8444 and 9091 by default (HTTPS and management API).

### How budgets and rate limits refill

`RATE_LIMIT_ALGORITHM` decides how the spend limit, cost-based routing, token
quota and MCP rate limit cards count:

- `gcra` (the demo's choice): capacity comes back gradually. The cards are
  tuned for it.
- `fixed-window`: the count resets at fixed times of the clock.

In production, weigh this choice against performance and memory use. With
several gateways, a shared Redis is recommended, with the same choice on each.

### The models the gateway uses itself

Besides the models that answer the customer, the gateway calls two models of
its own. Both are Mistral's by default. `demo.env` has a ready block for each
provider: comment out the Mistral one and uncomment the one you want.

- **Embeddings** (`EMBEDDING_*`): turn each question into numbers, so the
  gateway can compare meanings. Used by Semantic caching, Semantic routing
  and the meaning-based guards. Possible: Mistral or Gemini (paid key only).
  Anthropic has none. The cards' thresholds are tuned for Mistral's model.
- **Classifier** (`CLASSIFIER_*`): reads each question and picks the rule in
  Intelligent routing. Possible: Mistral, Anthropic or Gemini. If it fails
  (wrong key, no quota left), every question goes to the backup route.

For a provider other than Mistral, put its key in `secrets/api-keys.env`:
`EMBEDDINGS_PROVIDER_API_KEY` for the embeddings, `CLASSIFIER_API_KEY` for the
classifier.

When the embeddings model does not answer, the meaning-based cards fail and
the chatbot says why: a guard blocks every question to be safe, and a card the
gateway could not set up answers 500. Once the model answers again, deploy
those cards again, for the business in `demo.env`:

```
python3 scripts/python/provision_showcases.py prompt-injection topic-guardrail semantic-routing mistral-prompt-injection mistral-topic-guardrail mistral-semantic-routing
```

The provisioning deploys them one after the other. A gateway restart sets them
all up at once, which can go over the model's rate limit.

### Change the models that answer

The LLM providers and their models are in `providers.json`, at the root of
the repo. Each provider has a `small` and a `large` model: the routing cards
move traffic between the two, the other cards use one of them. The spend
limit and cost-based routing also need the model's price in
`ai-gateway/configs/llm-pricing/model_prices.json`.

After changing a model, run `./scripts/run-local.sh`, then
`./scripts/python/provision_showcases.py`.

To leave a provider out on this machine, list it in `DISABLED_PROVIDERS` in
`demo.env` (Gemini, by default; Anthropic cannot be left out). To leave it
out for everyone, set `"enabled": false` on it. Then run
`./scripts/run-local.sh`: a few minutes when a provider comes back.

### Use an AI Workspace and a gateway that already run elsewhere

To put the cards on an existing deployment instead of your machine:

1. In `demo.env`, uncomment and fill in `REMOTE_AI_WORKSPACE_URL`,
   `REMOTE_GATEWAY_ID` and `REMOTE_GATEWAY_URL`.
2. Give the admin password for this session only, never in a file:
   `export REMOTE_ADMIN_PASSWORD='...'`.
3. Check what would change, without changing anything:
   `./scripts/python/provision_showcases.py --check`.
4. Set up the cards: `./scripts/python/provision_showcases.py`. Add
   `--skip-existing` to only create what is missing.

The chatbot then uses that gateway. The scripts never register, rename or
restart it. The cards that need keys from 3. or 4. also need those
settings on that gateway.

Optional, in `demo.env`: `REMOTE_ADMIN_USERNAME` if the admin is not `admin`,
and `REMOTE_GATEWAY_CONTROLLER_URL` (the gateway's management API) to check
deployments without test calls that would show in analytics. The
`REMOTE_MCP_GATEWAY_*` lines send the MCP cards to another gateway.

### Settings you normally leave alone

- `DEMO_NAME`: the demo's name, used to name the custom gateway image. Set it
  before the first run, if at all.
- `DEMO_HOSTNAME`: only when the demo runs on a server: its public name.
  Blank on your machine.
- The versions (`AI_GATEWAY_VERSION` and the others): which product versions
  run. The gateway's must match `ai-gateway/build.yaml`, and a change needs
  `./scripts/reset-and-setup.sh`, which starts from an empty state.
- The ports of the chatbot (8600), AI Workspace (9643), the Platform API
  (9243) and the API Portal (9543). If you change the chatbot's, change the
  redirect URL in your identity provider too.
