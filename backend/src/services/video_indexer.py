import os
import time
import logging
import json
import urllib.request
import boto3
import yt_dlp

logger = logging.getLogger("video-indexer")


class VideoIndexerService:
    def __init__(self):
        self.bucket_name = os.getenv("AWS_S3_BUCKET_NAME")
        self.region = os.getenv("AWS_DEFAULT_REGION", "ap-south-1")

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

        # Double extension bug - direct s3_key - happens to work, but
        # the moment someone passes a filename with an extension, we get videos/test_video.mp4.mp4.
        # so we strip to fix this:
        base_name = os.path.splitext(video_name)[0]
        s3_key = f"videos/{base_name}.mp4"

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
        Starts Rekognition text-in-video detection + Amazon Transcribe concurrently, 
        then polls BOTH in a single interleaved loop so a failure in one job is detected
        without leaving the other running orphaned in the background.
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

        rek_status = "IN_PROGRESS"
        transcribe_status = "IN_PROGRESS"
        rek_final_response = None
        transcript_text = ""

        # 3. Interleaved polling: check both jobs each cycle, 
        # stop as soon as EITHER fails (cleanly, without abandoning the other job unchecked).
        while True:
            if rek_status not in ("SUCCEEDED", "FAILED"):
                resp = self.rekognition_client.get_text_detection(JobId=rek_job_id)
                rek_status = resp["JobStatus"]
                if rek_status == "SUCCEEDED":
                    rek_final_response = resp

            if transcribe_status not in ("COMPLETED", "FAILED"):
                job = self.transcribe_client.get_transcription_job(
                    TranscriptionJobName=transcribe_job_name
                )
                transcribe_status = job["TranscriptionJob"]["TranscriptionJobStatus"]
                if transcribe_status == "COMPLETED":
                    transcript_uri = job["TranscriptionJob"]["Transcript"]["TranscriptFileUri"]
                    with urllib.request.urlopen(transcript_uri) as f:
                        transcript_json = json.loads(f.read().decode())
                    transcript_text = transcript_json["results"]["transcripts"][0]["transcript"]

            if rek_status == "FAILED":
                raise Exception(
                    f"Rekognition text detection job failed. "
                    f"(Transcribe job '{transcribe_job_name}' status at failure: {transcribe_status})"
                )
            if transcribe_status == "FAILED":
                raise Exception(
                    f"Transcribe job failed. "
                    f"(Rekognition job status at failure: {rek_status})"
                )

            if rek_status == "SUCCEEDED" and transcribe_status == "COMPLETED":
                break

            logger.info(f"Rekognition: {rek_status} | Transcribe: {transcribe_status} — waiting 15s")
            time.sleep(15)

        if not rek_final_response:
            raise Exception("Rekognition finished without returning a valid response payload.")

        # 4. Paginate through ALL Rekognition text detection pages (NextToken)
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
            "transcript_text": transcript_text,
            "video_metadata_raw": rek_final_response.get("VideoMetadata", {}),
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