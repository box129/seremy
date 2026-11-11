# Hosted ZIP analysis

The hosted entry point accepts repository ZIP uploads and runs the existing CLI pipeline in a separate subprocess. Python and TypeScript use the same adapters, validation and evidence as the local application. Each job has a random 256-bit capability identifier and a separate result directory. Report routes require that job identifier and a completed job. The application exposes no directory listing or server folder input.

Limits are 3 MiB compressed, 8 MiB extracted, 1,000 ZIP entries, 180 seconds per analysis, one executing job and one queued job. Up to 16 result sets are retained for one hour. Expired jobs are removed when the service receives a job or result request. Inputs are removed when jobs finish. Cancellation and timeout terminate the analysis process and its children. Failed jobs retain a status response, and interrupted jobs are marked failed after a process restart on the same filesystem. A refreshed browser tab resumes polling its last submitted job through session storage.

The free Render instance uses ephemeral storage. A service restart or redeployment can remove jobs and results before their one-hour expiration. The interface explains this before upload and provides a portable HTML map and graph downloads. Result links include source code and should be kept private. Persistent history, account ownership and Git URL ingestion are future hosted milestones.

Run the container with a writable /tmp directory and exactly one Gunicorn worker. Its threads serve the API while one analysis worker consumes the bounded queue. Multiple workers or replicas require a shared job store and queue first.

```sh
docker build -t seremy-hosted .
docker run --rm -p 10000:10000 seremy-hosted
```

Health checks use GET /healthz. The Docker image includes Python 3.13, Node 22, Git and the pinned TypeScript adapter. The server runs as an unprivileged user. Uploaded source is statically analyzed without running repository scripts or installing repository dependencies.

The local launcher remains available through python -m seremy.server with its local folder, ZIP and HTTPS Git inputs.
