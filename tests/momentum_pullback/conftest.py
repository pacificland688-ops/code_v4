from __future__ import annotations

import pytest

from momentum_pullback.casebook import declare_synthetic_roster, hand_contract, hand_panel
from momentum_pullback.contracts import ROOT, load_contract
from momentum_pullback.features import build_features


@pytest.fixture(scope="session")
def base_contract():
    return load_contract(ROOT / "configs/momentum_pullback/research_contract_v0_2.yaml")


@pytest.fixture(scope="session")
def hand_draft(base_contract):
    return hand_contract(base_contract)


@pytest.fixture(scope="session")
def hand_features(hand_draft):
    panel, calendar = hand_panel()
    return build_features(panel, calendar, hand_draft, roster=declare_synthetic_roster(panel))
