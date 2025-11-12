import os
import asyncio
import logging
from datetime import datetime
from telegram import Update, InputMediaPhoto, InputMediaDocument, ChatMemberAdministrator
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import NetworkError, TimedOut, RetryAfter, BadRequest, Forbidden

# Configuration
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp', '.svg'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
LOGGING_ENABLED = True
LOG_FILE_PATH = "bot_upload_logs.txt"

# Reliability settings
MAX_RETRIES = 3
INITIAL_RETRY_DELAY = 2  # seconds
TIMEOUT_SECONDS = 300  # 5 minutes for large files
RATE_LIMIT_DELAY = 1.0  # Base delay between requests

logger = None
upload_stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

def setup_logger():
    """Initialize logger with file and console output"""
    global logger
    logger = logging.getLogger("telegram_uploader")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if LOGGING_ENABLED:
        file_handler = logging.FileHandler(LOG_FILE_PATH, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def log_message(level, message):
    """Log message to both console and file"""
    if not logger:
        return
        
    icon_map = {'info': '🔍', 'error': '❌', 'warning': '⚠️', 'success': '✅', 'debug': '🐛'}
    icon = icon_map.get(level, '•')
    formatted_message = f"{icon} {message}"
    
    if level == "info":
        logger.info(formatted_message)
    elif level == "error":
        logger.error(formatted_message)
    elif level == "warning":
        logger.warning(formatted_message)
    elif level == "success":
        logger.info(formatted_message)
    elif level == "debug":
        logger.debug(formatted_message)

def reset_stats():
    """Reset upload statistics"""
    global upload_stats
    upload_stats = {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}

def update_stats(action):
    """Update upload statistics"""
    global upload_stats
    upload_stats[action] += 1
    upload_stats['total'] += 1

async def retry_with_backoff(func, *args, **kwargs):
    """Retry function with exponential backoff"""
    last_exception = None
    
    for attempt in range(MAX_RETRIES):
        try:
            return await func(*args, **kwargs)
        except RetryAfter as e:
            wait_time = e.retry_after + 2
            log_message("warning", f"Rate limited. Waiting {wait_time}s...")
            await asyncio.sleep(wait_time)
        except (NetworkError, TimedOut) as e:
            last_exception = e
            delay = INITIAL_RETRY_DELAY * (2 ** attempt)
            log_message("warning", f"Network error (attempt {attempt + 1}/{MAX_RETRIES}). Retrying in {delay}s...")
            await asyncio.sleep(delay)
        except Exception as e:
            log_message("error", f"Non-retryable error: {str(e)}")
            raise e
    
    raise last_exception

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📁 <b>Multi-Step Uploader Bot v1.0</b>\n\n"
        "Send a folder path to start upload:\n"
        "<code>/upload /path/to/your/folder</code>\n\n"
        "Settings:\n"
        "<code>/topics on|off</code> - Create forum topic per subfolder (default: OFF)\n"
        "<code>/album on|off</code> - Album mode: group images into albums (default: ON)\n"
        "<code>/docgroup on|off</code> - Group documents into batches (default: OFF)\n"
        "<code>/albumcaptions on|off</code> - Add folder caption to albums (default: OFF)\n"
        "<code>/captions on|off</code> - Doc filename captions (default: ON)\n"
        "<code>/imagecaptions on|off</code> - Image folder name captions (default: OFF)\n"
        "<code>/logs on|off</code> - Enable/disable logging\n"
        "Commands:\n"
        "<code>/exportlog</code> - Export log file\n"
        "<code>/stats</code> - View upload statistics\n\n"
        "<b>⚠️ For topics to work:</b>\n"
        "1. Make bot admin with 'Manage Topics' permission\n"
        "2. Convert group to forum in Group Settings > Topics",
        parse_mode=ParseMode.HTML
    )

async def topics_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle forum topics mode for subfolders"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('topics_enabled', False) else "disabled"
        await update.message.reply_text(
            f"Topics mode is currently <b>{status}</b>\n\n"
            f"Use: <code>/topics on</code> (create separate topics for subfolders) or <code>/topics off</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        # Comprehensive forum and permission check
        chat_id = update.effective_chat.id
        can_create_topics = False
        forum_status = "Unknown"
        
        try:
            chat = await context.bot.get_chat(chat_id)
            is_forum = getattr(chat, 'is_forum', False)
            
            if is_forum:
                # Check bot's admin permissions
                bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                if isinstance(bot_member, ChatMemberAdministrator) and bot_member.can_manage_topics:
                    can_create_topics = True
                    forum_status = "Forum with proper bot permissions"
                else:
                    forum_status = "Forum but bot lacks 'Manage Topics' permission"
            else:
                forum_status = "Not a forum (convert in Group Settings > Topics)"
            
        except Exception as e:
            log_message("error", f"Failed to check forum status: {str(e)}")
            forum_status = f"Error checking status: {str(e)}"
        
        if not can_create_topics:
            await update.message.reply_text(
                f"⚠️ <b>Warning: {forum_status}</b>\n\n"
                f"Topic creation will likely fail. Ensure:\n"
                f"1. Group is converted to forum\n"
                f"2. Bot is admin with 'Manage Topics' permission\n\n"
                f"Proceeding anyway - uploads will fallback to main chat if topics fail.",
                parse_mode=ParseMode.HTML
            )
        
        context.chat_data['topics_enabled'] = True
        await update.message.reply_text("✅ Topics mode enabled.")
        log_message("info", f"=== Topics mode enabled by user === Forum status: {forum_status}")
    else:
        context.chat_data['topics_enabled'] = False
        await update.message.reply_text("✅ Topics mode disabled. All files will be uploaded to main chat.")
        log_message("info", "=== Topics mode disabled by user ===")

async def album_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle album mode"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('album_mode_enabled', True) else "disabled"
        await update.message.reply_text(
            f"Album mode is currently <b>{status}</b>\n\n"
            f"Use: <code>/album on</code> (group into albums) or <code>/album off</code> (send individually)",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        context.chat_data['album_mode_enabled'] = True
        await update.message.reply_text("✅ Album mode enabled (images will be grouped into albums).")
        log_message("info", "=== Album mode enabled by user ===")
    else:
        context.chat_data['album_mode_enabled'] = False
        await update.message.reply_text("✅ Album mode disabled (images will be sent individually).")
        log_message("info", "=== Album mode disabled by user ===")

async def docgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle document grouping mode"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('doc_group_enabled', False) else "disabled"
        await update.message.reply_text(
            f"Document grouping is currently <b>{status}</b>\n\n"
            f"Use: <code>/docgroup on</code> (group into batches) or <code>/docgroup off</code> (send individually)",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        context.chat_data['doc_group_enabled'] = True
        await update.message.reply_text("✅ Document grouping enabled (documents will be sent in groups).")
        log_message("info", "=== Document grouping enabled by user ===")
    else:
        context.chat_data['doc_group_enabled'] = False
        await update.message.reply_text("✅ Document grouping disabled (documents will be sent individually).")
        log_message("info", "=== Document grouping disabled by user ===")

async def albumcaptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle captions for image albums (when album mode is ON)"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('album_captions_enabled', False) else "disabled"
        await update.message.reply_text(
            f"Album captions are currently <b>{status}</b>\n\n"
            f"Use: <code>/albumcaptions on</code> (add folder caption to album) or <code>/albumcaptions off</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        context.chat_data['album_captions_enabled'] = True
        await update.message.reply_text("✅ Album captions enabled (shows folder name on album).")
        log_message("info", "=== Album captions enabled by user ===")
    else:
        context.chat_data['album_captions_enabled'] = False
        await update.message.reply_text("✅ Album captions disabled (albums have no caption).")
        log_message("info", "=== Album captions disabled by user ===")

async def captions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable/disable filename captions for documents"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('captions_enabled', True) else "disabled"
        await update.message.reply_text(
            f"Document captions are currently <b>{status}</b>\n\n"
            f"Use: <code>/captions on</code> or <code>/captions off</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        context.chat_data['captions_enabled'] = True
        await update.message.reply_text("✅ Document captions enabled (shows filename only).")
        log_message("info", "=== Document captions enabled by user (filename only) ===")
    else:
        context.chat_data['captions_enabled'] = False
        await update.message.reply_text("✅ Document captions disabled.")
        log_message("info", "=== Document captions disabled by user ===")

async def imagecaptions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable/disable folder name captions for individual images (when album mode is OFF)"""
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if context.chat_data.get('image_captions_enabled', False) else "disabled"
        await update.message.reply_text(
            f"Image captions are currently <b>{status}</b>\n\n"
            f"Use: <code>/imagecaptions on</code> or <code>/imagecaptions off</code>",
            parse_mode=ParseMode.HTML
        )
        return
    
    if context.args[0].lower() == 'on':
        context.chat_data['image_captions_enabled'] = True
        await update.message.reply_text("✅ Image captions enabled (shows folder name on each photo).")
        log_message("info", "=== Image captions enabled by user ===")
    else:
        context.chat_data['image_captions_enabled'] = False
        await update.message.reply_text("✅ Image captions disabled.")
        log_message("info", "=== Image captions disabled by user ===")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upload statistics"""
    stats_text = (
        f"📊 <b>Upload Statistics</b>\n\n"
        f"Total: {upload_stats['total']}\n"
        f"✅ Success: {upload_stats['success']}\n"
        f"❌ Failed: {upload_stats['failed']}\n"
        f"⊘ Skipped: {upload_stats['skipped']}"
    )
    await update.message.reply_text(stats_text, parse_mode=ParseMode.HTML)

async def logs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Enable/disable logging"""
    global LOGGING_ENABLED
    
    if not context.args or context.args[0].lower() not in ['on', 'off']:
        status = "enabled" if LOGGING_ENABLED else "disabled"
        await update.message.reply_text(f"Logging is currently <b>{status}</b>", parse_mode=ParseMode.HTML)
        return
    
    if context.args[0].lower() == 'on':
        LOGGING_ENABLED = True
        setup_logger()
        await update.message.reply_text("✅ Logging enabled. Logs will be saved to file.")
        log_message("info", "=== Logging enabled by user ===")
    else:
        LOGGING_ENABLED = False
        setup_logger()
        await update.message.reply_text("✅ Logging disabled. Only console output will be shown.")

async def export_log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export log file to user"""
    if not LOGGING_ENABLED or not os.path.exists(LOG_FILE_PATH):
        await update.message.reply_text("❌ Logging is disabled or no log file exists.")
        return
    
    try:
        with open(LOG_FILE_PATH, 'rb') as log_file:
            await update.message.reply_document(
                document=log_file,
                filename=f"upload_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                caption=f"Upload log export"
            )
    except Exception as e:
        await update.message.reply_text(f"❌ Error exporting log: {str(e)}")

async def upload_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main handler for /upload command"""
    if not context.args:
        await update.message.reply_text("❌ Please provide a folder path: /upload /path/to/folder")
        return
    
    folder_path = " ".join(context.args)
    
    if ".." in folder_path or not os.path.isdir(folder_path):
        await update.message.reply_text("❌ Invalid folder path!")
        return
    
    if not os.path.exists(folder_path):
        await update.message.reply_text(f"❌ Folder not found: {folder_path}")
        return
    
    folder_name = os.path.basename(os.path.abspath(folder_path))
    reset_stats()
    
    # Check all preferences
    topics_enabled = context.chat_data.get('topics_enabled', False)
    album_mode = context.chat_data.get('album_mode_enabled', True)
    doc_group = context.chat_data.get('doc_group_enabled', False)
    album_captions = context.chat_data.get('album_captions_enabled', False)
    doc_captions = context.chat_data.get('captions_enabled', True)
    image_captions = context.chat_data.get('image_captions_enabled', False)
    chat_id = update.effective_chat.id
    
    try:
        log_message("info", f"📂 Starting upload for folder: {folder_name}")
        log_message("info", f"📂 Full path: {folder_path}")
        log_message("info", f"📌 Topics mode: {topics_enabled}")
        log_message("info", f"📦 Album mode: {album_mode}")
        log_message("info", f"📎 Doc group mode: {doc_group}")
        log_message("info", f"🖼️ Album captions: {album_captions}")
        log_message("info", f"📝 Doc captions: {doc_captions}")
        log_message("info", f"🖼️ Image captions: {image_captions}")
        
        # Get chat info for forum status
        chat = await context.bot.get_chat(chat_id)
        is_forum = getattr(chat, 'is_forum', False)
        log_message("debug", f"Chat forum status: {is_forum}")
        
        # Format status line
        status_line = f"📌 Topics: {'ON' if topics_enabled else 'OFF'} | 📦 Album: {'ON' if album_mode else 'OFF'} | 📎 DocGroup: {'ON' if doc_group else 'OFF'} | 🖼️ AlbumCap: {'ON' if album_captions else 'OFF'} | 📝 Docs: {'ON' if doc_captions else 'OFF'} | 🖼️ ImgCap: {'ON' if image_captions else 'OFF'}"
        
        # Main status message stays in the main chat
        title_msg = await update.message.reply_text(
            f"📂 <b>Uploading Folder:</b> <code>{folder_name}</code>\n"
            f"{status_line}\n"
            f"⏳ Scanning contents...",
            parse_mode=ParseMode.HTML
        )
        
        # Build subfolder map
        subfolder_map = {}
        for root, dirs, files in os.walk(folder_path):
            rel_root = os.path.relpath(root, folder_path)
            if rel_root == '.':
                rel_root = ''  # Root folder
            
            if rel_root not in subfolder_map:
                subfolder_map[rel_root] = {'images': [], 'documents': []}
            
            for file in files:
                full_path = os.path.join(root, file)
                if not os.path.isfile(full_path):
                    continue
                
                rel_path = os.path.relpath(full_path, folder_path)
                ext = os.path.splitext(full_path)[1].lower()
                
                if ext in IMAGE_EXTENSIONS:
                    subfolder_map[rel_root]['images'].append((full_path, rel_path))
                else:
                    subfolder_map[rel_root]['documents'].append((full_path, rel_path))
        
        total_files = sum(len(v['images']) + len(v['documents']) for v in subfolder_map.values())
        if total_files == 0:
            await title_msg.edit_text("📂 Folder is empty!")
            log_message("warning", "Folder is empty!")
            return
        
        log_message("info", f"📊 Found {total_files} total files in {len(subfolder_map)} subfolders")
        
        # Process each subfolder sequentially
        processed_folders = 0
        topics_created = 0
        
        for subfolder, files_dict in sorted(subfolder_map.items()):
            if len(files_dict['images']) == 0 and len(files_dict['documents']) == 0:
                continue
            
            processed_folders += 1
            folder_display = subfolder if subfolder else "Root"
            
            # Determine album caption folder name (just the folder, not full path)
            album_caption_folder = folder_name if subfolder == '' else subfolder
            
            folder_display_full = f"{folder_name}/{subfolder}" if subfolder else folder_name
            
            # Create topic for subfolder if topics enabled
            topic_id = None
            if topics_enabled and subfolder:
                log_message("debug", f"Attempting to create topic for subfolder: {folder_display}")
                
                try:
                    if is_forum:
                        # Check bot permissions explicitly
                        bot_member = await context.bot.get_chat_member(chat_id, context.bot.id)
                        can_manage = getattr(bot_member, 'can_manage_topics', False)
                        
                        if can_manage:
                            # Topic name is just the folder name
                            topic_name = folder_display[:128]
                            
                            topic = await context.bot.create_forum_topic(
                                chat_id=chat_id,
                                name=topic_name
                            )
                            topic_id = topic.message_thread_id
                            topics_created += 1
                            log_message("success", f"✅ Created topic for subfolder: {folder_display} (ID: {topic_id})")
                            
                            # Send a header message in the topic
                            await context.bot.send_message(
                                chat_id=chat_id,
                                message_thread_id=topic_id,
                                text=f"📂 <b>Uploading to topic:</b> <code>{folder_display}</code>",
                                parse_mode=ParseMode.HTML
                            )
                        else:
                            log_message("warning", f"Bot lacks 'Manage Topics' permission for {folder_display}")
                    else:
                        log_message("warning", f"Chat is not a forum, cannot create topic for {folder_display}")
                        
                except BadRequest as e:
                    log_message("error", f"❌ BadRequest creating topic for {folder_display}: {str(e)}")
                    topic_id = None
                except Forbidden as e:
                    log_message("error", f"❌ Forbidden creating topic for {folder_display}: {str(e)}")
                    topic_id = None
                except Exception as e:
                    log_message("error", f"❌ Unexpected error creating topic for {folder_display}: {str(e)}")
                    topic_id = None
            
            # Step 2: Upload pictures for this subfolder
            if files_dict['images']:
                log_message("info", f"📂 Processing subfolder: {folder_display}")
                log_message("info", f"🖼️ Uploading {len(files_dict['images'])} images")
                
                # Update main status message in the main chat (no message_thread_id)
                await title_msg.edit_text(
                    f"📂 <b>{folder_name}</b>\n"
                    f"{status_line}\n"
                    f"🖼️ <b>Subfolder:</b> <code>{folder_display}</code> {'📌 (Topic)' if topic_id else ''}\n"
                    f"📤 Uploading {len(files_dict['images'])} image(s)...",
                    parse_mode=ParseMode.HTML,
                )
                
                # Pass album_caption_folder instead of folder_display_full
                if album_mode:
                    await upload_media_groups(update, context, files_dict['images'], album_captions, album_caption_folder, topic_id)
                else:
                    await upload_images_individual(update, context, files_dict['images'], image_captions, topic_id)
                
                log_message("success", f"✅ Images complete for {folder_display}")
                await asyncio.sleep(1)
            
            # Step 3: Upload documents for this subfolder
            if files_dict['documents']:
                if not files_dict['images']:
                    log_message("info", f"📂 Processing subfolder: {folder_display}")
                
                log_message("info", f"📄 Uploading {len(files_dict['documents'])} documents")
                
                # Update main status message in the main chat (no message_thread_id)
                await title_msg.edit_text(
                    f"📂 <b>{folder_name}</b>\n"
                    f"{status_line}\n"
                    f"📄 <b>Subfolder:</b> <code>{folder_display}</code> {'📌 (Topic)' if topic_id else ''}\n"
                    f"📤 Uploading {len(files_dict['documents'])} document(s)...",
                    parse_mode=ParseMode.HTML,
                )
                
                # Use document grouping if enabled
                if doc_group:
                    await upload_document_groups(update, context, files_dict['documents'], doc_captions, topic_id)
                else:
                    await upload_documents(update, context, files_dict['documents'], doc_captions, topic_id)
                
                log_message("success", f"✅ Documents complete for {folder_display}")
                await asyncio.sleep(1)
        
        # Final update in main chat
        topics_info = f" | 📌 Created {topics_created} topics" if topics_enabled and topics_created > 0 else ""
        
        await title_msg.edit_text(
            f"✅ <b>Upload Complete!</b>\n\n"
            f"📂 <b>Folder:</b> {folder_name}\n"
            f"{status_line}{topics_info}\n\n"
            f"📊 <b>Stats:</b> {upload_stats['success']}/{total_files} files\n"
            f"❌ Failed: {upload_stats['failed']} | ⊘ Skipped: {upload_stats['skipped']}",
            parse_mode=ParseMode.HTML
        )
        
        log_message("info", f"🏁 All uploads finished: {upload_stats}")
        
    except Exception as e:
        log_message("error", f"❌ Fatal error: {str(e)}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def upload_images_individual(update: Update, context: ContextTypes.DEFAULT_TYPE, image_files: list, captions_enabled: bool, topic_id: int = None):
    """Upload images individually (album mode OFF)"""
    chat_id = update.effective_chat.id
    
    for idx, (file_path, rel_path) in enumerate(image_files, 1):
        try:
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            if file_size > MAX_FILE_SIZE:
                log_message("warning", f"  ⊘ Skipped (too large): {rel_path} ({file_size_mb:.2f}MB)")
                update_stats('skipped')
                continue
            
            if not os.access(file_path, os.R_OK):
                log_message("warning", f"  ⊘ Skipped (not readable): {rel_path}")
                update_stats('skipped')
                continue
            
            log_message("info", f"  🖼️ [{idx}/{len(image_files)}] Uploading: {rel_path} ({file_size_mb:.2f}MB)")
            
            # Prepare caption showing folder name
            caption = None
            parse_mode = None
            
            if captions_enabled:
                parent_folder = os.path.dirname(rel_path)
                folder_name_part = os.path.basename(parent_folder) if parent_folder else "Root"
                caption = f"<code>{folder_name_part}</code>"
                parse_mode = ParseMode.HTML
            
            with open(file_path, 'rb') as file:
                await retry_with_backoff(
                    context.bot.send_photo,
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    photo=file,
                    caption=caption,
                    parse_mode=parse_mode
                )
            
            update_stats('success')
            log_message("info", f"  ✅ Uploaded: {rel_path}")
            
            # Dynamic delay based on file size
            size_delay = min(file_size_mb / 10, 5)
            await asyncio.sleep(RATE_LIMIT_DELAY + size_delay)
            
        except Exception as e:
            log_message("error", f"  ❌ Failed after retries: {rel_path} - {str(e)}")
            update_stats('failed')

async def upload_media_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, image_files: list, album_captions_enabled: bool, folder_name: str, topic_id: int = None):
    """Upload images in media groups (albums) of up to 10 photos each"""
    chat_id = update.effective_chat.id
    batch_size = 10
    
    for i in range(0, len(image_files), batch_size):
        batch = image_files[i:i + batch_size]
        media_group = []
        open_files = []
        batch_num = i // batch_size + 1
        total_batches = (len(image_files) + batch_size - 1) // batch_size
        
        log_message("info", f"  📦 Processing image batch {batch_num}/{total_batches} ({len(batch)} files)")
        
        try:
            # Build media group
            for idx, (file_path, rel_path) in enumerate(batch):
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)
                
                if file_size > MAX_FILE_SIZE:
                    log_message("warning", f"    ⊘ Skipped (too large): {rel_path} ({file_size_mb:.2f}MB)")
                    update_stats('skipped')
                    continue
                
                if not os.access(file_path, os.R_OK):
                    log_message("warning", f"    ⊘ Skipped (not readable): {rel_path}")
                    update_stats('skipped')
                    continue
                
                file = open(file_path, 'rb')
                open_files.append(file)
                
                # Use folder_name parameter which now contains just the folder name
                if album_captions_enabled and idx == 0:
                    media_group.append(InputMediaPhoto(
                        media=file,
                        caption=f"<code>{folder_name}</code>",
                        parse_mode=ParseMode.HTML
                    ))
                else:
                    media_group.append(InputMediaPhoto(media=file))
                
                log_message("info", f"    📤 Queued: {rel_path} ({file_size_mb:.2f}MB)")
            
            # Send album with retry logic
            if media_group:
                await retry_with_backoff(
                    context.bot.send_media_group,
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    media=media_group,
                    read_timeout=TIMEOUT_SECONDS,
                    write_timeout=TIMEOUT_SECONDS
                )
                update_stats('success')
                log_message("info", f"    ✅ Batch {batch_num} uploaded")
                
                # Dynamic rate limiting
                await asyncio.sleep(RATE_LIMIT_DELAY * len(media_group) * 0.5)
            
        except Exception as e:
            log_message("error", f"    ❌ Batch {batch_num} failed: {str(e)}")
            update_stats('failed')
        finally:
            for f in open_files:
                try:
                    f.close()
                except Exception:
                    pass

async def upload_document_groups(update: Update, context: ContextTypes.DEFAULT_TYPE, doc_files: list, captions_enabled: bool, topic_id: int = None):
    """Upload documents in media groups (batches) of up to 10 documents each"""
    chat_id = update.effective_chat.id
    batch_size = 10
    
    for i in range(0, len(doc_files), batch_size):
        batch = doc_files[i:i + batch_size]
        media_group = []
        open_files = []
        batch_num = i // batch_size + 1
        total_batches = (len(doc_files) + batch_size - 1) // batch_size
        
        log_message("info", f"  📎 Processing document batch {batch_num}/{total_batches} ({len(batch)} files)")
        
        try:
            # Build media group
            for idx, (file_path, rel_path) in enumerate(batch):
                file_size = os.path.getsize(file_path)
                file_size_mb = file_size / (1024 * 1024)
                
                if file_size > MAX_FILE_SIZE:
                    log_message("warning", f"    ⊘ Skipped (too large): {rel_path} ({file_size_mb:.2f}MB)")
                    update_stats('skipped')
                    continue
                
                if not os.access(file_path, os.R_OK):
                    log_message("warning", f"    ⊘ Skipped (not readable): {rel_path}")
                    update_stats('skipped')
                    continue
                
                file = open(file_path, 'rb')
                open_files.append(file)
                
                # Prepare caption (filename only)
                filename_only = os.path.basename(file_path)
                caption = f"<code>{filename_only}</code>" if captions_enabled else None
                
                # Add to media group
                media_group.append(
                    InputMediaDocument(
                        media=file,
                        filename=filename_only,
                        caption=caption,
                        parse_mode=ParseMode.HTML if captions_enabled else None
                    )
                )
                
                log_message("info", f"    📎 Queued: {rel_path} ({file_size_mb:.2f}MB)")
            
            # Send document group with retry logic
            if media_group:
                await retry_with_backoff(
                    context.bot.send_media_group,
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    media=media_group,
                    read_timeout=TIMEOUT_SECONDS,
                    write_timeout=TIMEOUT_SECONDS
                )
                update_stats('success')
                log_message("info", f"    ✅ Document batch {batch_num} uploaded")
                
                # Dynamic rate limiting
                await asyncio.sleep(RATE_LIMIT_DELAY * len(media_group) * 0.5)
            
        except Exception as e:
            log_message("error", f"    ❌ Document batch {batch_num} failed: {str(e)}")
            update_stats('failed')
        finally:
            for f in open_files:
                try:
                    f.close()
                except Exception:
                    pass

async def upload_documents(update: Update, context: ContextTypes.DEFAULT_TYPE, doc_files: list, captions_enabled: bool, topic_id: int = None):
    """Upload documents individually with optional captions and retry logic"""
    chat_id = update.effective_chat.id
    
    for idx, (file_path, rel_path) in enumerate(doc_files, 1):
        try:
            file_size = os.path.getsize(file_path)
            file_size_mb = file_size / (1024 * 1024)
            
            if file_size > MAX_FILE_SIZE:
                log_message("warning", f"  ⊘ Skipped (too large): {rel_path} ({file_size_mb:.2f}MB)")
                update_stats('skipped')
                continue
            
            if not os.access(file_path, os.R_OK):
                log_message("warning", f"  ⊘ Skipped (not readable): {rel_path}")
                update_stats('skipped')
                continue
            
            log_message("info", f"  📄 [{idx}/{len(doc_files)}] Uploading: {rel_path} ({file_size_mb:.2f}MB)")
            
            with open(file_path, 'rb') as file:
                # Caption shows only filename, not folder path
                filename_only = os.path.basename(file_path)
                caption = f"<code>{filename_only}</code>" if captions_enabled else None
                parse_mode = ParseMode.HTML if captions_enabled else None
                
                await retry_with_backoff(
                    context.bot.send_document,
                    chat_id=chat_id,
                    message_thread_id=topic_id,
                    document=file,
                    filename=filename_only,
                    caption=caption,
                    parse_mode=parse_mode
                )
            
            update_stats('success')
            log_message("info", f"  ✅ Uploaded: {rel_path}")
            
            # Dynamic delay based on file size
            size_delay = min(file_size_mb / 10, 5)
            await asyncio.sleep(RATE_LIMIT_DELAY + size_delay)
            
        except Exception as e:
            log_message("error", f"  ❌ Failed after retries: {rel_path} - {str(e)}")
            update_stats('failed')

def main():
    global logger
    
    # ** TERMINAL SPLASH SCREEN **
    print("\n" + "="*60)
    print("     📁 Multi-Step Uploader Bot v1.0")
    print("="*60)
    print("A robust Telegram bot for recursive folder uploads")
    print("with album grouping, forum topics, and smart captions")
    print("="*60 + "\n")
    
    logger = setup_logger()
    log_message("info", "=== Bot Started ===")
    
    print("Configuration:")
    print(f"  • Logging enabled: {LOGGING_ENABLED}")
    if LOGGING_ENABLED:
        print(f"  • Log file: {LOG_FILE_PATH}")
    print(f"  • Max retries: {MAX_RETRIES}")
    print(f"  • Timeout: {TIMEOUT_SECONDS}s")
    print(f"  • Rate limit delay: {RATE_LIMIT_DELAY}s")
    print("\nBot is running! Press Ctrl+C to stop\n")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("upload", upload_command))
    app.add_handler(CommandHandler("topics", topics_command))
    app.add_handler(CommandHandler("album", album_command))
    app.add_handler(CommandHandler("docgroup", docgroup_command))
    app.add_handler(CommandHandler("albumcaptions", albumcaptions_command))
    app.add_handler(CommandHandler("captions", captions_command))
    app.add_handler(CommandHandler("imagecaptions", imagecaptions_command))
    app.add_handler(CommandHandler("logs", logs_command))
    app.add_handler(CommandHandler("exportlog", export_log_command))
    
    print("Bot is running! Send /upload <folder_path> to test")
    print("Settings: /topics, /album, /docgroup, /albumcaptions, /captions, /imagecaptions, /logs")
    app.run_polling()

if __name__ == "__main__":
    main()