"""Versioned source universes; legacy TS/Python-only snapshots retain their identity."""
from seremy.contracts import PROFILE_ID

LEGACY_SOURCE_EXTENSIONS = (".ts", ".py")
SCRIPT_EXTENSIONS = (".ts", ".js", ".jsx", ".tsx")
EXTENDED_EXTENSIONS = (".js", ".jsx", ".tsx")
SOURCE_EXTENSIONS = (*SCRIPT_EXTENSIONS, ".py")
ECMASCRIPT_PROFILE = "seremy-ecmascript-static-v0.1"
ECMASCRIPT_PRODUCT_PROFILE = "seremy-local-ecmascript-v0.1"
ECMASCRIPT_BINDING_PROFILE = "typescript-ecmascript-checker-v0.1"


def has_ecmascript(paths):
    return any(path.endswith(EXTENDED_EXTENSIONS) for path in paths)


def syntax_profile(paths):
    return ECMASCRIPT_PROFILE if has_ecmascript(paths) else PROFILE_ID


def parsed_profile(results):
    return ECMASCRIPT_PROFILE if any(
        result.file_id.endswith(EXTENDED_EXTENSIONS) or result.construct_coverage.get("language_profile")==ECMASCRIPT_PROFILE
        for result in results) else PROFILE_ID
