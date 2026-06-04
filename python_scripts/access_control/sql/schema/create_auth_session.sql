CREATE TABLE IF NOT EXISTS auth_session (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    refresh_token_hash VARCHAR(255) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    revoked_at DATETIME NULL,
    last_used_at DATETIME NULL,
    KEY idx_auth_session_user (user_id),
    KEY idx_auth_session_expires (expires_at),
    CONSTRAINT fk_auth_session_user
        FOREIGN KEY (user_id) REFERENCES app_user(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
