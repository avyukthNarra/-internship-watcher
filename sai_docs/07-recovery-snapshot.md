# Recovery snapshot (T02)

`state_snapshot.py` creates an immutable generation containing `seen.json`, `delivery_state.json`, `message_map.json`, `notion_state.json`, `health.json`, and a manifest. The manifest records the Actions run ID and attempt (or `local`), schema version, UTC creation time, per-file SHA-256, size, record count, and producer generation ID. Creation rejects malformed state and cross-file inconsistencies. In particular, the watcher writes the ledger before `seen.json`, and the ledger seeds the next run's seen set, so `delivery_state.json["known_ids"]` may be ahead of but must contain `seen.json`; pending deliveries and accepted-message map receipts must also reference known IDs.

Restore verifies the complete manifest, generation membership, hashes, sizes, counts, JSON, and invariants before staging any target writes. It replaces only the five named state files, skips byte-identical files on a second restore, and preserves unrelated target files. CLI use:

```sh
python3 state_snapshot.py create --out "$RUNNER_TEMP/watcher-snapshots"
python3 state_snapshot.py restore --from /path/to/generation --to /path/to/state
```

## Proposed workflow placement

Place the following steps immediately before the existing `Persist state` step in `.github/workflows/watch.yml`, after the watcher and source-doctor dispatch steps. This captures the runner's completed state before any state commit, `git pull --rebase`, or push can modify it.

```yaml
      - name: Capture recovery snapshot
        id: recovery_snapshot
        if: always()
        run: |
          snapshot_dir="$(python3 state_snapshot.py create --out "$RUNNER_TEMP/watcher-snapshots")"
          echo "path=$snapshot_dir" >> "$GITHUB_OUTPUT"

      - name: Preserve recovery snapshot
        if: always() && steps.recovery_snapshot.outputs.path
        uses: actions/upload-artifact@v7
        with:
          name: watcher-state-${{ github.run_id }}-${{ github.run_attempt }}
          retention-days: 7
          if-no-files-found: error
          path: ${{ steps.recovery_snapshot.outputs.path }}/
```

**Privacy gate:** the snapshot contains Discord IDs and message receipts, Notion tracker identifiers, applied-link history, job queues, and other personal operational data. Keep it private. Do not enable the upload step in this public repository unless the owner has moved the workflow and artifact into an access-controlled private store as part of T03. A separate public state branch or public artifact is not an acceptable private store. The snippet is a proposal for owner review; no workflow files were changed.

## Verification and limits

Synthetic tests cover round trip, hash corruption, missing files, mixed generation membership, schema mismatch, idempotent restore, and inconsistent-ledger rejection. Snapshot creation reads each source file and checks that its bytes have not changed during capture; the workflow's single-writer concurrency is still needed to avoid concurrent watcher mutations. The manifest detects accidental corruption and mixing, but it is not signed and does not defend against a party able to rewrite both the generation and manifest. Configure access controls and retention in the private store under T03.

## Deployed

Enabled in `watch.yml` after T03. Each run writes a generation to `snapshot/` in the private `avyukthNarra/internship-watcher-state` repo alongside the live state files, so every commit there is a validated restore point. Nothing is uploaded as an artifact. To restore (pause the watcher first):

```sh
git clone git@github.com:avyukthNarra/internship-watcher-state.git && cd internship-watcher-state
git log --oneline            # pick the commit to go back to
git checkout <commit> -- snapshot
python3 ../-internship-watcher/state_snapshot.py restore --from snapshot --to .
git commit -am "Restore state from <commit>" && git push
```
