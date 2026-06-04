UPDATE auth_session
SET revoked_at = UTC_TIMESTAMP()
WHERE refresh_token_hash = %s
  AND revoked_at IS NULL
