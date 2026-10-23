#!/usr/bin/env python3
"""Checks a business's settings before a demo (DEMO_VERTICAL in demo.env).

1. Thresholds: it scores the test sentences of the business's "calibration"
   block with the gateway's own embeddings model, and proposes, for the
   semantic cache, the topic guard, the prompt guard and semantic routing, the
   value that best separates what must pass from what must not.
2. Budgets: it says how many answers each budget and quota lasts with the
   business's catalogue, so a card still runs out at the right moment.

It changes nothing: copy the values you want into the business's vertical.json.

Usage: python3 scripts/python/calibrate.py
"""
import json
import math
import sys

from platform_api import PROVIDERS, budget_for, provider_key, read_env_file, request, showcase
from target import ROOT, setting
from vertical import VERTICAL_ID, catalogue_path, policy, vertical

# The semantic cache's threshold is not a plain similarity: 0.6 + 0.4 x threshold is.
CACHE_FLOOR, CACHE_SPAN = 0.6, 0.4
# What a typical demo answer writes, in tokens.
ANSWER_TOKENS = 350


def embed(texts: list) -> list:
    """The texts as the gateway's embeddings model sees them."""
    keys = read_env_file(ROOT / "secrets" / "api-keys.env")
    # Without its own key, the embeddings model uses Mistral's.
    key = keys.get("EMBEDDINGS_PROVIDER_API_KEY") or provider_key(next(p for p in PROVIDERS if p["id"] == "mistral"))
    status, body = request("POST", setting("EMBEDDING_ENDPOINT"), {"model": setting("EMBEDDING_MODEL"), "input": texts},
                           {"Authorization": "Bearer " + key})
    if status != 200:
        sys.exit(f"the embeddings model answered {status}: {body}")
    return [item["embedding"] for item in body["data"]]


def cosine(a: list, b: list) -> float:
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def best_match(texts: list, references: list) -> list:
    """How close each text comes to the nearest reference phrase."""
    vectors = embed(texts + references)
    mine, theirs = vectors[:len(texts)], vectors[len(texts):]
    return [max(cosine(v, r) for r in theirs) for v in mine]


def propose(name: str, current: float, low: list, high: list, low_label: str, high_label: str, cache=False):
    """Prints the scores of both groups and the threshold halfway between them."""
    top, bottom = max(low), min(high)
    print(f"\n{name}  (now {current})")
    print(f"  {high_label:<24} {min(high):.3f} .. {max(high):.3f}")
    print(f"  {low_label:<24} {min(low):.3f} .. {max(low):.3f}")
    if top >= bottom:
        print("  OVERLAP: no threshold separates them; reword the phrases or the test sentences")
        return
    middle = (top + bottom) / 2
    proposed = (middle - CACHE_FLOOR) / CACHE_SPAN if cache else middle
    now = CACHE_FLOOR + CACHE_SPAN * current if cache else current
    print(f"  proposed {proposed:.3f}" + ("" if top < now <= bottom else "   (the current value does not separate them)"))


def thresholds():
    c = vertical().get("calibration") or {}
    if not c:
        print("no \"calibration\" block in vertical.json: nothing to measure")
        return
    cache = c["semanticCache"]
    pairs = cache["same"] + cache["different"]
    vectors = embed([t for pair in pairs for t in pair])
    scores = [cosine(vectors[2 * i], vectors[2 * i + 1]) for i in range(len(pairs))]
    same, different = scores[:len(cache["same"])], scores[len(cache["same"]):]
    propose("semantic cache (similarityThreshold)", policy("semanticCache")["threshold"],
            different, same, "different questions", "same question reworded", cache=True)

    topic = c["topicGuard"]
    allowed_phrases = policy("topicGuard")["allowedPhrases"]
    propose("topic guard (allowSimilarityThreshold)", policy("topicGuard")["threshold"],
            best_match(topic["refused"], allowed_phrases), best_match(topic["allowed"], allowed_phrases),
            "off topic", "on topic")

    guard = c["promptGuard"]
    denied = policy("promptGuard")["deniedPhrases"]
    propose("prompt guard (denySimilarityThreshold)", policy("promptGuard")["threshold"],
            best_match(guard["allowed"], denied), best_match(guard["refused"], denied),
            "legitimate", "attacks")

    routing = c["semanticRouting"]
    utterances = policy("semanticRouting")["utterances"]
    propose("semantic routing (scorethreshold)", policy("semanticRouting")["threshold"],
            best_match(routing["simple"], utterances), best_match(routing["deep"], utterances),
            "simple questions", "deep questions")


def prices() -> dict:
    with open(ROOT / "ai-gateway" / "configs" / "llm-pricing" / "model_prices.json") as handle:
        return json.load(handle)


def budgets():
    v = vertical()
    prompt = v["assistant"]["systemPrompt"] + v["assistant"]["catalogueIntro"]
    path = catalogue_path()
    if path:
        with open(path) as handle:
            prompt += handle.read()
    # About four characters a token: close enough to size a budget.
    prompt_tokens = len(prompt) // 4
    table = prices()
    quota = showcase("token-quota").get("quota") or {}
    print(f"\nbudgets  (prompt and catalogue: about {prompt_tokens} tokens, answers of about {ANSWER_TOKENS})")
    for provider in PROVIDERS:
        large = provider["models"]["large"]
        price = table.get(large) or {}
        if "input_cost_per_token" not in price:
            print(f"  {provider['id']:<10} {large}: no price in model_prices.json")
            continue
        answer = prompt_tokens * price["input_cost_per_token"] + ANSWER_TOKENS * price["output_cost_per_token"]
        budget = budget_for(provider)
        print(f"  {provider['id']:<10} {large}: ${answer:.5f} an answer; the ${budget} budget "
              f"(spend limit, cost-based routing) lasts about {budget / answer:.1f} answers")
    if quota.get("tokens"):
        print(f"  token quota: {quota['tokens']} tokens per {quota.get('duration')} last about "
              f"{quota['tokens'] / (prompt_tokens + ANSWER_TOKENS):.1f} answers per customer")


if __name__ == "__main__":
    print(f"business: {VERTICAL_ID} ({vertical()['brand']})")
    thresholds()
    budgets()
