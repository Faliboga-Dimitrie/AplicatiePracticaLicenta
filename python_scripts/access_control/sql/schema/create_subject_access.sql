CREATE TABLE IF NOT EXISTS subject_access (
    user_id BIGINT NOT NULL,
    subject_id VARCHAR(100) NOT NULL,
    PRIMARY KEY (user_id, subject_id),
    KEY idx_subject_access_subject (subject_id),
    CONSTRAINT fk_subject_access_user
        FOREIGN KEY (user_id) REFERENCES app_user(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_subject_access_subject
        FOREIGN KEY (subject_id) REFERENCES subject(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
