CREATE TABLE IF NOT EXISTS mri_case (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    subject_id VARCHAR(100) NOT NULL,
    acquisition_date DATE NOT NULL,
    notes TEXT NULL,
    status VARCHAR(50) NULL,
    UNIQUE KEY uq_mri_case_subject_date (subject_id, acquisition_date),
    KEY idx_mri_case_date (acquisition_date),
    CONSTRAINT fk_mri_case_subject
        FOREIGN KEY (subject_id) REFERENCES subject(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
