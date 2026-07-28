import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/pauta-propiedades")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import build_data


def test_event_metrics_from_actions():
    actions = [{"action_type": "link_click", "value": "10"},
               {"action_type": "offsite_conversion.custom.999", "value": "7"}]
    cpa_rows = [{"action_type": "offsite_conversion.custom.999", "value": "2.5"}]
    ev, cpa = build_data.event_metrics(actions, cpa_rows, spend=17.5)
    assert ev == 7
    assert cpa == 2.5


def test_event_metrics_none_when_absent():
    ev, cpa = build_data.event_metrics([], [], spend=10)
    assert ev == 0 and cpa == 0.0
