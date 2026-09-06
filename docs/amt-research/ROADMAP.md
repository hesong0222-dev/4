# 독립 악기별 Specialist AMT 전체 연구 로드맵

```mermaid
flowchart TD
    A[최종 목표: 정상 실제 음악 Multi-Instrument AMT SOTA] --> B[EXP01 Bass Specialization Pilot]
    B --> B0[M0 Base]
    B --> B1[C1 General Continued]
    B --> B2[M1 Bass Normal Specialist]
    B --> B3[M2 Bass TPCR]

    B0 --> C{EXP01 결과}
    B1 --> C
    B2 --> C
    B3 --> C

    C -->|M1 > C1| D[Specialization-specific signal]
    C -->|M1 ≈ C1| E[Continued-training 효과 재검토]
    C -->|M1 < C1| F[학습법/데이터/망각 원인 분석]

    D --> G{M2 > M1 ?}
    G -->|정상 F1↑ + CPD/CIPD↓| H[TPCR strong signal]
    G -->|정상 F1≈ + robustness↑| I[TPCR robustness-only]
    G -->|정상 F1↑ but robustness 동일| J[Generic remix augmentation 가능성]
    G -->|악화| K[TPCR 비율/매칭/normal replay 수정]

    H --> L[3 seeds + M1-R remix control]
    I --> L
    J --> L

    L --> M[Medium/Large scale]
    M --> N[다른 악기 재현]

    N --> N1[Piano Specialist]
    N --> N2[Guitar Specialist]
    N --> N3[Drum Specialist]
    N --> N4[Voice Specialist]
    N --> N5[Strings Specialist]
    N --> N6[Brass/Woodwind Specialists]

    N1 --> O[악기별 최적 architecture/학습법]
    N2 --> O
    N3 --> O
    N4 --> O
    N5 --> O
    N6 --> O

    O --> P[Heterogeneous Independent Specialist Bank]
    P --> Q[External reliability/calibration/routing]
    Q --> R[Raw mix vs separated stem 선택]
    R --> S[실제 음악 benchmark + multi-dataset validation]
    S --> A

    F --> F1[Partial FT / LoRA / adapters]
    F --> F2[Real-data FT 강화]
    F --> F3[Frame/F0/onset 기반 악기 전용 구조]
    F --> F4[Data provenance / label quality 개선]
    F1 --> B
    F2 --> B
    F3 --> N
    F4 --> B
```

## 병렬 연구축

```mermaid
flowchart LR
  A[독립 Specialist] --> B[TPCR/Context]
  A --> C[Non-musical / Anti-prior]
  A --> D[Data Provenance]
  A --> E[DSP / Instrument Physics]
  A --> F[Source Separation]
  A --> G[Calibration / Abstention]
  A --> H[Scale / Efficiency]
  B --> I[Counterfactual Consistency]
  C --> I
  E --> G
  F --> G
  G --> J[Independent Specialist Integration]
  H --> J
  I --> J
  J --> K[Real-world SOTA]
```

## 논문 후보

1. **Do Instrument Specialists Beat Universal Music Transcription Models?**
2. **Cross-Instrument Context Dependence in Multi-Instrument AMT**
3. **Target-Preserving Context Replacement for Robust AMT**
4. **Counterfactual Consistency Training for Instrument Transcription**
5. **Breaking the Music Prior: Non-Musical Curriculum Learning for AMT**
6. **Ground-Truth Reliability and Data Provenance in Large-Scale AMT**
7. **Reliability-Aware Independent Specialist Integration for Multi-Instrument AMT**
8. **Instrument-Physics-Constrained AMT**

상세 실험 120개와 모든 결과 분기는 `master-plan/`에 있다.
