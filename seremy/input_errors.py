"""Public, actionable failure protocol; never forward subprocess tracebacks."""
class InputFailure(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(message)


MESSAGES = {
    "GITHUB_ARCHIVE_LIMIT": "The GitHub archive exceeds the 3 MiB hosted download limit. Choose a source folder such as src, upload a source-folder ZIP, or analyze the full repository with the local app.",
    "GITHUB_SCOPED_DOWNLOAD_LIMIT": "The GitHub archive exceeds the 16 MiB source-folder download limit. Upload a source-folder ZIP or use the local app.",
    "GITHUB_FOLDER_NOT_FOUND": "That source folder was not found in the selected GitHub revision. Enter its repository-relative path, such as src, and check the revision.",
    "GITHUB_NOT_FOUND": "GitHub could not find that public repository or revision. Check the URL and branch, tag or commit.",
    "GITHUB_RATE_LIMIT": "GitHub refused the request or its public API limit was reached. Wait and retry, or upload a source ZIP.",
    "GITHUB_UNAVAILABLE": "GitHub could not be reached. Retry later or upload a source ZIP.",
    "ARCHIVE_EXTRACTION_LIMIT": "This archive exceeds the hosted limits of 1,000 entries, 8 MiB extracted or 1 MiB per selected file. Choose a smaller source folder, upload a source-folder ZIP or use the local app.",
    "TSCONFIG_PROFILE": "This repository uses tsconfig extends or project references, which the current snapshot profile does not support. Analyze a self-contained package with its own configuration, or prepare an explicit supported snapshot. Configuration was not silently ignored.",
    "ANALYSIS_FAILED": "Analysis could not finish. Retry with a smaller supported source ZIP. If it still fails, use the local app to inspect the detailed diagnostic.",
}


def public_failure(error):
    code = getattr(error, "code", None)
    if code not in MESSAGES:
        text = str(error)
        code = "TSCONFIG_PROFILE" if "extends/references require a multi-project snapshot profile" in text else "ANALYSIS_FAILED"
    return {"code": code, "message": MESSAGES[code]}
