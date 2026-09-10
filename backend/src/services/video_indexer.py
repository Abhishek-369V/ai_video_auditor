import os
import time
import logging
import boto3
import yt_dlp  

logger = logging.getLogger("video-indexer")

class VideoIndexerService:
    def __init__(self):
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.region = os.getenv("AWS_DEFAULT_REGION", "ap-south-2")

        if not self.bucket_name:
            raise Exception("AWS_S3_BUCKET_NAME not set in .env")

        self.s3_client = boto3.client("s3", region_name=self.region)
        self.rekognition_client = boto3.client("rekognition", region_name=self.region)
        self.transcribe_client = boto3.client("transcribe", region_name=self.region)

    # --- Download from YouTube ---
    def download_youtube_video(self, url, output_path="temp_video.mp4"):
        """Downloads a YouTube video to a local file."""
        logger.info(f"Downloading YouTube video: {url}")

        ydl_opts = {
            'format': 'best',
            'outtmpl': output_path,
            'quiet': False,
            'no_warnings': False,
            'extractor_args': {'youtube': {'player_client': ['android', 'web']}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Download complete.")
            return output_path
        except Exception as e:
            raise Exception(f"YouTube Download Failed: {str(e)}")

    # --- Upload to S3 (replaces Azure upload) ---
    def upload_video(self, video_path, video_name):
        """Uploads a LOCAL FILE to S3. Returns the S3 key (used as 'video_id')."""
        s3_key = f"videos/{video_name}.mp4"

        logger.info(f"Uploading {video_path} to s3://{self.bucket_name}/{s3_key}...")
        try:
            self.s3_client.upload_file(video_path, self.bucket_name, s3_key)
        except Exception as e:
            raise Exception(f"S3 Upload Failed: {str(e)}")

        return s3_key

    # --- Start + poll Rekognition Text Detection and Transcribe ---
    def wait_for_processing(self, video_id):
        """
        video_id here = S3 key returned by upload_video().
        Starts Rekognition text-in-video detection + Amazon Transcribe,
        polls both until COMPLETED, returns a combined raw result dict.
        """
        s3_key = video_id
        job_tag = s3_key.replace("/", "_").replace(".", "_")

        # 1. Start Rekognition text detection
        logger.info("Starting Rekognition text detection job...")
        rek_response = self.rekognition_client.start_text_detection(
            Video={"S3Object": {"Bucket": self.bucket_name, "Name": s3_key}}
        )
        rek_job_id = rek_response["JobId"]

        # 2. Start Transcribe job
        logger.info("Starting Transcribe job...")
        transcribe_job_name = f"transcribe_{job_tag}_{int(time.time())}"
        media_uri = f"s3://{self.bucket_name}/{s3_key}"
        self.transcribe_client.start_transcription_job(
            TranscriptionJobName=transcribe_job_name,
            Media={"MediaFileUri": media_uri},
            MediaFormat="mp4",
            LanguageCode="en-US",
        )

        # 3. Poll Rekognition
        rek_result = None
        while True:
            resp = self.rekognition_client.get_text_detection(JobId=rek_job_id)
            status = resp["JobStatus"]
            if status == "SUCCEEDED":
                rek_result = resp
                break
            elif status == "FAILED":
                raise Exception("Rekognition text detection job failed.")
            logger.info(f"Rekognition status: {status}... waiting 15s")
            time.sleep(15)

        # 4. Poll Transcribe
        transcript_text = ""
        while True:
            job = self.transcribe_client.get_transcription_job(
                TranscriptionJobName=transcribe_job_name
            )
            status = job["TranscriptionJob"]["TranscriptionJobStatus"]
            if status == "COMPLETED":
                transcript_uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                import urllib.request, json as jsonlib
                with urllib.request.urlopen(transcript_uri) as f:
                    transcript_json = jsonlib.loads(f.read().decode())
                transcript_text = transcript_json["results"]["transcripts"][0]["transcript"]
                break
            elif status == "FAILED":
                raise Exception("Transcribe job failed.")
            logger.info(f"Transcribe status: {status}... waiting 15s")
            time.sleep(15)

        return {
            "rekognition_text_detections": rek_result.get("TextDetections", []),
            "transcript_text": transcript_text,
            "video_metadata_raw": rek_result.get("VideoMetadata", {}),
        }

    # --- Extract data into the same output shape as before ---
    def extract_data(self, raw_result):
        """Parses the combined Rekognition + Transcribe result into State format."""
        ocr_lines = []
        seen = set()
        for det in raw_result.get("rekognition_text_detections", []):
            text = det.get("TextDetection", {}).get("DetectedText")
            if text and text not in seen:
                ocr_lines.append(text)
                seen.add(text)

        duration_ms = raw_result.get("video_metadata_raw", {}).get("DurationMillis")
        duration_seconds = (duration_ms / 1000) if duration_ms else None

        return {
            "transcript": raw_result.get("transcript_text", ""),
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration": duration_seconds,
                "platform": "youtube"
            }
        }