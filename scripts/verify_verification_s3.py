#!/usr/bin/env python3
"""Read-only verification for a provisioned private creator-verification bucket.

This script performs S3/IAM reads and optional anonymous/authorized HEAD requests.
It never writes, deletes, changes policy, or prints object keys or credentials.
"""

from __future__ import annotations

import argparse
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import boto3
from botocore.exceptions import ClientError


REQUIRED_OBJECT_ACTIONS = ("s3:PutObject", "s3:GetObject", "s3:DeleteObject")
FORBIDDEN_ACTIONS = ("s3:ListAllMyBuckets", "s3:PutBucketPolicy", "s3:PutLifecycleConfiguration")


class CheckResults:
    def __init__(self) -> None:
        self.passes = 0
        self.warnings = 0
        self.failures = 0

    def passed(self, message: str) -> None:
        self.passes += 1
        print(f"PASS: {message}")

    def warning(self, message: str) -> None:
        self.warnings += 1
        print(f"WARNING: {message}")

    def failed(self, message: str) -> None:
        self.failures += 1
        print(f"FAIL: {message}")


def _is_missing(exc: ClientError, *codes: str) -> bool:
    return exc.response.get("Error", {}).get("Code") in codes


def verify(args: argparse.Namespace) -> int:
    result = CheckResults()
    s3 = boto3.client("s3", region_name=args.region)
    expected_prefix = args.prefix.strip("/") + "/"

    try:
        s3.head_bucket(Bucket=args.bucket)
        result.passed("target bucket exists and current credentials can inspect it")
    except ClientError:
        result.failed("target bucket is missing or cannot be inspected")
        return 1

    if args.event_bucket and args.event_bucket == args.bucket:
        result.failed("verification bucket is the public event-cover bucket")
    else:
        result.passed("verification bucket is distinct from the supplied event-cover bucket")

    try:
        controls = s3.get_public_access_block(Bucket=args.bucket)["PublicAccessBlockConfiguration"]
        if all(controls.get(name) is True for name in ("BlockPublicAcls", "IgnorePublicAcls", "BlockPublicPolicy", "RestrictPublicBuckets")):
            result.passed("all four S3 Block Public Access controls are enabled")
        else:
            result.failed("one or more S3 Block Public Access controls are disabled")
    except ClientError:
        result.failed("Block Public Access configuration could not be verified")

    try:
        ownership = s3.get_bucket_ownership_controls(Bucket=args.bucket)
        rules = ownership.get("OwnershipControls", {}).get("Rules", [])
        if any(rule.get("ObjectOwnership") == "BucketOwnerEnforced" for rule in rules):
            result.passed("object ownership is BucketOwnerEnforced")
        else:
            result.failed("object ownership is not BucketOwnerEnforced")
    except ClientError:
        result.failed("object ownership controls could not be verified")

    try:
        s3.get_bucket_website(Bucket=args.bucket)
        result.failed("static website hosting is enabled")
    except ClientError as exc:
        if _is_missing(exc, "NoSuchWebsite", "NoSuchWebsiteConfiguration"):
            result.passed("static website hosting is disabled")
        else:
            result.failed("website configuration could not be verified")

    try:
        policy_status = s3.get_bucket_policy_status(Bucket=args.bucket).get("PolicyStatus", {})
        if policy_status.get("IsPublic") is False:
            result.passed("AWS policy analysis reports the bucket is not public")
        else:
            result.failed("AWS policy analysis does not prove the bucket is private")
    except ClientError as exc:
        if _is_missing(exc, "NoSuchBucketPolicy"):
            result.warning("bucket has no policy; add the repository TLS/encryption deny policy")
        else:
            result.failed("bucket policy status could not be verified")

    try:
        rules = s3.get_bucket_encryption(Bucket=args.bucket)["ServerSideEncryptionConfiguration"]["Rules"]
        algorithms = {
            rule.get("ApplyServerSideEncryptionByDefault", {}).get("SSEAlgorithm") for rule in rules
        }
        if algorithms.intersection({"AES256", "aws:kms", "aws:kms:dsse"}):
            result.passed("default server-side encryption is enabled")
        else:
            result.failed("default server-side encryption is not an approved mode")
    except ClientError:
        result.failed("default encryption could not be verified")

    try:
        lifecycle_rules = s3.get_bucket_lifecycle_configuration(Bucket=args.bucket).get("Rules", [])
        matching = [
            rule for rule in lifecycle_rules
            if rule.get("Status") == "Enabled"
            and rule.get("Filter", {}).get("Prefix") == expected_prefix
            and 1 <= int(rule.get("Expiration", {}).get("Days", 0)) <= args.max_retention_days
        ]
        if matching:
            result.passed(f"enabled lifecycle expiration is at most {args.max_retention_days} days")
        else:
            result.failed("required prefix-scoped lifecycle expiration was not found")
    except ClientError:
        result.failed("lifecycle configuration could not be verified")

    if args.runtime_role_arn:
        iam = boto3.client("iam", region_name=args.region)
        verification_arn = f"arn:aws:s3:::{args.bucket}/{expected_prefix}synthetic-check.jpg"
        simulation = iam.simulate_principal_policy(
            PolicySourceArn=args.runtime_role_arn,
            ActionNames=list(REQUIRED_OBJECT_ACTIONS),
            ResourceArns=[verification_arn],
        )
        decisions = {row["EvalActionName"]: row["EvalDecision"] for row in simulation["EvaluationResults"]}
        if all(decisions.get(action) == "allowed" for action in REQUIRED_OBJECT_ACTIONS):
            result.passed("runtime role can Put/Get/Delete only within the verification object scope tested")
        else:
            result.failed("runtime role lacks one or more required verification-object permissions")

        administrative = iam.simulate_principal_policy(
            PolicySourceArn=args.runtime_role_arn,
            ActionNames=list(FORBIDDEN_ACTIONS),
            ResourceArns=["*"],
        )
        unrelated = iam.simulate_principal_policy(
            PolicySourceArn=args.runtime_role_arn,
            ActionNames=list(REQUIRED_OBJECT_ACTIONS),
            ResourceArns=["arn:aws:s3:::admitly-forbidden-scope/synthetic-check"],
        )
        denied_results = administrative["EvaluationResults"] + unrelated["EvaluationResults"]
        if all(row["EvalDecision"] != "allowed" for row in denied_results):
            result.passed("runtime role simulation denies administrative and unrelated-object access")
        else:
            result.failed("runtime role has a broad S3 permission outside the verification scope")
    else:
        result.warning("runtime role was not supplied; IAM allow/deny simulation was not performed")

    if args.canary_key:
        canary_url = f"https://{args.bucket}.s3.{args.region}.amazonaws.com/{quote(args.canary_key)}"
        try:
            with urlopen(Request(canary_url, method="HEAD"), timeout=10):
                result.failed("anonymous retrieval of the synthetic canary succeeded")
        except HTTPError as exc:
            if exc.code in {401, 403}:
                result.passed("anonymous retrieval of the synthetic canary is denied")
            else:
                result.failed("anonymous canary check returned an unexpected response")
        try:
            s3.head_object(Bucket=args.bucket, Key=args.canary_key)
            result.passed("authorized credentials can access synthetic canary metadata")
        except ClientError:
            result.failed("authorized credentials cannot access synthetic canary metadata")
    else:
        result.warning("no synthetic canary key supplied; anonymous and authorized object HEAD checks were skipped")

    print(f"SUMMARY: {result.passes} PASS, {result.warnings} WARNING, {result.failures} FAIL")
    return 1 if result.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--region", required=True)
    parser.add_argument("--prefix", default="creator-verification/")
    parser.add_argument("--event-bucket")
    parser.add_argument("--runtime-role-arn")
    parser.add_argument("--canary-key", help="Existing synthetic object key; never use a real ID.")
    parser.add_argument("--max-retention-days", type=int, default=7)
    return verify(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
