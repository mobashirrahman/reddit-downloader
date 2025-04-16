#!/usr/bin/env python3
"""
Reddit Media Downloader - A tool to download images and videos from Reddit subreddits.
"""
import argparse
import datetime
import logging
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Tuple, Union

import praw
import requests
from dotenv import load_dotenv


class RedditDownloader:
    """Main class for downloading media from Reddit subreddits."""

    def __init__(self, config: Dict[str, Union[str, int, bool]]) -> None:
        """Initialize the downloader with configuration options.

        Args:
            config: Dictionary containing configuration options.
        """
        self.config = config
        self.logger = self._setup_logger()
        self.reddit = self._authenticate_reddit()
        self.stats = {
            "total_posts_processed": 0,
            "images_downloaded": 0,
            "videos_downloaded": 0,
            "audio_merged": 0,
            "errors": 0,
            "skipped": 0
        }
        
        # Check for ffmpeg if audio download is enabled
        if self.config.get("download_audio", False):
            self._check_ffmpeg()

    def _check_ffmpeg(self) -> None:
        """Check if ffmpeg is installed and available."""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            if result.returncode == 0:
                self.logger.debug("ffmpeg is available")
                self.ffmpeg_available = True
            else:
                self.logger.warning("ffmpeg command returned non-zero exit code")
                self.ffmpeg_available = False
        except FileNotFoundError:
            self.logger.warning(
                "ffmpeg not found. Audio merging will be disabled. "
                "Please install ffmpeg to enable audio merging."
            )
            self.ffmpeg_available = False

    def _setup_logger(self) -> logging.Logger:
        """Set up logging to both console and file.

        Returns:
            Logger object.
        """
        logger = logging.getLogger("reddit_downloader")
        logger.setLevel(logging.DEBUG if self.config["debug"] else logging.INFO)

        # Create logs directory if it doesn't exist
        os.makedirs("logs", exist_ok=True)

        # Log to file
        log_file = os.path.join(
            "logs",
            f"reddit_downloader_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        )
        file_handler = logging.FileHandler(log_file)
        file_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        # Log to console if verbose mode is enabled
        if self.config["verbose"]:
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter('%(levelname)s: %(message)s')
            console_handler.setFormatter(console_formatter)
            console_handler.setLevel(logging.INFO)
            logger.addHandler(console_handler)

        return logger

    def _authenticate_reddit(self) -> praw.Reddit:
        """Authenticate with Reddit API using credentials from environment.

        Returns:
            Authenticated Reddit instance.

        Raises:
            SystemExit: If authentication fails.
        """
        try:
            self.logger.debug("Authenticating with Reddit API")
            
            # For client credentials flow
            if self.config.get("use_access_token", False):
                auth = requests.auth.HTTPBasicAuth(
                    self.config["client_id"],
                    self.config["client_secret"]
                )
                headers = {'User-Agent': self.config["user_agent"]}
                data = {'grant_type': 'client_credentials'}
                
                self.logger.debug("Obtaining access token")
                response = requests.post(
                    'https://www.reddit.com/api/v1/access_token',
                    auth=auth,
                    data=data,
                    headers=headers,
                    timeout=30
                )
                response.raise_for_status()
                access_token = response.json()['access_token']
                
                reddit = praw.Reddit(
                    client_id=self.config["client_id"],
                    client_secret=self.config["client_secret"],
                    user_agent=self.config["user_agent"],
                    access_token=access_token
                )
            else:
                # Standard PRAW authentication
                reddit = praw.Reddit(
                    client_id=self.config["client_id"],
                    client_secret=self.config["client_secret"],
                    user_agent=self.config["user_agent"]
                )
                
            self.logger.info("Successfully authenticated with Reddit API")
            return reddit
            
        except Exception as e:
            self.logger.critical(f"Failed to authenticate with Reddit: {str(e)}")
            sys.exit(1)

    def _sanitize_filename(self, title: str) -> str:
        """Sanitize a string to make it a valid filename.

        Args:
            title: Original title string.

        Returns:
            Sanitized filename string.
        """
        # Replace invalid characters with underscore
        sanitized = re.sub(r'[\\/*?:"<>|]', '_', title)
        # Replace spaces with underscore if configured
        if self.config.get("replace_spaces", True):
            sanitized = sanitized.replace(' ', '_')
        # Truncate if too long
        max_length = self.config.get("max_filename_length", 100)
        if len(sanitized) > max_length:
            sanitized = sanitized[:max_length]
        
        return sanitized

    def _create_directories(self, subreddit: str) -> Tuple[str, str]:
        """Create directories for storing downloaded media.

        Args:
            subreddit: Name of the subreddit.

        Returns:
            Tuple of (video_path, image_path).
        """
        base_dir = self.config.get("output_dir", ".")
        subreddit_dir = os.path.join(base_dir, subreddit)
        
        video_path = os.path.join(subreddit_dir, "videos")
        image_path = os.path.join(subreddit_dir, "images")
        
        os.makedirs(video_path, exist_ok=True)
        os.makedirs(image_path, exist_ok=True)
        
        self.logger.debug(f"Created directories for subreddit {subreddit}")
        return video_path, image_path

    def _download_file(self, url: str, file_path: str, retries: int = 3) -> bool:
        """Download a file from a URL with retry logic.

        Args:
            url: URL to download from.
            file_path: Path to save the file.
            retries: Number of retry attempts.

        Returns:
            bool: True if download was successful, False otherwise.
        """
        if os.path.exists(file_path) and not self.config.get("overwrite", False):
            self.logger.info(f"Skipping existing file: {file_path}")
            self.stats["skipped"] += 1
            return True

        for attempt in range(retries):
            try:
                self.logger.debug(
                    f"Downloading {url} to {file_path} (attempt {attempt + 1})"
                )
                
                with requests.get(url, stream=True, timeout=30) as response:
                    response.raise_for_status()
                    
                    # Check if file size exceeds limit
                    size_limit = self.config.get("max_file_size_mb", 0)
                    if size_limit > 0:
                        content_length = int(response.headers.get('content-length', 0))
                        if content_length > size_limit * 1024 * 1024:
                            self.logger.warning(
                                f"File exceeds size limit "
                                f"({content_length / (1024 * 1024):.2f}MB > "
                                f"{size_limit}MB): {url}"
                            )
                            return False
                    
                    with open(file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                
                self.logger.info(f"Successfully downloaded: {os.path.basename(file_path)}")
                return True
                
            except (requests.RequestException, IOError) as e:
                self.logger.warning(f"Download attempt {attempt + 1} failed: {str(e)}")
                if attempt == retries - 1:
                    self.logger.error(f"Failed to download {url} after {retries} attempts")
                    self.stats["errors"] += 1
                    return False
                time.sleep(2 ** attempt)  # Exponential backoff

        return False

    def _derive_audio_url(self, video_url: str) -> str:
        """Derive the audio URL from the video URL.
        
        Args:
            video_url: URL of the video
            
        Returns:
            URL of the audio track
        """
        # Reddit video URLs typically look like:
        # https://v.redd.it/VIDEO_ID/DASH_720.mp4
        
        # There are multiple possible audio URL patterns
        # 1. DASH_audio.mp4
        # 2. audio
        # 3. DASH_audio.m4a
        
        # Extract the base URL (everything before the quality indicator)
        if 'DASH_' in video_url:
            base_url = video_url.split('DASH_')[0]
        else:
            # If no DASH_ in URL, try to extract base URL from the last slash before .mp4
            parts = video_url.split('/')
            base_url = '/'.join(parts[:-1]) + '/'
            
        # Try different audio formats/patterns that Reddit might use
        audio_patterns = [
            "DASH_audio.mp4",
            "audio",
            "DASH_audio.m4a",
            "audio.mp4"
        ]
        
        # We'll return the first pattern, but log that we're trying multiple
        self.logger.debug(f"Attempting to derive audio URL from {video_url}")
        for pattern in audio_patterns:
            self.logger.debug(f"Trying audio pattern: {pattern}")
            
        return f"{base_url}{audio_patterns[0]}"
        
    def _merge_audio_video(self, video_path: str, audio_path: str, output_path: str) -> bool:
        """Merge audio and video files using ffmpeg.
        
        Args:
            video_path: Path to the video file
            audio_path: Path to the audio file
            output_path: Path to save the merged file
            
        Returns:
            bool: True if merge was successful, False otherwise
        """
        if not self.ffmpeg_available:
            self.logger.warning("Cannot merge audio: ffmpeg not available")
            return False
            
        try:
            self.logger.debug(f"Merging {video_path} and {audio_path} to {output_path}")
            
            # Run ffmpeg to merge the files
            result = subprocess.run(
                [
                    'ffmpeg',
                    '-i', video_path,
                    '-i', audio_path,
                    '-c:v', 'copy',      # Copy the video stream without re-encoding
                    '-c:a', 'aac',       # Use AAC codec for audio
                    '-strict', 'experimental',
                    '-loglevel', 'warning',
                    '-y',                # Overwrite output file if it exists
                    output_path
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                self.logger.info(
                    f"Successfully merged audio and video: {os.path.basename(output_path)}"
                )
                self.stats["audio_merged"] += 1
                return True
            else:
                self.logger.error(f"Failed to merge audio and video: {result.stderr}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error merging audio and video: {str(e)}")
            return False

    def process_post(self, post: praw.models.Submission, video_path: str,
                     image_path: str) -> None:
        """Process a single Reddit post to download its media.

        Args:
            post: Reddit post submission.
            video_path: Path to save videos.
            image_path: Path to save images.
        """
        try:
            url = post.url
            title = post.title
            upvotes = post.ups
            
            # Skip posts that don't meet minimum score threshold
            if upvotes < self.config.get("min_score", 0):
                self.logger.debug(
                    f"Skipping post with low score: "
                    f"{upvotes} < {self.config.get('min_score', 0)}"
                )
                return
                
            self.logger.debug(f"Processing post: {title} ({url})")
            
            # Sanitize filename
            sanitized_title = self._sanitize_filename(title)
            
            # Format filename according to template
            if self.config.get("include_score", True):
                filename = f"{upvotes}_{sanitized_title}"
            else:
                filename = sanitized_title
                
            # Check if it's an image
            if any(url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                if not self.config.get("download_images", True):
                    return
                    
                file_path = os.path.join(image_path, f"{filename}.{url.split('.')[-1]}")
                if self._download_file(url, file_path):
                    self.stats["images_downloaded"] += 1
                    
            # Check if it's a video
            elif post.is_video and self.config.get("download_videos", True):
                try:
                    # Get video details
                    video_data = post.media['reddit_video']
                    video_url = video_data['fallback_url']
                    has_audio = video_data.get('has_audio', True)  # Assume it has audio
                    
                    self.logger.debug(f"Processing video with URL: {video_url}")
                    self.logger.debug(f"Video metadata indicates has_audio = {has_audio}")
                    
                    video_file_path = os.path.join(video_path, f"{filename}.mp4")
                    
                    # Download video file
                    if self._download_file(video_url, video_file_path):
                        self.stats["videos_downloaded"] += 1
                        
                        # Download audio if enabled, ffmpeg available, and video has audio
                        if (self.config.get("download_audio", False) and
                                self.ffmpeg_available and has_audio):
                            # Try all possible audio URL patterns
                            audio_tried = False
                            audio_found = False
                            
                            # Derive possible audio URL
                            if 'DASH_' in video_url:
                                base_url = video_url.split('DASH_')[0]
                            else:
                                parts = video_url.split('/')
                                base_url = '/'.join(parts[:-1]) + '/'
                                
                            audio_patterns = [
                                "DASH_audio.mp4",
                                "audio",
                                "DASH_audio.m4a",
                                "audio.mp4"
                            ]
                            
                            # Try each audio pattern
                            for pattern in audio_patterns:
                                audio_url = f"{base_url}{pattern}"
                                audio_file_path = os.path.join(
                                    video_path,
                                    f"{filename}_audio.mp4"
                                )
                                
                                self.logger.debug(f"Trying audio URL: {audio_url}")
                                audio_tried = True
                                
                                try:
                                    # Quick check if audio exists at this URL
                                    check_response = requests.head(audio_url, timeout=10)
                                    if check_response.status_code != 200:
                                        self.logger.debug(
                                            f"Audio pattern {pattern} not found "
                                            f"(status: {check_response.status_code})"
                                        )
                                        continue
                                        
                                    # Download the audio
                                    if self._download_file(audio_url, audio_file_path):
                                        self.logger.info(f"Found audio with pattern: {pattern}")
                                        audio_found = True
                                        
                                        # Merge audio and video
                                        merged_file_path = os.path.join(
                                            video_path,
                                            f"{filename}_with_audio.mp4"
                                        )
                                        if self._merge_audio_video(
                                                video_file_path,
                                                audio_file_path,
                                                merged_file_path
                                        ):
                                            # Remove separate audio file if merging was successful
                                            if self.config.get("cleanup_after_merge", True):
                                                os.remove(audio_file_path)
                                                if not self.config.get("keep_video_only", False):
                                                    os.remove(video_file_path)
                                        break  # Successfully processed audio
                                        
                                except requests.RequestException as e:
                                    self.logger.debug(f"Error checking audio URL {audio_url}: {str(e)}")
                                    continue
                            
                            if audio_tried and not audio_found:
                                self.logger.warning(f"No suitable audio found for video: {video_url}")
                                
                except (KeyError, TypeError, AttributeError) as e:
                    self.logger.error(f"Error extracting video URL: {str(e)}")
                
            # Check for gallery posts
            elif (hasattr(post, 'is_gallery') and
                  post.is_gallery and
                  self.config.get("download_galleries", True)):
                self.logger.info(f"Gallery post detected: {post.id}")
                # Gallery download logic would go here
                
            self.stats["total_posts_processed"] += 1
            
        except Exception as e:
            self.logger.error(f"Error processing post {post.id}: {str(e)}")
            self.stats["errors"] += 1

    def download_from_subreddit(self, subreddit_name: str) -> None:
        """Download media from a specific subreddit.

        Args:
            subreddit_name: Name of the subreddit to download from.
        """
        try:
            self.logger.info(f"Processing subreddit: r/{subreddit_name}")
            
            # Get subreddit instance
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Get posts based on sort method
            sort_method = self.config.get("sort", "hot").lower()
            limit = self.config.get("limit", 25)
            
            self.logger.info(f"Fetching {limit} {sort_method} posts from r/{subreddit_name}")
            
            if sort_method == "hot":
                posts = subreddit.hot(limit=limit)
            elif sort_method == "new":
                posts = subreddit.new(limit=limit)
            elif sort_method == "top":
                time_filter = self.config.get("time_filter", "all")
                posts = subreddit.top(time_filter=time_filter, limit=limit)
            else:
                posts = subreddit.hot(limit=limit)
                
            # Create directories
            video_path, image_path = self._create_directories(subreddit_name)
            
            # Process posts
            if self.config.get("multithreaded", False):
                with ThreadPoolExecutor(max_workers=self.config.get("max_workers", 4)) as executor:
                    for post in posts:
                        executor.submit(self.process_post, post, video_path, image_path)
            else:
                total_posts = limit  # Approximate since we can't get exact count from generator
                for i, post in enumerate(posts, 1):
                    if self.config["verbose"]:
                        print(f"\rProcessing post {i}/{total_posts} from r/{subreddit_name}", end="")
                    self.process_post(post, video_path, image_path)
                
                if self.config["verbose"]:
                    print()  # New line after progress indicator
                    
        except Exception as e:
            self.logger.error(f"Error processing subreddit {subreddit_name}: {str(e)}")
            self.stats["errors"] += 1

    def run(self) -> None:
        """Run the downloader for all configured subreddits."""
        start_time = time.time()
        self.logger.info(
            f"Starting Reddit media downloader with {len(self.config['subreddits'])} subreddits"
        )
        
        for subreddit_name in self.config["subreddits"]:
            self.download_from_subreddit(subreddit_name)
            
        elapsed_time = time.time() - start_time
        
        # Print summary
        self.logger.info("=" * 50)
        self.logger.info("Download Summary:")
        self.logger.info(f"  Total posts processed: {self.stats['total_posts_processed']}")
        self.logger.info(f"  Images downloaded: {self.stats['images_downloaded']}")
        self.logger.info(f"  Videos downloaded: {self.stats['videos_downloaded']}")
        self.logger.info(f"  Videos with audio merged: {self.stats['audio_merged']}")
        self.logger.info(f"  Files skipped: {self.stats['skipped']}")
        self.logger.info(f"  Errors: {self.stats['errors']}")
        self.logger.info(f"  Time elapsed: {elapsed_time:.2f} seconds")
        self.logger.info("=" * 50)


def read_subreddits_from_file(filename: str) -> List[str]:
    """Read list of subreddits from a file.

    Args:
        filename: Path to the file containing subreddit names.

    Returns:
        List of subreddit names.
    """
    try:
        with open(filename, 'r') as f:
            # Strip whitespace and skip empty lines or comments
            return [line.strip() for line in f if line.strip() and not line.startswith('#')]
    except Exception as e:
        print(f"Error reading subreddit file: {str(e)}")
        sys.exit(1)


def parse_arguments() -> Dict[str, Union[str, int, bool]]:
    """Parse command-line arguments.

    Returns:
        Dictionary of configuration options.
    """
    parser = argparse.ArgumentParser(
        description="Download images and videos from Reddit subreddits"
    )
    
    # Required arguments
    group = parser.add_argument_group('Reddit Authentication')
    group.add_argument("--client-id", help="Reddit API client ID")
    group.add_argument("--client-secret", help="Reddit API client secret")
    
    # Input sources
    parser.add_argument(
        "-s", "--subreddits", nargs="+",
        help="List of subreddit names to download from"
    )
    parser.add_argument("-f", "--file", help="Path to file containing subreddit names")
    
    # Output options
    parser.add_argument(
        "-o", "--output-dir", default=".",
        help="Base directory to save downloaded files"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Overwrite existing files"
    )
    
    # Download filtering
    parser.add_argument(
        "--sort", choices=["hot", "new", "top"], default="hot",
        help="Sort method for posts"
    )
    parser.add_argument(
        "--time-filter", choices=["hour", "day", "week", "month", "year", "all"],
        default="all", help="Time filter for 'top' sort method"
    )
    parser.add_argument(
        "--limit", type=int, default=25,
        help="Maximum number of posts to process per subreddit"
    )
    parser.add_argument(
        "--min-score", type=int, default=0,
        help="Minimum score (upvotes) required to download a post"
    )
    
    # Media types
    parser.add_argument(
        "--no-images", dest="download_images", action="store_false",
        help="Skip downloading images"
    )
    parser.add_argument(
        "--no-videos", dest="download_videos", action="store_false",
        help="Skip downloading videos"
    )
    parser.add_argument(
        "--download-galleries", action="store_true",
        help="Download gallery posts (multiple images)"
    )
    
    # Audio options
    parser.add_argument(
        "--download-audio", action="store_true",
        help="Download and merge audio for videos (requires ffmpeg)"
    )
    parser.add_argument(
        "--keep-video-only", action="store_true",
        help="Keep video-only file after merging with audio"
    )
    parser.add_argument(
        "--no-cleanup", dest="cleanup_after_merge", action="store_false",
        help="Don't remove temporary audio files after merging"
    )
    
    # Performance options
    parser.add_argument(
        "--multithreaded", action="store_true",
        help="Use multiple threads for downloading"
    )
    parser.add_argument(
        "--max-workers", type=int, default=4,
        help="Maximum number of worker threads when multithreaded"
    )
    parser.add_argument(
        "--max-file-size-mb", type=int, default=0,
        help="Maximum file size to download in MB (0 for no limit)"
    )
    
    # Logging options
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable verbose output"
    )
    parser.add_argument(
        "-d", "--debug", action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Load .env file if available
    load_dotenv()
    
    # Configuration dictionary
    config = {
        # Set from environment variables or command line arguments
        "client_id": args.client_id or os.getenv("REDDIT_CLIENT_ID"),
        "client_secret": args.client_secret or os.getenv("REDDIT_CLIENT_SECRET"),
        "user_agent": os.getenv("REDDIT_USER_AGENT", "MediaDownloader/1.0 (by /u/anonymous)"),
        
        # Command line arguments
        "output_dir": args.output_dir,
        "sort": args.sort,
        "time_filter": args.time_filter,
        "limit": args.limit,
        "min_score": args.min_score,
        "download_images": args.download_images,
        "download_videos": args.download_videos,
        "download_galleries": args.download_galleries,
        "download_audio": args.download_audio,
        "keep_video_only": args.keep_video_only,
        "cleanup_after_merge": args.cleanup_after_merge,
        "multithreaded": args.multithreaded,
        "max_workers": args.max_workers,
        "max_file_size_mb": args.max_file_size_mb,
        "verbose": args.verbose,
        "debug": args.debug,
        "overwrite": args.overwrite,
        "use_access_token": True,  # Use the token-based authentication
        
        # Additional configuration options
        "include_score": True,
        "replace_spaces": True,
        "max_filename_length": 100,
    }
    
    # Get subreddits from file or command line
    if args.file:
        config["subreddits"] = read_subreddits_from_file(args.file)
    elif args.subreddits:
        config["subreddits"] = args.subreddits
    elif os.path.exists("subreddits.txt"):
        # Try default file
        config["subreddits"] = read_subreddits_from_file("subreddits.txt")
    else:
        print("Error: No subreddits specified. Use --subreddits or --file options.")
        parser.print_help()
        sys.exit(1)
        
    # Validate required configuration
    if not config["client_id"] or not config["client_secret"]:
        print("Error: Reddit API credentials required.")
        print("Either set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables")
        print("or provide --client-id and --client-secret command line arguments.")
        sys.exit(1)
        
    return config


def main() -> None:
    """Main entry point for the application."""
    try:
        # Parse arguments and create configuration
        config = parse_arguments()
        
        # Create and run the downloader
        downloader = RedditDownloader(config)
        downloader.run()
        
    except KeyboardInterrupt:
        print("\nDownload interrupted by user.")
        sys.exit(0)
        
    except Exception as e:
        print(f"Error: {str(e)}")
        if "--debug" in sys.argv:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()