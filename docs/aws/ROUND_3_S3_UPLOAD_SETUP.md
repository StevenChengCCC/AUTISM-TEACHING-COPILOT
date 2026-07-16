# Round 3: Private S3 learner-record uploads

This round stores original PDF, DOCX, and TXT learner records as private S3
objects and stores extracted/corrected text in PostgreSQL. It is appropriate for
synthetic staging documents only. Authentication is still a demo boundary, OCR
is not connected, and malware scanning is explicitly `not_configured`.

## Bucket controls

Create a dedicated staging bucket (or a dedicated, access-controlled prefix) in
the same AWS Region as Elastic Beanstalk. Configure:

- S3 Block Public Access: all four settings enabled.
- Object Ownership: **Bucket owner enforced** (ACLs disabled).
- Default encryption: SSE-S3 (`AES256`) for this demo. A customer-managed KMS
  key can be configured later with `S3_SERVER_SIDE_ENCRYPTION=aws:kms` and
  `S3_KMS_KEY_ID`.
- Versioning according to the project's deletion/retention policy. Do not use
  versioning as a substitute for an approved privacy retention policy.
- No static website hosting, public-read ACL, public bucket policy, or public
  CloudFront origin for this bucket.

Example CLI (replace placeholders):

```bash
aws s3api create-bucket \
  --bucket YOUR_PRIVATE_RECORD_BUCKET \
  --region YOUR_REGION \
  --create-bucket-configuration LocationConstraint=YOUR_REGION

aws s3api put-public-access-block \
  --bucket YOUR_PRIVATE_RECORD_BUCKET \
  --public-access-block-configuration \
  'BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true'

aws s3api put-bucket-ownership-controls \
  --bucket YOUR_PRIVATE_RECORD_BUCKET \
  --ownership-controls 'Rules=[{ObjectOwnership=BucketOwnerEnforced}]'

aws s3api put-bucket-encryption \
  --bucket YOUR_PRIVATE_RECORD_BUCKET \
  --server-side-encryption-configuration \
  'Rules=[{ApplyServerSideEncryptionByDefault={SSEAlgorithm=AES256},BucketKeyEnabled=false}]'
```

For `us-east-1`, omit `--create-bucket-configuration` from `create-bucket`.

## Narrow browser CORS

Replace the example origins with the exact Amplify staging domain and, only if
needed, the custom staging domain. Do not use `*`.

```json
[
  {
    "AllowedHeaders": [
      "content-type",
      "x-amz-server-side-encryption",
      "x-amz-server-side-encryption-aws-kms-key-id"
    ],
    "AllowedMethods": ["PUT"],
    "AllowedOrigins": ["https://YOUR_AMPLIFY_STAGING_DOMAIN"],
    "ExposeHeaders": ["ETag"],
    "MaxAgeSeconds": 300
  }
]
```

Apply it with `aws s3api put-bucket-cors --bucket ... --cors-configuration
file://cors.json`. The frontend receives only a short-lived signed URL; it never
receives AWS credentials.

## Lifecycle rules

The current flow uses single-part PUT for files up to 10 MB. Add a lifecycle
rule for the `learner-records/` prefix that expires abandoned temporary objects
according to the staging retention policy. If multipart uploads are added, also
configure `AbortIncompleteMultipartUpload`; normal expiration alone does not
remove incomplete multipart parts.

Do not expire active records solely because the application has not yet marked
them complete. A safe implementation can tag confirmed records and expire only
unconfirmed objects, or run a reconciler against upload state.

## Elastic Beanstalk instance-profile policy

Attach a least-privilege policy to the EB EC2 instance profile, not to the
browser and not as source-controlled access keys:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PrivateLearnerRecordObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::YOUR_PRIVATE_RECORD_BUCKET/learner-records/*"
    }
  ]
}
```

`HeadObject` is authorized by `s3:GetObject`. Bucket listing is not required by
the application. If a KMS key is selected, add only the necessary key permissions
for the specific key and restrict its key policy to the EB role.

## Backend environment

```text
APP_ENV=staging
OBJECT_STORAGE_PROVIDER=s3
S3_BUCKET=YOUR_PRIVATE_RECORD_BUCKET
S3_REGION=YOUR_REGION
S3_UPLOAD_PREFIX=learner-records
S3_PRESIGNED_TTL_SECONDS=300
S3_SERVER_SIDE_ENCRYPTION=AES256
PUBLIC_API_BASE_URL=https://api-staging.YOUR_DOMAIN
MAX_UPLOAD_BYTES=10485760
ALLOWED_UPLOAD_EXTENSIONS=.txt,.pdf,.docx
ALLOWED_UPLOAD_MIME_TYPES=text/plain,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document
ENABLE_UPLOAD_ANTIVIRUS_SCAN=false
```

Staging forces the S3 adapter even if `OBJECT_STORAGE_PROVIDER` is accidentally
set to `local`. No S3 secret key is needed when the EB instance profile is used.

## Verification

1. Run `alembic upgrade head` once using the documented migration process.
2. Upload synthetic TXT, PDF, and DOCX files from the exact Amplify origin.
3. Confirm S3 objects have no public ACL, use server-side encryption, and use a
   random key under `learner-records/` with no learner code/name/title.
4. Confirm anonymous S3 GET returns access denied.
5. Confirm the record row and extracted-text row persist after restart.
6. Confirm image-only PDFs show `needs_ocr` rather than proceeding silently.
7. Confirm deletion removes the S3 object and soft-deletes/clears extracted text.
8. Confirm readiness reports object storage configured, while still reporting
   the incomplete production authentication and scanner capabilities honestly.

## AWS references

- [Uploading objects with presigned URLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/PresignedUrlUploadObject.html)
- [Blocking public access to S3 storage](https://docs.aws.amazon.com/AmazonS3/latest/userguide/access-control-block-public-access.html)
- [S3 Object Ownership and disabling ACLs](https://docs.aws.amazon.com/AmazonS3/latest/userguide/about-object-ownership.html)
- [S3 CORS configuration](https://docs.aws.amazon.com/AmazonS3/latest/userguide/enabling-cors-examples.html)
- [S3 lifecycle configuration elements](https://docs.aws.amazon.com/AmazonS3/latest/userguide/intro-lifecycle-rules.html)
- [Elastic Beanstalk instance profiles](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/iam-instanceprofile.html)
