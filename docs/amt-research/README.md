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

### EXP01 실행 코드
- `../../experiments/EXP01_BassSpecialization/README_KO.md`
- `../../experiments/EXP01_BassSpecialization/source-snapshot/part-01.md` ~ `part-04.md`
  - `muscriptor_bass_pilot_v2.zip`의 UTF-8 연구 소스 25개를 파일 경계와 함께 전부 보존한 snapshot.

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

## 운영 원칙

1. 새 AMT 연구 산출물은 이 저장소에 즉시 반영한다.
2. 데이터 provenance, split, model revision, code commit, seed를 기록한다.
3. MulTTiPop test는 설정을 잠근 뒤 최종 평가에서만 사용한다.
4. 한 seed pilot은 screening이며 확정 결과는 multiple seeds + cluster bootstrap으로 확인한다.
5. 최종 목표는 random/OOD 음악이 아니라 **정상 실제 음악의 transcription SOTA**다.
