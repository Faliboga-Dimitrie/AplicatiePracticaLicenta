SELECT id, subject_id, acquisition_date, notes, status
FROM mri_case
WHERE subject_id = %s AND acquisition_date = %s
