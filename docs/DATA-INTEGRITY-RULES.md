# Data integrity rules

- Do not count source catalogue rows as collected pairs.
- Do not count a render recipe as audio until the audio object exists and is hashed.
- Do not infer orchestra, band, or jazz from a filename alone.
- Keep `work_id`, `arrangement_id`, and `render_id` separate.
- Split by work/arrangement group, never by render variant.
- Every published count must be reproducible from a committed manifest and validator.
- Commercial VST-rendered audio must carry plugin, preset/state, version, license decision, and file hash.
