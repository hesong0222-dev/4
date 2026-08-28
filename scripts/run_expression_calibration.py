#!/usr/bin/env python3
from __future__ import annotations
import bisect
from collections import defaultdict
import analyze_expression_corpora as core

def greedy_match(score_notes, perf_notes, score_beats, perf_beats, tol=.22):
    by_pitch=defaultdict(list)
    for i,n in enumerate(perf_notes):
        by_pitch[n['pitch']].append((n['start'],i,n))
    pitch_times={p:[x[0] for x in arr] for p,arr in by_pitch.items()}
    used=set(); matches=[]
    for sn in sorted(score_notes,key=lambda x:(x['start'],x['pitch'])):
        target=core.interp(score_beats,perf_beats,sn['start'])
        if target is None: continue
        arr=by_pitch.get(sn['pitch'],[]); ts=pitch_times.get(sn['pitch'],[])
        j=bisect.bisect_left(ts,target); cand=[]
        for k in (j-2,j-1,j,j+1,j+2):
            if 0<=k<len(arr) and arr[k][1] not in used: cand.append(arr[k])
        if not cand: continue
        best=min(cand,key=lambda x:abs(x[0]-target))
        if abs(best[0]-target)<=tol:
            used.add(best[1]); matches.append((sn,best[2],target))
    return matches

core.greedy_match=greedy_match
if __name__=='__main__': core.main()
