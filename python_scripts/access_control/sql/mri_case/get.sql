SELECT id, subject_id, acquisition_date, notes, status
FROM mri_case
WHERE id = %s
