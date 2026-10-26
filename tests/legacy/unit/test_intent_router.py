import pytest
from src.backend.pipeline.intent import IntentRouter, IntentCategory

@pytest.fixture
def router():
    return IntentRouter()

def test_intent_category_command(router):
    command_examples = [
        "set a timer for 5 minutes",
        "calculate 25 plus 17",
        "remind me to call Mom tomorrow",
        "set an alarm for 7 am",
        "turn on the lights",
        "volume up please"
    ]

    for utterance in command_examples:
        res = router.classify(utterance)
        assert res.category == IntentCategory.COMMAND, f"Expected COMMAND for '{utterance}', got {res.category}"
        assert res.confidence >= 0.9
        assert res.matched_rule is not None
        assert res.matched_rule.startswith("command:")

def test_intent_category_knowledge(router):
    knowledge_examples = [
        "According to the policy, what is the sick leave allowance?",
        "Search the documents for the API specification",
        "What does the handbook say about annual leave?",
        "Look up in the manual how to configure the port",
        "Check company policy for expense reimbursements"
    ]

    for utterance in knowledge_examples:
        res = router.classify(utterance)
        assert res.category == IntentCategory.KNOWLEDGE, f"Expected KNOWLEDGE for '{utterance}', got {res.category}"
        assert res.confidence >= 0.9
        assert res.matched_rule is not None
        assert res.matched_rule.startswith("knowledge:")

def test_intent_category_chat_default(router):
    chat_examples = [
        "Hello, how are you doing today?",
        "Tell me a short bedtime story",
        "What is the capital of France?",
        "bhai what is the plan aaj ka?",
        "I am feeling tired after work",
        "Can you recommend a good book?"
    ]

    for utterance in chat_examples:
        res = router.classify(utterance)
        assert res.category == IntentCategory.CHAT, f"Expected CHAT (default) for '{utterance}', got {res.category}"
        assert res.matched_rule is None

def test_intent_empty_input(router):
    res = router.classify("")
    assert res.category == IntentCategory.CHAT

    res_whitespace = router.classify("   ")
    assert res_whitespace.category == IntentCategory.CHAT
