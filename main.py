import discord
import asyncio
import aiosqlite
import os
import io
import math
from quart import Quart, request, jsonify, render_template, Response

# ==========================================
# CONFIGURATION
# ==========================================
# Read the bot token from a .env file to keep it out of git history
BOT_TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not BOT_TOKEN and os.path.exists('.env'):
    with open('.env', 'r') as f:
        for line in f:
            if line.strip().startswith('DISCORD_BOT_TOKEN='):
                BOT_TOKEN = line.strip().split('=', 1)[1]
# REPLACE THIS WITH THE ID OF THE CHANNEL WHERE FILES WILL BE STORED
STORAGE_CHANNEL_ID = 1476637189206180065

CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB chunks
DB_FILE = 'database.db'

# ==========================================
# INITIALIZATION
# ==========================================
app = Quart(__name__)
# Allow up to 10 GB file uploads (default is 16MB)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024 * 1024 

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# ==========================================
# DATABASE SETUP
# ==========================================
async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                size INTEGER NOT NULL,
                upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                message_id TEXT NOT NULL,
                FOREIGN KEY (file_id) REFERENCES files (id)
            )
        ''')
        await db.commit()

# ==========================================
# DISCORD BOT EVENTS
# ==========================================
@client.event
async def on_ready():
    print(f'Bot Logged on as {client.user}')

# ==========================================
# WEB SERVER ENDPOINTS
# ==========================================
@app.before_serving
async def startup():
    await init_db()
    # Start the bot in the background
    asyncio.create_task(client.start(BOT_TOKEN))

@app.route('/')
async def index():
    return await render_template('index.html')

@app.route('/files', methods=['GET'])
async def get_files():
    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute('SELECT id, filename, size, upload_date FROM files ORDER BY upload_date DESC') as cursor:
            files = []
            async for row in cursor:
                files.append({
                    'id': row[0],
                    'filename': row[1],
                    'size': row[2],
                    'upload_date': row[3]
                })
            return jsonify({'success': True, 'files': files})

@app.route('/upload', methods=['POST'])
async def upload_file():
    files = await request.files
    if 'file' not in files:
        return jsonify({'success': False, 'error': 'No file part'})
    
    file = files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No selected file'})
    
    file_bytes = file.read()
    file_size = len(file_bytes)
    
    # Check if we have the Discord channel set up properly
    channel = client.get_channel(STORAGE_CHANNEL_ID)
    if not channel:
        return jsonify({'success': False, 'error': 'Storage channel not found or bot not ready.'}), 500

    async with aiosqlite.connect(DB_FILE) as db:
        # 1. Insert file record
        cursor = await db.execute('INSERT INTO files (filename, size) VALUES (?, ?)', (file.filename, file_size))
        file_id = cursor.lastrowid
        
        # 2. Chunking and Uploading to Discord
        total_chunks = math.ceil(file_size / CHUNK_SIZE)
        
        for i in range(total_chunks):
            start = i * CHUNK_SIZE
            end = start + CHUNK_SIZE
            chunk_data = file_bytes[start:end]
            
            # Send chunk to Discord
            with io.BytesIO(chunk_data) as stream:
                discord_file = discord.File(fp=stream, filename=f"{file_id}_chunk_{i}.bin")
                try:
                    message = await channel.send(
                        content=f"**FileID:** {file_id} | **Chunk:** {i+1}/{total_chunks} | **Orig Name:** `{file.filename}`",
                        file=discord_file
                    )
                    # 3. Save chunk metadata
                    await db.execute(
                        'INSERT INTO chunks (file_id, chunk_index, message_id) VALUES (?, ?, ?)',
                        (file_id, i, str(message.id))
                    )
                except Exception as e:
                    await db.rollback()
                    return jsonify({'success': False, 'error': f'Failed to upload chunk: {str(e)}'}), 500
        
        await db.commit()

    return jsonify({'success': True, 'message': 'File uploaded successfully', 'file_id': file_id})

@app.route('/download/<int:file_id>', methods=['GET'])
async def download_file(file_id):
    async with aiosqlite.connect(DB_FILE) as db:
        # 1. Get file metadata
        async with db.execute('SELECT filename FROM files WHERE id = ?', (file_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return jsonify({'success': False, 'error': 'File not found'}), 404
            filename = row[0]
            
        # 2. Get chunk metadata, sorted by index
        chunks = []
        async with db.execute('SELECT message_id FROM chunks WHERE file_id = ? ORDER BY chunk_index ASC', (file_id,)) as cursor:
            async for row in cursor:
                chunks.append(row[0])
                
    if not chunks:
         return jsonify({'success': False, 'error': 'No chunks found for this file'}), 404

    channel = client.get_channel(STORAGE_CHANNEL_ID)
    if not channel:
        return jsonify({'success': False, 'error': 'Storage channel not found.'}), 500

    # Stream the file back
    async def generate_file_stream():
        for str_message_id in chunks:
            message_id = int(str_message_id)
            try:
                message = await channel.fetch_message(message_id)
                if not message.attachments:
                    continue
                attachment = message.attachments[0]
                # Read attachment bytes
                chunk_bytes = await attachment.read()
                yield chunk_bytes
            except Exception as e:
                 print(f"Error fetching chunk {message_id}: {e}")
                 # You might want to handle this more gracefully

    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"'
    }
    return Response(generate_file_stream(), headers=headers, mimetype='application/octet-stream')


# ==========================================
# RUN APPLICATION
# ==========================================
if __name__ == '__main__':
    # Quart runs securely using asyncio
    app.run(host='0.0.0.0', port=5000)