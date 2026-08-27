# Catalog schema

## Identity and provenance

- `match_id`: stable release-local ID (`PDMX-ORCH-00001` …).
- `source`, `source_doi`, `source_record_url`: dataset provenance.
- `source_record_id`: stable ID derived from the complete source path.
- `title`, `subtitle`, `composer`, `artist`: source metadata.
- `license`, `license_url`: per-record source license metadata.

## Classification

- `orchestra_class`: accepted orchestral category.
- `confidence_tier`: `A`, `B`, or `C`.
- `quality_score`: deterministic ranking score.
- `selection_reason`: concise rule that admitted the row.
- `n_tracks`: source track count.
- `instrument_families`: detected family names separated by `|`.
- `instrument_family_track_counts`: compact JSON object with family track counts.
- `tracks`: original PDMX General MIDI program field.
- `genres`, `groups`, `tags`: source descriptors.

## Musical scale and popularity

- `song_length_seconds`, `song_length_bars`, `n_notes`.
- `rating`, `n_ratings`, `n_views`.
- `has_custom_audio`: unverified PDMX metadata flag; not a human-performance assertion.

## Score and audio relationship

- `mxl_path`, `pdf_path`, `midi_path`: same-source PDMX exports.
- `audio_match_type`: always `deterministic_render_from_same_score_midi`.
- `audio_render_recipe`: command template for rendering the row’s MIDI.
- `symbolic_match_guarantee`: always `exact_same_source_score_conversion`.

## Required subset and duplication fields

- `subset_no_license_conflict`.
- `subset_all_valid`.
- `subset_deduplicated`: whether PDMX marks this source row as its best unique arrangement.
- `duplicate_group_id`: stable hash of PDMX’s representative arrangement path, used to cap repeated engravings/arrangements.
