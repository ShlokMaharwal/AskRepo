import hmac

from fastapi import HTTPException

from app.models import IndexRequest


class DailyIndexLimit(OverflowError):
    pass


def authorize_index(settings, url, token, *, already_ready=False):
    allowed = {IndexRequest(repo_url=value).repo_url.lower() for value in settings.demo_repos}
    if settings.indexing_mode == "allowlist" and url.lower() not in allowed:
        raise HTTPException(
            403, "This public demo indexes only the demo repositories. Choose a demo below."
        )
    if settings.indexing_mode == "token" and not already_ready:
        expected = settings.admin_token.get_secret_value() if settings.admin_token else ""
        if not expected or not token or not hmac.compare_digest(token.encode(), expected.encode()):
            raise HTTPException(
                403,
                "Indexing new repositories requires an admin token. "
                "Demo repositories remain available.",
            )
