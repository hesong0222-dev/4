#!/usr/bin/env python3
"""Final attack-density calibration wrapper.

Captures the base calibration function before importing v2, avoiding recursive
monkey-patching while reusing the validated attack-density analyzers.
"""
from __future__ import annotations
import analyze_expression_corpora as core
BASE_CALIBRATION = core.calibration
import run_expression_calibration_v2 as v2

def calibration(gmd, asap, ep, pop):
    out = BASE_CALIBRATION(gmd, asap, ep, pop)
    out['calibration_version'] = 'empirical-2026-08-28.2-attack-density'
    out['fast_passage_reference'] = {
        'density_semantics': 'attack/onset groups per second; simultaneous chord tones count once',
        'asap_local_attack_density_hz': asap['local_attack_density_hz'],
        'e_piano_max_local_attack_density_hz_advisory': ep['max_local_attack_density_hz'],
        'pop909_max_local_attack_density_hz_structural': pop['max_local_attack_density_hz'],
        'planner_rule': 'use empirical piano density bins plus an event-order safety cap',
    }
    out['piano']['density_semantics'] = asap['density_semantics']
    return out

core.greedy_match = v2.greedy_match
core.analyze_asap = v2.analyze_asap
core.generic_performance_stats = v2.generic_performance_stats
core.analyze_pop909 = v2.analyze_pop909
core.calibration = calibration

if __name__ == '__main__':
    core.main()
