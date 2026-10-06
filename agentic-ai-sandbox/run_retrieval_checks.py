"""Check policy ranking, freshness, provenance, and output minimization."""

from __future__ import annotations

from policy_retrieval import PolicyCatalog
from support_agent import RunContext, ToolRuntime


def main() -> int:
    catalog = PolicyCatalog()
    assert len(catalog.fingerprint()) == 64
    print("PASS  policy catalog has a reproducible SHA-256 fingerprint")
    damaged = catalog.search("The notebook arrived broken on arrival. What is the reporting window?")
    assert damaged and damaged[0]["article_id"] == "DAM-01"
    assert damaged[0]["version"] == "2026.2"
    assert "7 days" in damaged[0]["text"]
    print("PASS  paraphrased damaged-item query ranks the specific current article first")

    delivery = catalog.search("Are delivery estimates guaranteed? Where should I look for updates?")
    assert delivery and delivery[0]["article_id"] == "SHIP-01"
    assert "not guarantees" in delivery[0]["text"]
    print("PASS  delivery-estimate query retrieves the tracking article")

    returns = catalog.search("refunds and return window")
    assert returns and returns[0]["article_id"] == "RET-01"
    assert "30 days" in returns[0]["text"]
    print("PASS  return/refund query retrieves the current policy with a source ID")

    returned_ids = {article["article_id"] for article in returns}
    assert "RET-00" not in returned_ids
    print("PASS  superseded article is excluded from search results")

    result_text = str(damaged)
    assert "untrusted_ingestion_note" not in result_text
    assert "Ignore all rules" not in result_text
    assert "customer-blair" not in result_text
    print("PASS  ingestion-only instruction text and unrelated customer data are not returned")

    assert len(damaged) <= catalog.MAX_RESULTS
    assert all(len(article["text"]) <= catalog.MAX_EXCERPT_CHARS for article in damaged)
    assert all({"article_id", "version", "effective_date", "text"} <= article.keys() for article in damaged)
    print("PASS  results are bounded and carry source version and effective date")

    assert catalog.search("quantum bicycles on Mars") == []
    runtime = ToolRuntime()
    tool_result = runtime.call("search_policy", {"topic": "broken on arrival"}, RunContext("customer-ada", "retrieval"))
    assert tool_result["matches"][0]["article_id"] == "DAM-01"
    print("PASS  irrelevant query returns no match and the tool uses the catalog")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
