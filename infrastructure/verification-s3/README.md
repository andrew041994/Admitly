# Private creator-verification S3 templates

These templates are operator inputs, not applied infrastructure. Replace only the
explicit bucket placeholder. The runtime policy is attached to the backend
workload identity; the bucket policy is attached to the new private bucket.

The templates use SSE-S3 (`AES256`). If a separately reviewed customer-managed
KMS design is adopted, update the bucket policy, default encryption, application
configuration, and runtime KMS permissions together. Do not set only
`S3_VERIFICATION_KMS_KEY_ID` against these SSE-S3 templates.

The runtime policy deliberately contains no bucket-listing, lifecycle, policy,
event-cover, IAM, or administrative permission. Provisioning permissions remain
with the operator and must not be attached to the application role.
