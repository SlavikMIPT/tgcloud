# tgcloud

Opensourse Telegram based cloud storage
using:

```
from telegram_client_x import TelegramClientX

client = TelegramClientX(entity, api_id, api_hash, update_workers=None, spawn_read_thread=True)

client.set_upload_threads_count(24)

client.set_download_threads_count(8)
```
