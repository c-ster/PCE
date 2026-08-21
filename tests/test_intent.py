from pce.router.intent import Intent, classify_intent


def test_prd_fiction_example():
    assert classify_intent("Rewrite this chapter in my voice.") == Intent.FICTION_WRITING


def test_prd_business_example():
    assert classify_intent("What did we commit to this customer?") == Intent.BUSINESS_WRITING


def test_ip_research():
    assert classify_intent("Is there any prior art for this invention?") == Intent.IP_RESEARCH


def test_decision_history():
    assert classify_intent("Why did we decide to reject that approach?") == Intent.DECISION_HISTORY


def test_neutral_query_falls_back_to_general():
    assert classify_intent("banana bread recipe ratios") == Intent.GENERAL


def test_empty_query_falls_back_to_general():
    assert classify_intent("") == Intent.GENERAL


def test_case_insensitive():
    assert classify_intent("REWRITE THIS CHAPTER IN MY VOICE") == Intent.FICTION_WRITING
