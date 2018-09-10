# tgcloud
## UNDER DEVELOPMENT
## Opensourсe Virtual Filesystem for Telegram
Synchronizes and structures files downloaded to Telegram.
- Stores only metadata, accessing raw data only when loading files.
- Loading speed is up to 240Mbit/s per session
- Multiplatform: provides standard volumes which can be mounted on linux/win/mac...
- Opensource
### Project structure:
**tgcloud:** linux based docker container
* **redis** - updates, rpc, communication
* **tfs:** FUSE based VFS module
  * [python-fuse](https://github.com/SlavikMIPT/tfs) - interface to linux kernel FS
  * redis storage - FS struct, meta, telegram file_id,settings
  * rq communication interface
  * docker
* **file_telegram_rxtx** - telegram read/write driver
  * [telethon(sync)](https://github.com/SlavikMIPT/Telethon) by [@Lonami](https://github.com/Lonami) - telegram access, multithreaded downloading/uploading
    * improved and tested by [@SlavikMIPT](https://github.com/SlavikMIPT) - load speed 240Mb/s 
  * rq communication interface
  * docker
* **polling daemon**
  * [telethon(asyncio)](https://github.com/SlavikMIPT/Telethon) - updates from telegram, synchronization, hashtags
  * rq communication interface
  * docker
* **client**
  * telegram authorization interface
  * [filebrowser](https://github.com/SlavikMIPT/filebrowser) - opensource golang filebrowser
  * windows service
  * telegram desktop client with filebrowser
  * settings, statistics, monitoring...
  * rq communication interface
  * docker
![Diagram](/img/ProjectDiagram.png)

You are welcome to collaborate - contact 
Telegram: [@SlavikMIPT](t.me/SlavikMIPT)
