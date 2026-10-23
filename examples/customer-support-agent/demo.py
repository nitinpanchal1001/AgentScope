import os
import time

from agentscope import AgentScope, default_redaction

client = AgentScope(
    api_key=os.environ["AGENTSCOPE_API_KEY"],
    endpoint=os.getenv("AGENTSCOPE_ENDPOINT", "http://localhost:8000"),
    processors=default_redaction(),
    batch_size=10,
    flush_interval=1,
)


@client.trace(name="customer-support-agent", agent_version="demo-v1", tags=["demo"])
def answer_customer(message: str) -> str:
    with client.span(name="retrieve-policy", span_type="retrieval", input={"query": message}) as span:
        time.sleep(0.01)
        policy = {"returns": "Returns are accepted within 30 days."}
        span.set_output(policy)

    with client.span(
        name="draft-response",
        span_type="llm",
        provider="simulated",
        model="deterministic-demo",
        input={"message": message, "context": policy},
    ) as span:
        response = f"Thanks for contacting us. {policy['returns']}"
        span.set_output(response)

    with client.span(name="record-resolution", span_type="tool") as span:
        result = {"recorded": True}
        span.set_output(result)
    return response


if __name__ == "__main__":
    print(answer_customer("Can I return my order?"))
    client.close()
