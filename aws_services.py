"""Amazon Rekognition and private Amazon S3 helpers."""

import json
import os
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError, PartialCredentialsError


class AWSServiceError(RuntimeError):
    """Raised when an AWS service request fails."""


class AwsConfigurationError(RuntimeError):
    """Raised when required AWS credentials or configuration are unavailable."""


try:
    MIN_CONFIDENCE = float(os.getenv("REKOGNITION_MIN_CONFIDENCE", "70"))
except ValueError as exc:
    raise RuntimeError("REKOGNITION_MIN_CONFIDENCE must be a number from 0 to 100.") from exc
if not 0 <= MIN_CONFIDENCE <= 100:
    raise RuntimeError("REKOGNITION_MIN_CONFIDENCE must be a number from 0 to 100.")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def _session():
    """Build a boto3 session from the standard AWS credential provider chain."""
    session = boto3.Session(region_name=AWS_REGION)
    try:
        credentials = session.get_credentials()
    except (BotoCoreError, ClientError) as exc:
        raise AwsConfigurationError(
            "AWS credentials could not be loaded. Configure the AWS CLI credential chain."
        ) from exc
    if credentials is None:
        raise AwsConfigurationError(
            "No AWS credentials were found. Configure them with `aws configure`, "
            "or set DEMO_MODE=true to use clearly labelled sample results."
        )
    return session


def ensure_s3_bucket_configured():
    """Fail before calling paid services when live-mode storage is not configured."""
    if not os.getenv("S3_BUCKET_NAME", "").strip():
        raise AwsConfigurationError(
            "S3_BUCKET_NAME is required when DEMO_MODE=false. Set it in your environment."
        )


def detect_labels(image_bytes):
    """Call Rekognition DetectLabels and return simplified labels."""
    session = _session()
    try:
        client = session.client("rekognition", region_name=AWS_REGION)
        response = client.detect_labels(
            Image={"Bytes": image_bytes},
            MinConfidence=MIN_CONFIDENCE,
            MaxLabels=50,
        )
    except (NoCredentialsError, PartialCredentialsError) as exc:
        raise AwsConfigurationError(
            "AWS credentials are missing or incomplete. Configure the AWS CLI credential chain."
        ) from exc
    except (BotoCoreError, ClientError) as exc:
        raise AWSServiceError(
            "Amazon Rekognition could not process this image. Check your AWS region, "
            "permissions, and service quotas."
        ) from exc

    return [
        {
            "name": label["Name"],
            "confidence": round(float(label["Confidence"]), 2),
            "instances_count": len(label.get("Instances", [])),
        }
        for label in response.get("Labels", [])
    ]


def save_to_s3(image_bytes, report, extension):
    """Store an image and its JSON report without granting public access."""
    ensure_s3_bucket_configured()
    bucket_name = os.getenv("S3_BUCKET_NAME", "").strip()

    session = _session()
    object_id = uuid.uuid4().hex
    timestamp = datetime.now(timezone.utc)
    image_key = "detections/{}/{}/image.{}".format(
        timestamp.strftime("%Y/%m/%d"), object_id, extension
    )
    report_key = "detections/{}/{}/report.json".format(
        timestamp.strftime("%Y/%m/%d"), object_id
    )
    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    content_type = "image/png" if extension == "png" else "image/jpeg"

    try:
        client = session.client("s3", region_name=AWS_REGION)
        client.put_object(
            Bucket=bucket_name,
            Key=image_key,
            Body=image_bytes,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        client.put_object(
            Bucket=bucket_name,
            Key=report_key,
            Body=report_bytes,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
    except (NoCredentialsError, PartialCredentialsError) as exc:
        raise AwsConfigurationError(
            "AWS credentials are missing or incomplete. Configure the AWS CLI credential chain."
        ) from exc
    except (BotoCoreError, ClientError) as exc:
        raise AWSServiceError(
            "Amazon S3 could not save the image and report. Check the bucket name, "
            "region, and s3:PutObject permission."
        ) from exc

    return {"bucket": bucket_name, "image_key": image_key, "report_key": report_key}
