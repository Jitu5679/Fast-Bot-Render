import os
import math
import asyncio
from telethon import TelegramClient, helpers
from telethon.tl.functions.upload import SaveBigFilePartRequest

async def upload_file(client: TelegramClient, file_path: str, progress_callback=None):
    file_size = os.path.getsize(file_path)
    file_id = helpers.generate_random_long()
    
    # Standard Telegram chunk size
    part_size = 512 * 1024
    total_parts = math.ceil(file_size / part_size)
    
    is_large = file_size > 10 * 1024 * 1024
    
    workers = 5  # Number of concurrent connections
    
    queue = asyncio.Queue()
    for i in range(total_parts):
        queue.put_nowait(i)
        
    uploaded_bytes = 0
    
    async def worker():
        nonlocal uploaded_bytes
        with open(file_path, 'rb') as f:
            while not queue.empty():
                try:
                    part_num = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                
                f.seek(part_num * part_size)
                chunk = f.read(part_size)
                
                req = SaveBigFilePartRequest(
                    file_id=file_id,
                    file_part=part_num,
                    file_total_parts=total_parts,
                    bytes=chunk
                )
                
                # Retry loop
                for attempt in range(5):
                    try:
                        await client(req)
                        break
                    except Exception as e:
                        if attempt == 4:
                            raise e
                        await asyncio.sleep(1)
                
                uploaded_bytes += len(chunk)
                if progress_callback:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(uploaded_bytes, file_size)
                    else:
                        progress_callback(uploaded_bytes, file_size)
                        
                queue.task_done()
                
    tasks = [asyncio.create_task(worker()) for _ in range(workers)]
    await asyncio.gather(*tasks)
    
    # To return an InputFile for Telethon
    from telethon.tl.types import InputFileBig
    return InputFileBig(
        id=file_id,
        parts=total_parts,
        name=os.path.basename(file_path)
    )
