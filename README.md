<h1 align="center">Reddit Media Downloader</h1>

<div align="center">

📥 Download videos, images and audio from Reddit subreddits with ease and flexibility!

![Python](https://img.shields.io/badge/python-3.6+-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)
![PRAW](https://img.shields.io/badge/PRAW-7.7+-FF5700?style=for-the-badge&logo=reddit&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green?style=for-the-badge)
![FFmpeg](https://img.shields.io/badge/FFmpeg-optional-007808?style=for-the-badge&logo=ffmpeg&logoColor=white)

<p align="center">
  <a href="#-key-features">Features</a> •
  <a href="#-installation">Installation</a> •
  <a href="#-setup">Setup</a> •
  <a href="#-usage">Usage</a> •
  <a href="#-examples">Examples</a> •
  <a href="#-configuration">Configuration</a>
</p>

</div>

## 📋 Overview

This powerful tool downloads media content from any subreddit, organizing files by type and preserving metadata. It offers extensive customization options and handles various media types including videos with audio when available.

### 🌟 Key Features

- ✅ **Multi-subreddit support** - Download from multiple subreddits simultaneously
- ✅ **Audio extraction** - Downloads and merges audio with videos (requires FFmpeg)
- ✅ **Flexible filtering** - Filter by post score, sort method, and time period
- ✅ **Multithreaded downloads** - Parallel processing for faster operation
- ✅ **Comprehensive logging** - Detailed logs and progress tracking
- ✅ **Customizable output** - Organize downloads your way
- ✅ **Retry logic** - Handles network issues with exponential backoff
- ✅ **Secure credentials** - Environment variables for API keys

## 🔧 Installation

Clone the repository and install dependencies:

```bash
# Clone the repository
git clone https://github.com/mobashirrahman/reddit-downloader.git
cd reddit-downloader

# Install required packages
pip install -r requirements.txt

# For audio support (optional but recommended)
sudo apt-get install ffmpeg    # Ubuntu/Debian
# or
brew install ffmpeg            # macOS with Homebrew
```

## 🔑 Setup

### 1. Create Reddit API Credentials

1. Visit [Reddit's App Preferences](https://www.reddit.com/prefs/apps)
2. Scroll down and click "create another app..."
3. Fill in the details:
   - Name: `RedditMediaDownloader` (or any name)
   - Type: select "script"
   - Description: optional
   - About URL: optional
   - Redirect URI: `http://localhost:8080` (this isn't used but is required)
4. Click "create app"
5. Note your `client_id` (the string under "personal use script") and `client_secret`

### 2. Configure Environment

Create a `.env` file in the project directory:

```
REDDIT_CLIENT_ID=your_client_id
REDDIT_CLIENT_SECRET=your_client_secret
REDDIT_USER_AGENT=RedditMediaDownloader/1.0
```

### 3. Create Subreddit List

Create a `subreddits.txt` file with subreddit names (one per line):

```
# Popular image subreddits
EarthPorn
itookapicture
pics

# Video subreddits
Whatcouldgowrong
PublicFreakout

# Comments starting with # are ignored
```

## 🚀 Usage

### Basic Usage

```bash
python reddit.py
```

This will read subreddits from `subreddits.txt` and download the latest hot posts.

### Command-line Options

#### 📚 Input Sources
- `-s, --subreddits [NAMES]`: Specify subreddits on command line
- `-f, --file PATH`: Use a custom subreddit list file

#### 📂 Output Options
- `-o, --output-dir DIR`: Set base download directory
- `--overwrite`: Replace existing files

#### 🔍 Content Filtering
- `--sort {hot,new,top}`: Choose sort method
- `--time-filter {hour,day,week,month,year,all}`: Timeframe for top posts
- `--limit NUM`: Maximum posts per subreddit (default: 25)
- `--min-score NUM`: Minimum upvotes required

#### 🖼️ Media Controls
- `--no-images`: Skip image downloads
- `--no-videos`: Skip video downloads
- `--download-galleries`: Include gallery posts
- `--download-audio`: Get audio for videos (requires FFmpeg)
- `--keep-video-only`: Keep video file after merging with audio

#### ⚡ Performance
- `--multithreaded`: Enable parallel downloads
- `--max-workers NUM`: Set number of threads (default: 4)
- `--max-file-size-mb SIZE`: Limit file size (0 for no limit)

#### 📊 Logging
- `-v, --verbose`: Show download progress
- `-d, --debug`: Enable detailed logs

## 💡 Examples

### Download Top Weekly Posts with High Upvotes

```bash
python reddit.py -s EarthPorn NatureIsFuckingLit --sort top --time-filter week --min-score 5000 -v
```

### Download Only Videos with Audio

```bash
python reddit.py --no-images --download-audio --multithreaded
```

### Mass Download with Custom Organization

```bash
python reddit.py -f my_special_subreddits.txt -o ./reddit_archive --limit 100 --multithreaded --max-workers 8 -v
```

## 📁 Output Structure

```
[output_dir]/
├── [subreddit1]/
│   ├── images/
│   │   └── [upvotes]_[title].[ext]
│   └── videos/
│       ├── [upvotes]_[title].mp4           # Video only
│       └── [upvotes]_[title]_with_audio.mp4  # Video with audio
├── [subreddit2]/
│   ├── images/
│   └── videos/
└── logs/
    └── reddit_downloader_[timestamp].log
```

## 🔊 Audio Support Notes

Reddit hosts videos with separate audio and video streams. As of 2024:

- Videos marked `has_audio` are checked for available audio streams
- Multiple audio URL patterns are attempted (success rate ~70%)
- Some older videos use formats that don't allow separate audio download
- FFmpeg is required for merging audio and video

## ⚠️ API Limitations

Reddit has strict API rate limits:
- Maximum 60 requests per minute
- The script implements retry logic with exponential backoff
- For large downloads, consider using `--limit` to avoid rate limiting

## 🛠️ Troubleshooting

### Common Issues:

1. **No audio in videos**: Some Reddit videos don't have separable audio tracks or use formats not currently supported
2. **API rate limits**: If you see 429 errors, reduce batch size or use `--limit`
3. **FFmpeg not found**: Ensure FFmpeg is installed and in your PATH

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

Distributed under the MIT License. See `LICENSE` for more information.

---

<div align="center">

Made with ❤️ by [Md Mobashir Rahman](https://github.com/mobashirrahman)

</div>
