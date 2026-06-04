UPDATE mri_case
SET {assignments}
WHERE subject_id = %s AND acquisition_date = %s
