UPDATE auth_session
SET refresh_token_hash = %s,
    expires_at = %s,
    last_used_at = UTC_TIMESTAMP()
WHERE id = %s
  AND refresh_token_hash = %s
  AND revoked_at IS NULL
  AND expires_at > UTC_TIMESTAMP()
