# Repository preflight and parsing timeout investigation

Date: 18 November 2026.

## Reproduction

The reported public repository was `https://github.com/Mizzy006/Sabi`, pinned for this investigation to `3184572f7212cf3fa83101dabac7b3c3dd5be714`.

| Measurement | Observed value |
|---|---:|
| Compressed archive | 494,939 bytes (0.47 MiB) |
| Extracted content | 1,448,269 bytes (1.38 MiB) |
| ZIP entries / files | 72 / 61 |
| Supported source files | 23 (13 Python, 4 JavaScript, 6 JSX) |
| Supported source bytes | 885,102 |
| Largest script | `static/react/app.js`, 390,065 bytes |

The repository fits the hosted size limits. Its generated React bundle also contains third-party React code. Generated bundles are not silently excluded; preflight warnings let the user decide the scope.

The original independent UTF-16/UTF-8 coordinate check rescanned decoded file prefixes for every declaration and candidate. A sampled stack during the reproduction was inside `utf16_index_to_byte_offset`. The correction constructs one independent compact coordinate index per source file and verifies each range against it, retaining name-text, hash, byte-boundary and coordinate checks. Surrogate-pair interiors are rejected.

On the same Windows/Python 3.14 machine, the previous parser from commit `98cb42f` remained in S02 when the controlled test stopped after 180 seconds. With the correction, the pipeline through generated-output validation completed in 35.654 seconds (36.512 seconds including child-process overhead). All 23 supported source files parsed completely; there were 1,499 distinct call edges and five module dependency edges. Both pre- and post-generation validation passed. This is one local reproduction, not a broad benchmark or a promised Render runtime. It excludes download and map publication time; the separate browser test covers full publication and source verification.

The graph also records 3,726 unsupported call-profile candidates and 795 missing call targets; successful completion does not imply complete semantic coverage of the application. HTML/CSS are not architectural parser inputs.

## Checks

- Targeted Python suite: 59 passed, covering Unicode coordinate validation, many-record performance behavior, archive bounds, preflight confirmation/access, cancellation, unsupported inputs, GitHub scope/commit reuse and existing hosted behavior.
- Full Python run: 322 passed, one hosted-documentation fixture setup error (the analysis subprocess returned a generic failure). Its entire ten-test module passed on isolated rerun. The original error is retained in the evidence; its underlying cause was not established, so the full run is not reported as clean.
- Browser regression: reported repository upload, explicit confirmation, refresh recovery, full report publication/source verification, mobile limits/help and GitHub folder selection.
- Existing hosted workflow: nine grouped checks passed (downloads, device history, visibility/Back, refresh and failed replacement). Accessibility regression: 14 visible frame/state records, no confirmed automated violations or page errors; incomplete contrast checks still require manual review. Local provider availability changes the last enabled field in the documentation dialog; the focus check now uses the actual enabled controls.
- Warnings use measured size/density, not a reliable generated-code classifier: a script at least 256 KiB, or at least 64 KiB with a line of 2,000 bytes or a `.min.js` name, is flagged for review. Warnings never remove files.

Reproduce functional checks from the repository root:

```powershell
python -B -m pytest seremy/tests/test_preflight.py seremy/tests/test_parsing.py seremy/tests/test_hosted.py seremy/tests/test_github_input.py -q --basetemp=../ArchDoc-Preflight-Tests
node seremy/tools/check-preflight.cjs http://127.0.0.1:8789 <pinned-Sabi.zip> <evidence-directory>
```

The browser check needs a hosted-mode server and performs static analysis only. It does not request paid AI documentation. The original public archive can be acquired from GitHub's codeload ZIP endpoint using the exact commit above. Do not install its dependencies or run its scripts to reproduce this analysis.

## Remaining usability limits

The mobile screenshot of this full repository opens at 5% zoom. Code is unreadable at that scale and folder labels overlap. A detailed source-map fit is still a weak first view on a phone. A focused file/folder entry view or a simplified component overview deserves a separate change; improved instructions alone do not resolve that problem. The reported unstable taps/gestures have not been verified on the user's physical phone. Desktop/mobile viewport automation is not a real-device user trial.

Preflight cannot predict all CPU/memory demands. GitHub acquisition can fail or time out, passing checks does not guarantee analysis within 180 seconds, HTML/CSS semantics remain unsupported, and selecting a folder loses outside context. The free service still uses temporary storage.
