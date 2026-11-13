# Hosted repository analysis

The hosted entry point accepts repository ZIP uploads or a public GitHub repository URL and runs the existing analysis pipeline in a separate subprocess. Python, TypeScript, JavaScript, JSX and TSX use the same adapters, declared static profiles, validation and evidence as the local application. JSX tag syntax does not establish runtime framework relationships. See [the extended language profile](ecmascript-profile.md). Each job has a random 256-bit capability identifier and a separate result directory. Report routes require that job identifier and a completed job. The application exposes no directory listing or server folder input.

GitHub inputs must use https://github.com/owner/repository. An optional branch, tag or commit goes in the revision field. The worker resolves it through GitHub's commit API, validates the returned 40-character SHA, and downloads that exact commit from codeload.github.com. Redirects are rejected, downloads are bounded, and the same archive limits and extraction safeguards apply as ZIP uploads. The graph records the GitHub repository and resolved commit in its snapshot identity. GitHub API rate limits and private or unavailable repositories can cause imports to fail. Credentials and private repository imports require a future authentication feature.

Limits are 3 MiB compressed, 8 MiB extracted, 1,000 ZIP entries, 180 seconds per analysis, one executing job and one queued job. Up to 16 result sets are retained for one hour. Expired jobs are removed when the service receives a job or result request. Inputs are removed when jobs finish. Cancellation and timeout terminate the analysis process and its children. Failed jobs retain a status response, and interrupted jobs are marked failed after a process restart on the same filesystem. A refreshed browser tab resumes polling its last submitted job through session storage.

The free Render instance uses ephemeral storage. A service restart or redeployment can remove jobs and results before their one-hour expiration. The interface explains this before submission and provides a portable HTML map and graph downloads. Result links include source code and should be kept private.

Save on this device stores a copy of the map, documentation, graph, validation result and manifest in IndexedDB after the visitor explicitly chooses to save. Files are checked against the publication manifest both before saving and reopening. Saved reports open using local blob URLs and remain usable after the server result expires. The history dialog allows reopening and deleting reports, with repository names and save dates. Storage is bounded to 10 reports and 50 MiB, enforced in one database transaction across tabs. Browser storage quotas can also cause saving to fail, and clearing site data or browser storage eviction can remove saved history. History is specific to this browser and device. Account-backed cloud history and synchronization require a future persistence feature.

Run the container with a writable /tmp directory and exactly one Gunicorn worker. Its threads serve the API while one analysis worker consumes the bounded queue. Multiple workers or replicas require a shared job store and queue first.

```sh
docker build -t seremy-hosted .
docker run --rm -p 10000:10000 seremy-hosted
```

Health checks use GET /healthz. The Docker image includes Python 3.13, Node 22, Git and the pinned TypeScript adapter. The server runs as an unprivileged user. Uploaded source is statically analyzed without running repository scripts or installing repository dependencies.

The local launcher remains available through python -m seremy.server with its local folder, ZIP and HTTPS Git inputs.
