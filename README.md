🚀 Multi-Step Uploader Bot v1.0 - Complete Feature Showcase


📂 Core Upload Engine

      🌳 Recursive Folder Traversal: Uploads entire directory trees with infinite depth

  🎯 Intelligent File Classification: Auto-separates images from documents for optimal handling

  ⚡ Async Architecture: Non-blocking uploads with parallel-ready design

  🛡️ Path Security: Validates and sanitizes all paths to prevent directory traversal attacks

  🖼️ Media Management Mastery

Image Features
📦 Album Mode (/album on): Groups images into sleek 10-photo albums
🖼️ Individual Mode (/album off): Sends photos one-by-one for granular control
🎨 Smart Album Captions (/albumcaptions): Embeds folder names as album titles
📸 Image Captions (/imagecaptions): Shows folder name on individual photos
Document Features
📎 Document Grouping (/docgroup on): Batches documents into groups of 10
📄 Individual Mode (/docgroup off): Sends documents one-by-one
📝 Filename-Only Captions (/captions): Documents show just the filename, never messy paths
💬 Forum Topic Automation
📌 Auto-Topic Creation: Each subfolder becomes its own forum topic (when enabled)
🎯 Native Topic Names: Topics use exact folder names - clean and professional
🛡️ Permission-Aware: Automatically checks bot's "Manage Topics" admin right
🔄 Graceful Degradation: Fails back to main chat if topics aren't available
📊 Topic Tracking: Shows count of successfully created topics in final summary
🛡️ Enterprise-Grade Reliability
🔄 Exponential Backoff: 3 automatic retries with increasing delays (2s → 4s → 8s)
⏱️ Dynamic Rate Limiting: Smart delays based on file size (up to 5s for large files)
⏳ 5-Minute Timeouts: Handles massive files without choking
📊 Real-Time Statistics: Live success/failure/skip counts during upload
💾 Dual Logging: Console + file logging with emoji-enhanced readability
🚨 Error Recovery: Continues upload even if individual files fail
⚙️ Granular Configuration Commands
Table
Copy
Command	Function	Default
/upload <path>	Start recursive folder upload	-
`/topics on	off`	Create forum topic per subfolder	OFF
`/album on	off`	Batch images into albums	ON
`/docgroup on	off`	Group documents into batches	OFF
`/albumcaptions on	off`	Show folder name on albums	OFF
`/captions on	off`	Show filename on documents	ON
`/imagecaptions on	off`	Show folder name on photos	OFF
`/logs on	off`	Enable/disable file logging	ON
/stats	View lifetime upload statistics	-
/exportlog	Download detailed operation logs	-
🎨 User Experience Excellence
📱 Telegram-Native: Uses official Bot API for maximum compatibility
🔐 Security First: Validates paths, checks permissions, skips malicious input
📈 Progress Tracking: Live editing status messages show current subfolder & file count
✨ Clean Aesthetics: All captions in monospace format for consistency
🎯 Smart Defaults: Sensible out-of-the-box settings for immediate use
✅ Requirements for Premium Features
Forum Topics require:
Group converted to Forum in settings
Bot promoted to Admin with Manage Topics permission
Document Grouping works in any chat type (no special requirements)
📊 Upload Statistics Tracked
✅ Successful uploads
❌ Failed uploads (after all retries)
⊘ Skipped files (too large, not readable)
Version 1.0 - Upload Smarter, Not Harder

Reliability Features
Automatic Retries: 3 attempts with exponential backoff
Rate Limiting: Dynamic delays based on file size
Timeout Handling: 5-minute timeout for large files
Error Logging: Detailed logs with emojis for readability
Size Limits: Skips files > 50MB with warning



Commands
Copy
/start          - Show help menu
/upload <path>  - Upload folder
/topics on|off   - Toggle forum topics
/album on|off    - Toggle album mode
/albumcaptions on|off - Toggle album captions
/captions on|off - Toggle document filename captions
/imagecaptions on|off - Toggle image folder captions
/logs on|off     - Enable/disable logging
/exportlog      - Download log file
/stats          - View upload statistics


the main goal of this was to create a upload bot that would stucture my comic collection how i want it to be done on telegram,
so a directory of comics with cover images (one can apply this to tv shows or movies or anime folder),c the bot will create a topic of that folder name, it will first upload the image and then the data that is in that folder

get a telegram Bot Token from @BotFather, place that token key in line 8, where it says YOUR_BOT_TOKEN_HERE. (add the bot to where you want to make sure it has the correct premissions).
and then start the bot within the telegram group its been added to.
open terminal or cmd and run python .\msu.py
you then should see a reply of all the commands you can use in that telegram group.
