from pce.retrieval.fusion import reciprocal_rank_fusion


def test_item_ranked_first_in_both_lists_wins():
    fused = reciprocal_rank_fusion([["a", "b", "c"], ["a", "c", "b"]])
    assert fused[0][0] == "a"


def test_item_present_in_both_lists_beats_item_in_only_one():
    # "a" shows up in both lists (rank 2 then rank 1); "x" and "y" each show
    # up in only one list. Accumulating across lists should beat either.
    fused = dict(reciprocal_rank_fusion([["x", "a"], ["a", "y"]]))
    assert fused["a"] > fused["x"]
    assert fused["a"] > fused["y"]


def test_empty_rankings_produce_no_results():
    assert reciprocal_rank_fusion([]) == []
    assert reciprocal_rank_fusion([[], []]) == []
