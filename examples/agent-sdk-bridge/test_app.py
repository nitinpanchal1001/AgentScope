from app import _message, _spans, _usage


def test_message_accepts_agent_scope_input_shapes() -> None:
    assert _message({"message": "hello"}) == "hello"
    assert _message({"query": "find this"}) == "find this"
    assert _message("plain") == "plain"


def test_events_map_to_usage_and_tool_spans() -> None:
    events = [
        {
            "type": "actions.requested",
            "data": {
                "calls": [
                    {
                        "callId": "call-1",
                        "toolName": "search_faq",
                        "args": {"query": "returns"},
                    }
                ]
            },
        },
        {
            "type": "action.result",
            "data": {
                "callId": "call-1",
                "toolName": "search_faq",
                "input": {"query": "returns"},
                "result": {"matches": 1},
                "isError": False,
            },
        },
        {
            "type": "turn.completed",
            "data": {"usage": {"inputTokens": 12, "outputTokens": 8}},
        },
    ]
    assert _usage(events) == {
        "input_tokens": 12,
        "output_tokens": 8,
        "total_tokens": 20,
        "total_cost": 0,
    }
    spans = _spans(events, "returns", "30 days")
    assert spans[1]["name"] == "search_faq"
    assert spans[1]["input"] == {"query": "returns"}
    assert spans[1]["status"] == "SUCCESS"
