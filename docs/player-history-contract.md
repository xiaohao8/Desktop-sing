# Player history contract (storage v2)

## Scope

This contract covers the persisted listening history and the smallest playback
resume API that the player UI can call. It intentionally does **not** introduce
"play any history entry": only the source session that is still attached to the
current SMTC session can be resumed.

UI is an adapter and owns presentation only. It must not write schema fields or
implement its own fallback playback.

## Storage schema

`listening.json` is versioned by `v`. The reader migrates v1 entries to v2 in
memory with defaults; no one-shot migration script is required.

### Session fields

| Field | Type | Meaning | Empty/zero semantics |
|---|---:|---|---|
| `t` | string | Track title. | Unknown/empty title. |
| `a` | string | Track artist. | Unknown/empty artist. |
| `s` | float | Listened seconds. | No listened time; below the 20 second rule is not persisted. |
| `n` | integer | Play count. | Zero. |
| `d` | string | Local day key. | Unknown. |
| `h` | integer | Local hour. | Zero means 00:00, not "unknown". |
| `last` | float | Unix timestamp of the last accepted update. | Zero means unknown. |
| `src` | string | Source app AUMID. | `""` means unknown source; the entry cannot be resumed. |
| `dur` | float | Reported track duration in seconds. | `0.0` means unknown duration. |
| `pos` | float | Last observed playback position in seconds. | `0.0` means no usable progress. |
| `cov` | string | SHA-256 cache key of the cover image. | `""` means no cover. |

Backward compatibility rules:

- Missing `src`, `dur`, `pos`, and `cov` are filled lazily with `""`, `0.0`,
  `0.0`, and `""` respectively.
- Existing fields keep their names and meanings. Nothing is renamed or removed.
- A legacy entry therefore remains a valid statistics item, but it has no cover
  and is not resumable.
- Unknown values never use `null`; use empty string or zero.
- `pos` and `dur` are best-effort values from SMTC, not a persistent playlist
  cursor. If a source changes sessions, a stale value is not reused.

## Cover cache

SMTC cover bytes are written to:

```text
%APPDATA%/Desktop-sing/covers/<sha256>.png
```

`listening.json` stores only the SHA-256 key. Cover files are an LRU cache with
a 50 MiB budget, keyed by mtime. The cache may disappear at any time, so all
readers must treat a missing file as "cover unavailable", not an error.

Downloaded lyrics cover URLs use the same directory and pruning logic, but their
key is `SHA-256(url)`. This keeps two implementations from racing over the same
file while preserving one directory budget.

The API is:

```python
listening_store.covers_dir() -> str
listening_store.save_cover(data: bytes) -> str
listening_store.save_cover_url(url: str, data: bytes) -> str
listening_store.load_cover(cover_hash: str) -> bytes
listening_store.load_cover_url(url: str) -> bytes
```

All write failures return `""` or `b""`; they never raise to the caller.

## Read API

```python
store.recent_tracks(limit: int = 20) -> list[dict]
```

Each returned track contains the legacy statistics fields plus:

| Field | Type | Meaning | Empty/zero semantics |
|---|---:|---|---|
| `source` | string | AUMID of the latest source session. | `""` means unknown or legacy. |
| `duration` | float | Duration of the latest source session. | `0.0` means unknown. |
| `position` | float | Last saved playback position. | `0.0` means no progress. |
| `cover` | string | Cover cache key. | `""` means no cover. |
| `resume_id` | string | Stable identity of a resumable session. | `""` means not resumable. |

`resume_id` is:

```text
track_key(title, artist) + "\x1f" + source
```

Legacy entries without a source always return `resume_id == ""`.

## Playback control

The existing command path remains:

```python
overlay.media_command(cmd: str)
```

The new minimal async commands are:

```python
overlay.play() -> None
overlay.pause() -> None
overlay.current_resume_id() -> str
overlay.resume_history(track: dict) -> bool
```

`play()` and `pause()` ask the current SMTC session to resume or pause. They are
fire-and-forget; failures are logged and do not raise into the UI thread.

`resume_history()` follows this exact decision table:

| Condition | Action | Return |
|---|---|---:|
| `resume_id` is empty | No playback action. | `False` |
| `resume_id != current_resume_id()` | No playback action; UI shows the "open source player" state. | `False` |
| Same `resume_id` | `seek(position)`, then `play()`. | `True` |

If SMTC cannot provide the current session, `current_resume_id()` returns `""`.
The UI must not infer a different session from title and artist alone.

## Failure paths

- Cover cache miss: show the history/report row without artwork.
- No source AUMID: history row remains visible, but it is not resumable.
- Source mismatch: keep the row disabled and show the localized source-player hint.
- SMTC command timeout: no retry loop in the UI; the user can click again.
- Unknown duration/position: `seek(0.0) + play()` is still allowed for the same
  session; the source player decides its own restart semantics.
