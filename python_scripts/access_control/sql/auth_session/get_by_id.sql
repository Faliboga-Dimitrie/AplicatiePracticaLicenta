SELECT
    id, user_id, refresh_token_hash, created_at, expires_at,
    revoked_at, last_used_at
FROM auth_session
WHERE id = %s
