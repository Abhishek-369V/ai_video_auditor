import os
import time
import logging
import boto3
import yt_dlp
import whisper

logger = logging.getLogger("video-indexer")


class VideoIndexerService:
    def __init__(self):
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

        if not self.bucket_name:
            raise Exception("AWS_S3_BUCKET_NAME not set in .env")

        self.s3_client = boto3.client("s3", region_name=self.region)
        self.rekognition_client = boto3.client("rekognition", region_name=self.region)

        self._whisper_model = None  # lazy-loaded on first use

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

    # --- Local transcription via Whisper (replaces Amazon Transcribe) ---
    def _get_whisper_model(self):
        if self._whisper_model is None:
            logger.info("Loading Whisper model (base)... this may take a moment on first run.")
            self._whisper_model = whisper.load_model("base")
            logger.info("Whisper model loaded.")
        return self._whisper_model

    def transcribe_locally(self, video_path):
        """
        Transcribes the given LOCAL video/audio file using OpenAI Whisper, running entirely offline. 
        Must be called BEFORE the local file is deleted (i.e., before upload_video's caller does any cleanup).
        """
        if not os.path.exists(video_path):
            raise Exception(f"Cannot transcribe — file not found: {video_path}")

        model = self._get_whisper_model()
        logger.info(f"Transcribing {video_path} locally with Whisper...")
        try:
            result = model.transcribe(video_path)
            transcript_text = result.get("text", "").strip()
            logger.info(f"Whisper transcription complete ({len(transcript_text)} chars).")
            return transcript_text
        except Exception as e:
            raise Exception(f"Whisper transcription failed: {str(e)}")

    # --- Upload to S3 (for Rekognition text detection only now) ---
    def upload_video(self, video_path, video_name):
        """Uploads a LOCAL FILE to S3. Returns the S3 key (used as 'video_id').

        Strips any existing extension from video_name before appending .mp4,
        so passing 'clip.mp4' doesn't produce 'clip.mp4.mp4'.
        """
        base_name = os.path.splitext(video_name)[0]
        s3_key = f"videos/{base_name}.mp4"

        logger.info(f"Uploading {video_path} to s3://{self.bucket_name}/{s3_key}...")
        try:
            self.s3_client.upload_file(video_path, self.bucket_name, s3_key)
        except Exception as e:
            raise Exception(f"S3 Upload Failed: {str(e)}")

        return s3_key

    # --- Rekognition text detection only (Transcribe removed) ---
    def wait_for_processing(self, video_id):
        """
        video_id = S3 key returned by upload_video().
        Starts Rekognition text detection and polls until SUCCEEDED/FAILED.
        Paginates through all result pages via NextToken.
        """
        s3_key = video_id

        # Start Rekognition text detection
        logger.info("Starting Rekognition text detection job...")
        rek_response = self.rekognition_client.start_text_detection(
            Video={"S3Object": {"Bucket": self.bucket_name, "Name": s3_key}}
        )
        rek_job_id = rek_response["JobId"]

        rek_final_response = None
        while True:
            resp = self.rekognition_client.get_text_detection(JobId=rek_job_id)
            status = resp["JobStatus"]

            if status == "SUCCEEDED":
                rek_final_response = resp
                break
            elif status == "FAILED":
                raise Exception("Rekognition text detection job failed.")

            logger.info(f"Rekognition status: {status}... waiting 15s")
            time.sleep(15)

        # Paginate through ALL Rekognition text detection pages (NextToken)
        all_text_detections = list(rek_final_response.get("TextDetections", []))
        next_token = rek_final_response.get("NextToken")
        while next_token:
            page = self.rekognition_client.get_text_detection(
                JobId=rek_job_id, NextToken=next_token
            )
            all_text_detections.extend(page.get("TextDetections", []))
            next_token = page.get("NextToken")

        return {
            "rekognition_text_detections": all_text_detections,
            "video_metadata_raw": rek_final_response.get("VideoMetadata", {}),
        }

    # --- Extract data into the output shape used by state.py ---
    def extract_data(self, raw_result):
        """Parses the Rekognition OCR result into State format.
        NOTE: 'transcript' is intentionally NOT set here anymore —
        it's injected separately by the caller from transcribe_locally().
        """
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
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration": duration_seconds,
                "platform": "youtube"
            }
        }