# Cloud-Based Object Detection System using AWS Cloud Services

A beginner-friendly local web application inspired by cloud vision workflows. It uses Flask, OpenCV (optional local camera helper), Amazon Rekognition `DetectLabels`, Amazon S3, and Boto3. **It does not use AWS Panorama APIs, the Panorama CLI, or a Panorama appliance.** AWS Panorama was discontinued in 2026; this project is a local alternative, not a Panorama deployment.

## What it does

- Upload JPG, JPEG, and PNG images or capture a still image using your browser camera.
- Show detected labels and confidence percentages on a responsive dashboard.
- In AWS mode, call Rekognition and store each image and JSON report in a private S3 bucket.
- Keep a recent detection list and object count for the current application process.
- Run immediately in clearly labelled demo mode without AWS credentials. Demo labels are sample data and are never represented as AWS results.

Images are limited to 5 MB. Local image copies are used to display the recent session history; they are stored under `uploads/`, are not exposed as static files, and are excluded from Git. The history is in memory and resets when the process restarts.

## Project layout

```text
cloud-object-detection/
├── app.py
├── aws_services.py
├── camera.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
├── templates/
│   ├── index.html
│   └── results.html
├── static/
│   ├── style.css
│   └── script.js
└── uploads/                 # created automatically; local temporary images
```

## Requirements

- Python 3.10 or later (64-bit recommended)
- Windows, macOS, or Linux
- An AWS account only for live AWS mode
- AWS CLI only for live AWS mode

## Install and run on Windows in VS Code

Open the project folder in VS Code, then run these commands in the integrated PowerShell terminal:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python app.py
```

If PowerShell blocks environment activation, either allow it for the current terminal with `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` and activate again, or call the environment interpreter directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Open **http://127.0.0.1:5000**. Leave `DEMO_MODE=true` to try the interface without AWS. Choose a JPG, JPEG, or PNG image (up to 5 MB) or grant browser camera permission and capture a photo. Demo results are fixed illustrative examples, not analysis of your image.

## Configure live AWS mode

1. Install and configure the AWS CLI. Use the standard credential chain (for example, an AWS CLI profile, IAM Identity Center/SSO, or an assigned role). Do not put access keys in the project or `.env`.

   ```powershell
   aws configure
   aws sts get-caller-identity
   ```

   If using a named profile, set it for the terminal with `$env:AWS_PROFILE = "your-profile-name"` before starting Flask. For AWS IAM Identity Center, sign in with `aws sso login --profile your-profile-name`.

2. Create an S3 bucket in your selected region. Keep **Block Public Access** enabled and do not add a public bucket policy. This application does not grant public access. It writes image and JSON objects with server-side encryption (`AES256`).

3. Give the CLI identity least-privilege permission for Rekognition `rekognition:DetectLabels` and S3 `s3:PutObject` on the chosen bucket's `detections/*` prefix. A basic policy shape (replace placeholders; attach to the intended identity, not to source code) is:

   ```json
   {
     "Version": "2012-10-17",
     "Statement": [
       {
         "Effect": "Allow",
         "Action": "rekognition:DetectLabels",
         "Resource": "*"
       },
       {
         "Effect": "Allow",
         "Action": "s3:PutObject",
         "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/detections/*"
       }
     ]
   }
   ```

   S3 bucket-level encryption, ownership, and public-access-block settings should be configured on the bucket. No `s3:GetObject`, public ACL, or public-read permission is needed by this application.

4. Update `.env` (copied from `.env.example`):

   ```dotenv
   DEMO_MODE=false
   AWS_REGION=us-east-1
   S3_BUCKET_NAME=your-private-bucket-name
   REKOGNITION_MIN_CONFIDENCE=70
   FLASK_DEBUG=false
   ```

   The app loads non-secret configuration from `.env` (with existing environment variables taking precedence). Boto3 reads credentials from its standard AWS credential provider chain. Do not put access keys or secret keys in `.env`. Alternatively, set the values in PowerShell before launching:

   ```powershell
   $env:DEMO_MODE = "false"
   $env:AWS_REGION = "us-east-1"
   $env:S3_BUCKET_NAME = "your-private-bucket-name"
   $env:REKOGNITION_MIN_CONFIDENCE = "70"
   python app.py
   ```

   Or use the `.env` file as a reference and set the variables in your VS Code launch configuration or terminal. The AWS CLI credential store is separate from project files.

5. Upload an image from the dashboard. Live detections will be labelled **AWS LIVE MODE**. A successful response saves an image and a JSON report to separate objects under `detections/YYYY/MM/DD/...` in the configured bucket.

## Configuration and behavior

| Variable | Default | Description |
|---|---|---|
| `DEMO_MODE` | `true` | `true` uses sample labels; `false` requires live AWS credentials and an S3 bucket. |
| `AWS_REGION` | `us-east-1` | Region for Rekognition and S3 clients. |
| `S3_BUCKET_NAME` | empty | Existing private bucket name; required for live mode. |
| `REKOGNITION_MIN_CONFIDENCE` | `70` | Minimum Rekognition confidence threshold, from 0 to 100. |
| `FLASK_DEBUG` | `false` | Enables Flask's local debug server when explicitly set to `true`. |

AWS errors are returned visibly to the dashboard. There is no automatic switch from AWS mode to demo mode. Unsupported files, invalid image data, oversized uploads, camera denial, missing credentials, and AWS service errors are handled with actionable messages.

## Notes

- The dashboard's browser camera works on `localhost` (or an HTTPS origin) after the user grants permission. The optional `camera.py` helper captures from a camera connected to the machine running Python; it is not needed for browser capture.
- This is a local development server. Do not expose Flask's development server directly to the public internet.
- The app has not been tested with your AWS account, credentials, permissions, or bucket. Live integration can only be confirmed after you configure valid AWS credentials and run a real request.
