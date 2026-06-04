SELECT id, subject_id, acquisition_date, notes, status
FROM mri_case
WHERE subject_id = %s
ORDER BY acquisition_date ASC
