import pytest

from glint.beliefs import Beliefs
from glint.history import BeliefRevision

REVISIONS = [
    BeliefRevision({}, {1: "The user likes films.", 2: "Most films are rated G."}),
    BeliefRevision({2: "Most films are rated G."}, {3: "Few films are rated G."}),
]


def test_beliefs():
    beliefs = Beliefs(REVISIONS)
    assert beliefs.current == {1: "The user likes films.", 3: "Few films are rated G."}
    assert beliefs.next_number == 4


def test_beliefs_none_yet():
    beliefs = Beliefs()
    assert beliefs.current == {}
    assert beliefs.next_number == 1


def test_numbers_are_not_reused():
    beliefs = Beliefs(REVISIONS)
    beliefs.apply(BeliefRevision({3: "Few films are rated G."}, {}))
    assert beliefs.next_number == 4  # 3 was dropped, but was given


def test_dropping_a_belief_not_held():
    beliefs = Beliefs(REVISIONS)
    with pytest.raises(ValueError):
        beliefs.apply(BeliefRevision({2: "Most films are rated G."}, {}))
