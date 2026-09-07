# AMT Independent Specialist Research Workspace

이 디렉터리는 정상 실제 음악에서 multi-instrument AMT SOTA를 목표로 하는 **독립 악기별 Specialist 모델 연구**의 canonical research index다. 모델은 MoE가 아니라 악기별로 독립적인 weights/architecture를 갖는 것을 원칙으로 한다.

## Canonical artifacts

### 전체 연구 계획
- `master-plan/part-01.md` ~ `part-09.md`
  - 원본 `AMT_독립전문가_전체연구실험설계서_v1.md`를 순서대로 무손실 분할한 것.
  - 순서대로 concatenate하면 원문 Markdown이 복원된다.

### EXP01 방법론 리뷰
- `reviews/EXP01_METHOD_REVIEW_20260904/part-01.md` ~ `part-04.md`
  - 첫 Bass specialization/TPCR 계획을 비판적으로 검토한 전체 리뷰 원문.

### EXP01 실행/상태
- `../../experiments/EXP01_BassSpecialization/STATUS.md`
  - 현재 C1/M1/M2 진행상황과 확정 run 기록.
- `../../experiments/EXP01_BassSpecialization/runs/C1/PROVENANCE_SUMMARY.json`
  - C1 확정 실측치와 무결성 상태 요약. 정확한 checkpoint SHA256은 원본 provenance JSON을 authoritative source로 유지하며, 채팅에 제공되지 않은 문자열은 추측해 채우지 않는다.
- `../../experiments/EXP01_BassSpecialization/scripts/07_train.py`
  - 완료 run 덮어쓰기 방지 + 정상 종료 시 provenance/checksum/COMPLETE 자동 생성 trainer.
- `../../experiments/EXP01_BassSpecialization/scripts/11_write_run_provenance.py`
  - 구버전 trainer로 완료된 M1/M2 등의 provenance를 사후 생성하는 backfill utility.

### 전체 로드맵
- `ROADMAP.md`
  - 실험 분기와 논문 후보를 Mermaid tree로 정리.

### 생성 아티팩트 검증
- `ARTIFACT_MANIFEST.json`
  - 채팅에서 생성된 MD/DOCX/ZIP/PNG 원본의 byte size와 SHA-256.

## EXP01 핵심 비교

- **M0**: MuScriptor-small original checkpoint
- **C1**: General Continued-Training control
- **M1**: Bass-Normal specialist
- **M2**: Bass-TPCR specialist

핵심 contrast:

- `M1 - M0`: 실용적인 bass-specialized recipe 이득
- `M1 - C1`: continued training을 넘어선 specialization 이득
- `M2 - M1`: TPCR replacement 이득
- `CPD/CIPD`: context robustness 변화

## EXP01 live status — 2026-09-07

- **C1**: ✅ complete, 3000 steps, 73.4 min, final loss 0.5627, token acc 0.7844, peak VRAM 3.68 GB, seed 42, MuScriptor `d73147e`.
- **M1**: 🔄 running in the latest report.
- **M2**: ⏳ queued.

Training loss/token accuracy are not cross-task scientific endpoints; C1 vs M1/M2 must be compared on the same bass evaluation metrics.

## 운영 원칙

1. 새 AMT 연구 산출물은 이 저장소에 즉시 반영한다.
2. 데이터 provenance, split, model revision, code commit, seed를 기록한다.
3. 완료된 run directory는 기본적으로 immutable하게 취급한다. `CHECKPOINT_COMPLETE`가 있으면 새 trainer는 명시적 위험 override 없이는 재사용을 거부한다.
4. 성공 종료 시 `provenance.json`과 `CHECKPOINT_COMPLETE`에 checkpoint/log SHA256을 자동 기록한다.
5. MulTTiPop test는 설정을 잠근 뒤 최종 평가에서만 사용한다.
6. 한 seed pilot은 screening이며 확정 결과는 multiple seeds + cluster bootstrap으로 확인한다.
7. 최종 목표는 random/OOD 음악이 아니라 **정상 실제 음악의 transcription SOTA**다.
