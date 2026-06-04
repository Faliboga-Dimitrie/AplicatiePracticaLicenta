UPDATE auth_session
SET revoked_at = UTC_TIMESTAMP()
WHERE user_id = %s
  AND revoked_at IS NULL
